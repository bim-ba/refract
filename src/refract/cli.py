"""The ``refract`` console-script entry point — ``refract generate [--write|--check]``.

Renders every resource under ``examples/ycli-tracker/**/resource.yaml`` via
:mod:`refract.generate` into ``examples/ycli-tracker/out/``. With no flag, prints the render plan
without touching disk; ``--write`` (re)writes the rendered files; ``--check`` is the drift gate —
it exits 1 if the committed ``out/`` tree has diverged from the specs, 0 if it's up to date.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from refract.generate import check, plan, write
from refract.loader import SpecError

_EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples" / "ycli-tracker"
_SPECS_DIR = _EXAMPLES
_OUT_DIR = _EXAMPLES / "out"


def main(argv: list[str] | None = None) -> int:
    """Parse ``argv`` and run the ``generate`` subcommand; returns the process exit code."""
    parser = argparse.ArgumentParser(prog="refract", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate", help="render examples/ycli-tracker specs into out/"
    )
    group = generate_parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="write the rendered files to out/")
    group.add_argument("--check", action="store_true", help="exit 1 if any out/ file is stale")

    args = parser.parse_args(argv)

    try:
        the_plan = plan(_SPECS_DIR, _OUT_DIR)
    except SpecError as error:
        print(f"spec error: {error}", file=sys.stderr)
        return 2

    if args.write:
        write(the_plan)
        print(f"wrote {len(the_plan)} files.")
        return 0
    if args.check:
        return check(the_plan)

    for path in the_plan:
        print(f"would render {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
