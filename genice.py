#  This source file is part of the Avogadro project
#  This source code is released under the 3-Clause BSD License, (see "LICENSE").
#  https://github.com/ghutchis/avogadro-genice/


import argparse
import json
import sys

from genice2.genice import GenIce
from genice2.plugin import Lattice, Format, Molecule

def getOptions():
    userOptions = {}

    userOptions['a'] = {
        'type' : 'integer',
        'default': 2,
        'minimum': 2,
        'label': 'A Repeats'
    }

    userOptions['b'] = {
        'type' : 'integer',
        'default': 2,
        'minimum': 2,
        'label': 'B Repeats'
    }

    userOptions['c'] = {
        'type' : 'integer',
        'default': 2,
        'minimum': 2,
        'label': 'C Repeats'
    }

    userOptions['lattice'] = {
        'type': 'stringList',
        'default': 0,
        'values': ['1h', '1c', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']
    }

    userOptions['model'] = {
        'type': 'stringList',
        'default': 0,
        'values': ['tip3p', 'tip4p', 'tip5p', 'spce', 'physical']
    }

    userOptions['seed'] = {
        'type' : 'integer',
        'default': 12345,
        'maximum': 65530,
        'label': 'Random Seed'
    }

    opts = {'userOptions': userOptions}
    return opts


def runCommand():
    # Read options from stdin
    stdinStr = sys.stdin.read()

    # Parse the JSON strings
    opts = json.loads(stdinStr)

    lattice = Lattice(opts['lattice']) 
    formatter = Format('cif') # adds periodic vectors
    water = Molecule(opts['model'])

    a = int(opts['a'])
    b = int(opts['b'])
    c = int(opts['c'])
    s = int(opts['seed'])
    ice = GenIce(lattice, rep=(a,b,c), seed=s).generate_ice(formatter, water=water)

    # Append the ice
    result = {}
    result['moleculeFormat'] = 'cif'
    result['cif'] = ice

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser('Genice')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--print-options', action='store_true')
    parser.add_argument('--run-command', action='store_true')
    parser.add_argument('--display-name', action='store_true')
    parser.add_argument('--menu-path', action='store_true')
    parser.add_argument('--lang', nargs='?', default='en')
    args = vars(parser.parse_args())

    debug = args['debug']

    if args['display_name']:
        print("Generate Ice...")
    if args['menu_path']:
        print("&Build")
    if args['print_options']:
        print(json.dumps(getOptions()))
    elif args['run_command']:
        print(json.dumps(runCommand()))
