import random
import sys
import traceback
from select import *
from socket import *

sockNames = {}               # from socket to name
nextClientNumber = 0     # each client is assigned a unique id
debug = 0
            
    
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
        print "New client #%d to %s" % (clientIndex, repr(saddr))
        sockNames[ssock] = "C%d:ToServer" % clientIndex
        ssock.setblocking(False)
        ssock.connect_ex(saddr)
        liveClients.add(self)
    def doSend(self):
        self.numSent += self.ssock.send("a"*random.randrange(1,2048))
        if random.randrange(0,200) == 0:
            self.allSent = 1
            self.ssock.shutdown(SHUT_WR)
    def doRecv(self):
        n = len(self.ssock.recv(1024))
        self.numRecv += n
        if self.numRecv > self.numSent: 
            self.error("sent=%d < recd=%d" %  (self.numSent, self.numRecv))
        if n != 0:
            return
        if debug: print "client %d: zero length read" % self.clientIndex
        # zero length read (done)
        if self.numRecv == self.numSent:
            self.done()
        else:
            self.error("sent=%d but recd=%d" %  (self.numSent, self.numRecv))
    def doErr(self):
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
        try:
            self.ssock(close)
        except:
            pass
        print "client %d done (error=%d)" % (self.clientIndex, self.error)
        deadClients.add(self)
        liveClients.remove(self)
       
    def error(self, msg):
        self.allSent =1
        self.error = 1
        print "FAILURE client %d: %s" % (self.clientIndex, msg)
        self.done()
        
                  
def lookupSocknames(socks):
    return [ sockName(s) for s in socks ]

for i in range(4):
    liveClients.add(Client(AF_INET, SOCK_STREAM, ("localhost", 50000)))


while len(liveClients):
    rmap,wmap,xmap = {},{},{}   # socket:object mappings for select
    for client in liveClients:
        sock = client.checkRead()
        if (sock): rmap[sock] = client
        sock = client.checkWrite()
        if (sock): wmap[sock] = client
        xmap[client.ssock] = client
    if debug: print "select params (r,w,x):", [ repr([ sockNames[s] for s in sset] ) for sset in [rmap.keys(), wmap.keys(), xmap.keys()] ]
    rset, wset, xset = select(rmap.keys(), wmap.keys(), xmap.keys(),60)
    #print "select r=%s, w=%s, x=%s" %
    if debug: print "select returned (r,w,x):", [ repr([ sockNames[s] for s in sset] ) for sset in [rset,wset,xset] ]
    for sock in rset:
        rmap[sock].doRecv()
    for sock in wset:
        wmap[sock].doSend()
    for sock in xset:
        xmap[sock].doErr()

numFailed = 0
for client in deadClients:
    err = client.error
    print "Client %d Succeeded=%s, Bytes sent=%d, rec'd=%d" % (client.clientIndex, not err, client.numSent, client.numRecv)
    if err:
        numFailed += 1
print "%d Clients failed." % numFailed

