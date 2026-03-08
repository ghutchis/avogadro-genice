#  This source file is part of the Avogadro project
#  This source code is released under the 3-Clause BSD License, (see "LICENSE").
#  https://github.com/ghutchis/avogadro-genice/

import warnings

import numpy as np
from genice2.genice import GenIce
from genice2.plugin import Lattice, Format, Molecule


def generate(opts):
    options = opts.get("options", {})

    lattice = Lattice(options['lattice'])
    formatter = Format('cif')  # adds periodic vectors
    water = Molecule(options['model'])

    np.random.seed(options['seed'])

    a = int(options['a'])
    b = int(options['b'])
    c = int(options['c'])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ice = GenIce(lattice, rep=(a, b, c)).generate_ice(formatter, water=water)

    return ice


def run(avo_input):
    return {
        'moleculeFormat': 'cif',
        'cif': generate(avo_input),
    }
