"""Command line entry point for oats-scan."""
import argparse
import sys

from oats_scan import __version__
from oats_scan.gateway import ScanError


def build_parser():
    parser = argparse.ArgumentParser(
        prog="oats-scan",
        description=(
            "Show what the agent skills on this machine instruct an AI agent "
            "to run, sorted by what kind of effect each command has."
        ),
        epilog=(
            "examples:\n"
            "\n"
            "    oats-scan                 # skills installed on this machine\n"
            "    oats-scan --files         # and which file each one came from\n"
            "    oats-scan ~/my-project    # a specific directory\n"
            "    oats-scan --json          # machine readable\n"
            "\n"
            "Nothing is installed, nothing is changed, and nothing leaves\n"
            "this machine.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path", nargs="?", default=None,
        help="Directory to scan. Default: agent skills installed on this "
             "machine, plus the current directory.",
    )
    parser.add_argument("--files", action="store_true",
                        help="List which files carry the actions worth reviewing")
    parser.add_argument("--json", action="store_true", help="Machine readable output")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if anything needs review, for CI")
    parser.add_argument("--workers", type=int, default=8,
                        help="Parallel classifications (default 8)")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    from oats_scan.scan import run

    try:
        return run(args)
    except ScanError as error:
        print("\n{}".format(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
