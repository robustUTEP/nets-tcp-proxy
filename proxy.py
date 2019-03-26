#! /usr/bin/env python3
import re
from select import select
from socket import (AF_INET, SHUT_WR, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET,
                    socket)
import sys
import traceback

import params

switchesVarDefaults = (
    (('-l', '--listenPort'), 'listenPort', 50000),
    (('-s', '--server'), 'server', "127.0.0.1:50001"),
    (('-d', '--debug'), 'debug', False),  # boolean (set if present)
    (('-?', '--usage'), 'usage', False),  # boolean (set if present)
    )

paramMap = params.parseParams(switchesVarDefaults)
server = paramMap['server']
listenPort = paramMap['listenPort']
usage = paramMap['usage']
debug = paramMap['debug']

if usage:
    params.usage()

try:
    serverHost, serverPort = re.split(":", server)
    serverPort = int(serverPort)
except:
    print(f"Can't parse server:port from {server}")
    sys.exit(1)

try:
    listenPort = int(listenPort)
except:
    print(f"Can't parse listen port from {listenPort}")
    sys.exit(1)

sockNames = {}               # from socket to name
nextConnectionNumber = 0     # each connection is assigned a unique id


class Fwd:
    def __init__(self, conn, inSock, outSock, bufCap=1000):
        self.inSock, self.outSock = inSock, outSock
        self.conn, self.bufCap = conn, bufCap
        self.inClosed, self.buf = 0, b""

    def checkRead(self):
        if len(self.buf) < self.bufCap and not self.inClosed:
            return self.inSock
        else:
            return None

    def checkWrite(self):
        if len(self.buf) > 0:
            return self.outSock
        else:
            return None

    def doRecv(self):
        b = ""
        try:
            b = self.inSock.recv(self.bufCap - len(self.buf))
        except:
            self.conn.die()
        if len(b):              # read something
            self.buf += b
        else:                   # zero length read (input closed)
            self.inClosed = 1
        self.checkDone()

    def doSend(self):
        try:
            n = self.outSock.send(self.buf)
            self.buf = self.buf[n:]
        except:
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
        self.csock = csock  # to client
        self.caddr, self.saddr = caddr, saddr  # addresses
        self.connIndex = connIndex = nextConnectionNumber
        nextConnectionNumber += 1
        self.ssock = ssock = socket(af, socktype) # socket to connect to server
        self.forwarders = forwarders = set()
        print(f"New connection #{connIndex} from {caddr}")
        sockNames[csock] = f"ToClnt.{connIndex}"
        sockNames[ssock] = f"ToSrvr.{connIndex}"
        ssock.setblocking(False)
        ssock.connect_ex(saddr)  # start connecting
        forwarders.add(Fwd(self, csock, ssock))
        forwarders.add(Fwd(self, ssock, csock))
        connections.add(self)

    def fwdDone(self, forwarder):
        forwarders = self.forwarders
        forwarders.remove(forwarder)
        print(
            f"Forwarder {sockNames[forwarder.inSock]} ==>",
            f"{sockNames[forwarder.outSock]} from connection {self.connIndex}",
            "shutting down",
            )
        if len(forwarders) == 0:
            self.die()

    def die(self):
        print(f"Connection {self.connIndex} shutting down")
        for s in self.ssock, self.csock:
            del sockNames[s]
            try:
                s.close()
            except Exception as e:
                print(f"close exception {e}")
                pass
        connections.remove(self)

    def doErr(self):
        print(f"Forwarder from client {self.caddr} failing due to error")
        self.die()


class Listener:
    def __init__(self, bindaddr, saddr, addrFamily=AF_INET,
                 socktype=SOCK_STREAM):  # saddr is address of server
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
            csock, caddr = self.lsock.accept()  # socket connected to client
            Conn(csock, caddr, self.addrFamily, self.socktype, self.saddr)
        except:
            print("Weird, listener readable but can't accept!")
            traceback.print_exc(file=sys.stdout)

    def doErr(self):
        print("Listener socket failed!")
        sys.exit(2)

    def checkRead(self):
        return self.lsock

    def checkWrite(self):
        return None

    def checkErr(self):
        return self.lsock


l = Listener(("0.0.0.0", listenPort), (serverHost, serverPort))


def lookupSocknames(socks):
    return [sockNames[s] for s in socks]

while 1:
    rmap, wmap, xmap = {}, {}, {}   # socket:object mappings for select
    xmap[l.checkErr()] = l
    rmap[l.checkRead()] = l
    for conn in connections:
        for sock in conn.csock, conn.ssock:
            xmap[sock] = conn
            for fwd in conn.forwarders:
                sock = fwd.checkRead()
                if (sock):
                    rmap[sock] = fwd
                sock = fwd.checkWrite()
                if (sock):
                    wmap[sock] = fwd
    rset, wset, xset = select(list(rmap.keys()), list(wmap.keys()),
                              list(xmap.keys()), 60)
    # print "select r=%s, w=%s, x=%s" %
    if debug:
        print(
            "ready sockets: ",
            [[sockNames[s] for s in sset] for sset in [rset, wset, xset]]
            )
    for sock in rset:
        rmap[sock].doRecv()
    for sock in wset:
        wmap[sock].doSend()
    for sock in xset:
        xmap[sock].doErr()
