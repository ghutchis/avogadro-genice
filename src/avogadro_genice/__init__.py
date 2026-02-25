"""Avogadro plugin for generating ice structures using GenIce2."""

import argparse
import json
import sys


def main():
    # Avogadro calls the plugin as:
    #   avogadro-genice <identifier> [--lang <locale>] [--debug]
    # with the user options JSON on stdin.
    parser = argparse.ArgumentParser()
    parser.add_argument("feature")
    parser.add_argument("--lang", nargs="?", default="en")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    avo_input = json.load(sys.stdin)
    output = None

    match args.feature:
        case "genice":
            from .generator import run
            output = run(avo_input)

    if output is not None:
        print(json.dumps(output))
