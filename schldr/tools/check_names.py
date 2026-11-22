#!/usr/bin/env python3
"""Fail when a name of the roofing application Schldr was forked from is left.

    python3 tools/check_names.py

Looks through every text file of the addons for the words below. The tools
themselves and the README (which tell where the code comes from) are exempt.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN = re.compile(r"tectora|roof|\bdak|epdm|skylux", re.IGNORECASE)
TEXT_SUFFIXES = {
    ".py", ".xml", ".js", ".scss", ".css", ".csv", ".md", ".svg", ".txt", ".json", ".po",
}


def main():
    hits = 0
    for module in sorted(ROOT.glob("schldr_*")):
        for path in sorted(module.rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line):
                    hits += 1
                    print("%s:%d: %s" % (path.relative_to(ROOT), number, line.strip()[:120]))
    if hits:
        sys.exit("%d line(s) still name the roofing application" % hits)
    print("No roofing names left.")


if __name__ == "__main__":
    main()
