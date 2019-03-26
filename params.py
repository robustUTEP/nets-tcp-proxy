import re
import sys

progName = "()"
if sys.argv:
    progName = sys.argv.pop(0)

switchesVarDefaults = ()


def parseParams(_switchesVarDefaults):
    global switchesVarDefaults
    paramMap = {}
    switchesVarDefaults = _switchesVarDefaults
    swVarDefaultMap = {}  # map from cmd switch to param var name
    for switches, param, default in switchesVarDefaults:
        for sw in switches:
            swVarDefaultMap[sw] = (param, default)
        paramMap[param] = default  # set default values
    try:
        while sys.argv:
            sw = sys.argv.pop(0)
            paramVar, defaultVal = swVarDefaultMap[sw]
            if (defaultVal):
                val = sys.argv.pop(0)
                paramMap[paramVar] = val
            else:
                paramMap[paramVar] = True
    except Exception as e:
        print(f"Problem parsing parameters: {e}")
        usage()
    return paramMap


def usage():
    print("%s usage:" % progName)
    for switches, param, default in switchesVarDefaults:
        for sw in switches:
            if default:
                print(f" [{sw} {param}]   (default = {default})")
            else:
                print(f" [{sw}]   ({param} if present)")
    sys.exit(1)
