import random
import sys
import traceback
from select import *
from socket import *

import re
import params

switchesVarDefaults = (
    (('-s', '--server'), 'server', "127.0.0.1:50000"),
    (('-n', '--numClients'), 'numClients', "4"),
    (('-d', '--debug'), "debug", False), # boolean (set if present)
    (('-?', '--usage'), "usage", False) # boolean (set if present)
    )

paramMap = params.parseParams(switchesVarDefaults)
server, usage, debug = paramMap["server"], paramMap["usage"], paramMap["debug"]
numClients = int(paramMap["numClients"])


if usage:
    params.usage()

try:
    serverHost, serverPort = re.split(":", server)
    serverPort = int(serverPort)
except:
    print("Can't parse server:port from '%s'" % server)
    sys.exit(1)


sockNames = {}               # from socket to name
nextClientNumber = 0     # each client is assigned a unique id



liveClients, deadClients = set(), set()

class Client:
    def __init__(self, af, socktype, saddr):
        global nextClientNumber
        global liveClients, deadClients
        self.saddr = saddr # addresses
        self.numSent, self.numRecv = 0,0
        self.allSent = 0
        self.error = 0
        self.isDone = 0
        self.clientIndex = clientIndex = nextClientNumber
        nextClientNumber += 1
        self.ssock = ssock = socket(af, socktype)
        print("New client #%d to %s" % (clientIndex, repr(saddr)))
        sockNames[ssock] = "C%d:ToServer" % clientIndex
        ssock.setblocking(False)
        ssock.connect_ex(saddr)
        liveClients.add(self)
    def doSend(self):
        try:
            bytesToSend = ("a"* random.randrange(1,2048)).encode()
            self.numSent += self.ssock.send(bytesToSend)
        except Exception as e:
            self.errorAbort("can't send: %s" % e)
            return
        if random.randrange(0,200) == 0:
            self.allSent = 1
            self.ssock.shutdown(SHUT_WR)
    def doRecv(self):
        try:
            n = len(self.ssock.recv(1024))
        except Exception as e:
            print("doRecv on dead socket")
            print(e)
            self.done()
            return
        self.numRecv += n
        if self.numRecv > self.numSent:
            self.errorAbort("sent=%d < recd=%d" %  (self.numSent, self.numRecv))
        if n != 0:
            return
        if debug: print("client %d: zero length read" % self.clientIndex)
        # zero length read (done)
        if self.numRecv == self.numSent:
            self.done()
        else:
            self.errorAbort("sent=%d but recd=%d" %  (self.numSent, self.numRecv))
    def doErr(self, msg=""):
        error("socket error")
    def checkWrite(self):
        if self.allSent:
            return None
        else:
            return self.ssock
    def checkRead(self):
        if self.isDone:
            return None
        else:
            return self.ssock
    def done(self):
        self.isDone = 1
        self.allSent =1
        if self.numSent != self.numRecv: self.error = 1
        try:
            self.ssock.close()
        except:
            pass
        print("client %d done (error=%d)" % (self.clientIndex, self.error))
        deadClients.add(self)
        try: liveClients.remove(self)
        except: pass

    def errorAbort(self, msg):
        self.allSent =1
        self.error = 1
        print("FAILURE client %d: %s" % (self.clientIndex, msg))
        self.done()


def lookupSocknames(socks):
    return [ sockNames[s] for s in socks ]

for i in range(numClients):
    liveClients.add(Client(AF_INET, SOCK_STREAM, (serverHost, serverPort)))


while len(liveClients):
    rmap,wmap,xmap = {},{},{}   # socket:object mappings for select
    for client in liveClients:
        sock = client.checkRead()
        if (sock): rmap[sock] = client
        sock = client.checkWrite()
        if (sock): wmap[sock] = client
        xmap[client.ssock] = client
    if debug: print("select params (r,w,x):", [ repr([ sockNames[s] for s in sset] ) for sset in [list(rmap.keys()), list(wmap.keys()), list(xmap.keys())] ])
    rset, wset, xset = select(list(rmap.keys()), list(wmap.keys()), list(xmap.keys()),60)
    #print "select r=%s, w=%s, x=%s" %
    if debug: print("select returned (r,w,x):", [ repr([ sockNames[s] for s in sset] ) for sset in [rset,wset,xset] ])
    for sock in xset:
        xmap[sock].doErr()
    for sock in rset:
        rmap[sock].doRecv()
    for sock in wset:
        wmap[sock].doSend()


numFailed = 0
for client in deadClients:
    err = client.error
    print("Client %d Succeeded=%s, Bytes sent=%d, rec'd=%d" % (client.clientIndex, not err, client.numSent, client.numRecv))
    if err:
        numFailed += 1
print("%d Clients failed." % numFailed)
