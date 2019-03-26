import random
import re
from select import select
from socket import AF_INET, SHUT_WR, SOCK_STREAM, socket
import sys
import traceback

import params

switchesVarDefaults = (
    (('-s', '--server'), 'server', "127.0.0.1:50000"),
    (('-n', '--numClients'), 'numClients', "4"),
    (('-d', '--debug'), 'debug', False),  # boolean (set if present)
    (('-?', '--usage'), 'usage', False),  # boolean (set if present)
    )

paramMap = params.parseParams(switchesVarDefaults)
server, usage, debug = paramMap['server'], paramMap['usage'], paramMap['debug']
numClients = int(paramMap['numClients'])

if usage:
    params.usage()

try:
    serverHost, serverPort = re.split(":", server)
    serverPort = int(serverPort)
except:
    print(f"Can't parse server:port from {repr(server)}")
    sys.exit(1)


sockNames = {}        # from socket to name
nextClientNumber = 0  # each client is assigned a unique id


liveClients, deadClients = set(), set()


class Client:
    def __init__(self, af, socktype, saddr):
        global nextClientNumber
        global liveClients, deadClients
        self.saddr = saddr  # addresses
        self.numSent, self.numRecv = 0, 0
        self.allSent = 0
        self.error = 0
        self.isDone = 0
        self.clientIndex = clientIndex = nextClientNumber
        nextClientNumber += 1
        self.ssock = ssock = socket(af, socktype)
        print(f"New client #{clientIndex} to {saddr}")
        sockNames[ssock] = f"C{clientIndex}:ToServer"
        ssock.setblocking(False)
        ssock.connect_ex(saddr)
        liveClients.add(self)

    def doSend(self):
        try:
            self.numSent += self.ssock.send(b"a" * random.randrange(1, 2048))
        except Exception as e:
            self.errorAbort(f"Can't send: {e}")
            return
        if random.randrange(0, 200) == 0:
            self.allSent = 1
            self.ssock.shutdown(SHUT_WR)

    def doRecv(self):
        try:
            n = len(self.ssock.recv(1024))
        except Exception as e:
            print(f"doRecv on dead socket: {e}")
            self.done()
            return
        self.numRecv += n
        if self.numRecv > self.numSent:
            self.errorAbort(f"sent={self.numSent} < recd={self.numRecv}")
        if n != 0:
            return
        if debug:
            print(f"Client {self.clientIndex}: zero length read")
        # zero length read (done)
        if self.numRecv == self.numSent:
            self.done()
        else:
            self.errorAbort(f"sent={self.numSent} but recd={self.numRecv}")

    def doErr(self):
        self.errorAbort("Socket error")

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
        self.allSent = 1
        if self.numSent != self.numRecv:
            self.error = 1
        try:
            self.ssock.close()
        except:
            pass
        print(f"Client {self.clientIndex} done (error={self.error})")
        deadClients.add(self)
        try:
            liveClients.remove(self)
        except:
            pass

    def errorAbort(self, msg):
        self.allSent = 1
        self.error = 1
        print(f"FAILURE client {self.clientIndex}: {msg}")
        self.done()


def lookupSocknames(socks):
    return [sockNames[s] for s in socks]

for i in range(numClients):
    liveClients.add(Client(AF_INET, SOCK_STREAM, (serverHost, serverPort)))


while len(liveClients):
    rmap, wmap, xmap = {}, {}, {}  # socket:object mappings for select
    for client in liveClients:
        sock = client.checkRead()
        if (sock):
            rmap[sock] = client
        sock = client.checkWrite()
        if (sock):
            wmap[sock] = client
        xmap[client.ssock] = client
    if debug:
        print(
            "select params (r,w,x):",
            [repr([sockNames[s] for s in sset]) for sset in [
                list(rmap.keys()),
                list(wmap.keys()),
                list(xmap.keys()),
                ]],
            )
    rset, wset, xset = select(list(rmap.keys()), list(wmap.keys()),
                              list(xmap.keys()), 60)
    if debug:
        print(
            "select returned (r,w,x):",
            [repr([sockNames[s] for s in sset]) for sset in [rset, wset, xset]]
            )
    for sock in xset:
        xmap[sock].doErr()
    for sock in rset:
        rmap[sock].doRecv()
    for sock in wset:
        wmap[sock].doSend()


numFailed = 0
for client in deadClients:
    err = client.error
    print(
        f"Client {client.clientIndex} Succeeded={not err},",
        f"Bytes sent={client.numSent}, rec'd={client.numRecv}",
        )
    if err:
        numFailed += 1
print(f"{numFailed} Clients failed.")
