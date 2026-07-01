"""Unified entrypoint for demo and sample data generators."""

import argparse
import importlib
import os
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


COMMANDS = {
    'sample-contracts': ('scripts.generate_sample_contracts', 'main'),
    'demo-flow': ('demo_flow_data', 'main'),
}


def run(command):
    module_name, func_name = COMMANDS[command]
    module = importlib.import_module(module_name)
    return getattr(module, func_name)()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run demo/sample data generators.')
    parser.add_argument('command', choices=sorted(COMMANDS))
    args = parser.parse_args(argv)
    return run(args.command)


if __name__ == '__main__':
    raise SystemExit(main())
