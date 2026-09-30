"""The scanner, which is pheo-oats' `oats scan`.

oats-scan used to carry its own copy of the extraction and its own list of
classes. One scanner means one set of numbers, so both now come from
pheo-oats, and this module keeps the names oats_scan.scan offered so code
that imported them still works.

Prose is ignored. "This skill can delete your notes" is a sentence, not an
action. Only fenced shell content counts, which is why the numbers are a
floor rather than an estimate.
"""
import argparse

from oats_scan.gateway import ScanError

try:
    from pheo_oats.scan import (  # noqa: F401  (re-exported)
        COMMAND_START,
        DATA,
        INSTALLED_SKILL_DIRS,
        INSTRUCTION_NAMES,
        MAX_FILES,
        SEP,
        SHELL_LANGS,
        SKIP_DIRS,
        collect,
        fenced_blocks,
        installed_skill_roots,
        instruction_files,
    )
except ImportError as error:
    raise ScanError(
        "oats-scan runs pheo-oats' scanner and needs pheo-oats 0.7.1 or newer "
        "({}). pip install --upgrade oats-scan".format(error)
    ) from None


def run(args):
    """Scan as `oats scan` does, with oats-scan's arguments.

    Every oats-scan flag has the same meaning there. `oats scan` also takes
    --port, to reuse a running gateway; oats-scan always starts its own.
    """
    from pheo_oats.scan import scan

    return scan(argparse.Namespace(
        path=args.path,
        files=args.files,
        json=args.json,
        strict=args.strict,
        workers=args.workers,
        port=0,
    ))
