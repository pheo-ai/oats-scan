"""Command line entry point for oats-scan.

oats-scan is `oats scan` from pheo-oats under its old name: the same
scanner, so the two print the same numbers, with the flags, defaults and
exit codes oats-scan has always had (0 clean, 1 when --strict finds
something that needs review, 2 when the scan could not run, 130 on
Ctrl-C).
"""
import argparse
import os
import sys

from oats_scan import __version__
from oats_scan.gateway import ScanError


def build_parser():
    parser = argparse.ArgumentParser(
        prog="oats-scan",
        description=(
            "Show what the agent skills on this machine instruct an AI agent "
            "to run, sorted by what kind of effect each command has. The same "
            "scanner as `oats scan` in pheo-oats."
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
    # OATS_SCAN_BIN_DIR keeps pointing the scan at its binaries, now that
    # they are pheo-oats' and pheo-oats looks for PHEO_OATS_BIN_DIR.
    if os.environ.get("OATS_SCAN_BIN_DIR") and not os.environ.get("PHEO_OATS_BIN_DIR"):
        os.environ["PHEO_OATS_BIN_DIR"] = os.environ["OATS_SCAN_BIN_DIR"]
    try:
        from pheo_oats.cli import OatsError
    except ImportError:  # no pheo-oats: importing the scan says so
        OatsError = ScanError

    try:
        from oats_scan.scan import run

        return run(args)
    except (ScanError, OatsError) as error:
        print("\n{}".format(error), file=sys.stderr)
        return 2
    except SystemExit as error:
        # pheo-oats reports a missing binary, or a classifier that would not
        # start, as SystemExit with a sentence. Here that is exit status 2,
        # which --strict never uses, so CI can tell "could not scan" from
        # "found something".
        if isinstance(error.code, str):
            print("\n{}".format(error.code), file=sys.stderr)
            return 2
        raise
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
