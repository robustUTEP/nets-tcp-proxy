from sys import argv
import sys, re

progName = "()"
if len(argv):
    progName = argv[0]
    del argv[0]

switchesVarDefaults = ()

def parseParams(_switchesVarDefaults):
    global switchesVarDefaults
    paramMap = {}
    switchesVarDefaults = _switchesVarDefaults
    swVarDefaultMap = {}       # map from cmd switch to param var name
    for switches, param, default in switchesVarDefaults:
        for sw in switches:
            swVarDefaultMap[sw] = (param, default)
        paramMap[param] = default # set default values
    try:
        while len(argv):
            sw = argv[0]; del argv[0]
            paramVar, defaultVal = swVarDefaultMap[sw]
            if (defaultVal):
                val = argv[0]; del argv[0]
                paramMap[paramVar] = val
            else:
                paramMap[paramVar] = True
    except Exception as e:
        print "Problem parsing parameters (exception=%s)" % e
        usage()
    return paramMap
        
def usage():
    print "%s usage:" % progName
    for switches, param, default in switchesVarDefaults:
        for sw in switches:
            if default:
                print " [%s %s]   (default = %s)" % (sw, param, default)
            else:
                print " [%s]   (%s if present)" % (sw, param)
    sys.exit(1)

