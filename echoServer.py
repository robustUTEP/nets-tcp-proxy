#! /usr/bin/env python3
import re
from select import select
from socket import (AF_INET, SHUT_WR, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET,
                    socket)
import sys
import traceback

import params

switchesVarDefaults = (
    (('-l', '--listenPort'), 'listenPort', 50001),
    (('-d', '--debug'), 'debug', False),  # boolean (set if present)
    (('-?', '--usage'), 'usage', False),  # boolean (set if present)
    )

paramMap = params.parseParams(switchesVarDefaults)
listenPort = paramMap['listenPort']
usage = paramMap['usage']
debug = paramMap['debug']

if usage:
    params.usage()

try:
    listenPort = int(listenPort)
except:
    print(f"Can't parse listen port from {listenPort}")
    sys.exit(1)

sockNames = {}            # from socket to name
nextConnectionNumber = 0  # each connection is assigned a unique id


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
        b = b""
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
        try:
            n = self.outSock.send(self.buf)
            self.buf = self.buf[n:]
        except:
            self.conn.die()
        self.checkDone()

    def checkDone(self):
        if len(self.buf) == 0 and self.inClosed:
            try:
                self.outSock.shutdown(SHUT_WR)
            except:
                pass
            self.conn.fwdDone(self)


connections = set()


class Conn:
    def __init__(self, csock, caddr):
        global nextConnectionNumber
        self.csock = csock      # to client
        self.caddr = caddr
        self.connIndex = connIndex = nextConnectionNumber
        nextConnectionNumber += 1
        self.forwarders = forwarders = set()
        sockName = sockNames[csock] = f"S.{connIndex}"
        print(f"New connection {sockName} from {caddr}")
        forwarders.add(Fwd(self, csock, csock))
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
        del sockNames[self.csock]
        try:
            self.csock.close()
        except:
            pass
        connections.remove(self)

    def doErr(self):
        print(f"Forwarder from client {self.caddr} failing due to error")
        self.die()


class Listener:                 # a listener socket is a factory for established connections
    def __init__(self, bindaddr, addrFamily=AF_INET, socktype=SOCK_STREAM):
        self.bindaddr = bindaddr
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
            Conn(csock, caddr)
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


l = Listener(("0.0.0.0", listenPort))

while 1:
    rmap, wmap, xmap = {}, {}, {}  # socket:object mappings for select
    xmap[l.checkErr()] = l
    rmap[l.checkRead()] = l
    for conn in connections:
        for sock in [conn.csock]:
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
