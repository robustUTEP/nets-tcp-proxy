import sys
import traceback
from select import *
from socket import *
import time
import random

import re
import params

switchesVarDefaults = (
    (('-l', '--listenPort') ,'listenPort', 50000),
    (('-s', '--server'), 'server', "127.0.0.1:50001"),
    (('-d', '--debug'), "debug", False), # boolean (set if present)
    (('-?', '--usage'), "usage", False) # boolean (set if present)
    )

paramMap = params.parseParams(switchesVarDefaults)
server, listenPort, usage, debug = paramMap["server"], paramMap["listenPort"], paramMap["usage"], paramMap["debug"]

if usage:
    params.usage()

try:
    serverHost, serverPort = re.split(":", server)
    serverPort = int(serverPort)
except:
    print "Can't parse server:port from '%s'" % server
    sys.exit(1)

try:
    listenPort = int(listenPort)
except:
    print "Can't parse listen port from %s" % listenPort
    sys.exit(1)


sockNames = {}               # from socket to name
nextConnectionNumber = 0     # each connection is assigned a unique id

now = time.time()

class Fwd:
    def __init__(self, conn, inSock, outSock, bufCap = 1000):
        global now
        self.conn, self.inSock, self.outSock, self.bufCap = conn, inSock, outSock, bufCap
        self.inClosed, self.buf = 0, ""
        self.delaySendUntil = 0 # no delay
    def checkRead(self):
        if len(self.buf) < self.bufCap and not self.inClosed:
            return self.inSock
        else:
            return None
    def checkWrite(self):
        if len(self.buf) > 0 and now >= self.delaySendUntil:
            return self.outSock
        else:
            return None
    def doRecv(self):
        b = ""
        try:
            b = self.inSock.recv(self.bufCap - len(self.buf))
        except:
            self.conn.die()
        if len(b):
            self.buf += b
        else:
            self.inClosed = 1
        self.checkDone()
    def doSend(self):
        global now
        try:
            bufLen = len(self.buf)
            toSend = random.randrange(1, bufLen+1)
            if debug: print "attempting to send %d of %d" % (toSend, len(self.buf))
            n = self.outSock.send(self.buf[0:toSend])
            self.buf = self.buf[n:]
            if len(self.buf):
                self.delaySendUntil = now + 0.1
        except Exception as e:
            print e
            self.conn.die()
        self.checkDone()
    def checkDone(self):
        if len(self.buf) == 0 and self.inClosed:
            self.outSock.shutdown(SHUT_WR)
            self.conn.fwdDone(self)
            
    
connections = set()

class Conn:
    def __init__(self, csock, caddr, af, socktype, saddr):
        global nextConnectionNumber
        self.csock = csock      # to client
        self.caddr, self.saddr = caddr, saddr # addresses
        self.connIndex = connIndex = nextConnectionNumber
        nextConnectionNumber += 1
        self.ssock = ssock = socket(af, socktype)
        self.forwarders = forwarders = set()
        print "New connection #%d from %s" % (connIndex, repr(caddr))
        sockNames[csock] = "C%d:ToClient" % connIndex
        sockNames[ssock] = "C%d:ToServer" % connIndex
        ssock.setblocking(False)
        ssock.connect_ex(saddr)
        forwarders.add(Fwd(self, csock, ssock))
        forwarders.add(Fwd(self, ssock, csock))
        connections.add(self)
    def fwdDone(self, forwarder):
        forwarders = self.forwarders
        forwarders.remove(forwarder)
        print "forwarder %s ==> %s from connection %d shutting down" % (sockNames[forwarder.inSock], sockNames[forwarder.outSock], self.connIndex)
        if len(forwarders) == 0:
            self.die()
    def die(self):
        print "connection %d shutting down" % self.connIndex
        for s in self.ssock, self.csock:
            del sockNames[s]
            try:
                s.close()
            except:
                pass 
        connections.remove(self)
    def doErr(self):
        print "forwarder from client %s failing due to error" % repr(self.caddr)
        die()
                
class Listener:
    def __init__(self, bindaddr, saddr, addrFamily=AF_INET, socktype=SOCK_STREAM): # saddr is address of server
        self.bindaddr, self.saddr = bindaddr, saddr
        self.addrFamily, self.socktype = addrFamily, socktype
        self.lsock = lsock = socket(addrFamily, socktype)
        sockNames[lsock] = "listener"
        lsock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        lsock.bind(bindaddr)
        lsock.setblocking(False)
        lsock.listen(2)
    def doRecv(self):
        try:
            csock, caddr = self.lsock.accept() # socket connected to client
            conn = Conn(csock, caddr, self.addrFamily, self.socktype, self.saddr)
        except:
            print "weird.  listener readable but can't accept!"
            traceback.print_exc(file=sys.stdout)
    def doErr(self):
        print "listener socket failed!!!!!"
        sys.exit(2)

    def checkRead(self):
        return self.lsock
    def checkWrite(self):
        return None
    def checkErr(self):
        return self.lsock
        

l = Listener(("0.0.0.0", listenPort), (serverHost, serverPort))

def lookupSocknames(socks):
    return [ sockName(s) for s in socks ]

while 1:
    rmap,wmap,xmap = {},{},{}   # socket:object mappings for select
    xmap[l.checkErr()] = l
    rmap[l.checkRead()] = l
    now = time.time()
    nextDelayUntil = now + 10   # default 10s poll
    for conn in connections:
        for sock in conn.csock, conn.ssock:
            xmap[sock] = conn
            for fwd in conn.forwarders:
                sock = fwd.checkRead()
                if (sock): rmap[sock] = fwd
                sock = fwd.checkWrite()
                if (sock): wmap[sock] = fwd
                delayUntil = fwd.delaySendUntil
                if (delayUntil < nextDelayUntil and delayUntil > now): # minimum active delay
                    nextDelayUntil = delayUntil
    delay = nextDelayUntil - now
    if debug: print "delay=%f" % delay
    rset, wset, xset = select(rmap.keys(), wmap.keys(), xmap.keys(), delay)
    if debug: print [ repr([ sockNames[s] for s in sset]) for sset in [rset,wset,xset] ]
    for sock in rset:
        rmap[sock].doRecv()
    for sock in wset:
        wmap[sock].doSend()
    for sock in xset:
        xmap[sock].doErr()

    

