"""Run an NVFlare simulation without terminal-error postprocessing."""

import argparse
import subprocess
import sys

from debugger import (
    build_simulator_command,
    configure_simulator_authorization,
    define_simulator_parser,
)


def run_simulator(simulator_args):
    """Run the NVFlare simulator with parsed command-line arguments."""
    configure_simulator_authorization(simulator_args.workspace)
    completed_process = subprocess.run(
        build_simulator_command(simulator_args),
        check=False,
    )
    return completed_process.returncode


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        raise RuntimeError("Please use Python 3.10 or above.")

    parser = argparse.ArgumentParser()
    define_simulator_parser(parser)
    args = parser.parse_args()
    status = run_simulator(args)
    sys.exit(status)
