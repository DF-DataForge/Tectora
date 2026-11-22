#!/usr/bin/env python3
"""Port a Tectora addon to its Schldr name.

Schldr started as a fork of the Tectora addons (DF-DataForge/Tectora, commit
f9e8309). This script does the mechanical part of that fork: it copies a
module, renames files and identifiers with one ordered replace map, resets the
version and drops the migrations (Schldr starts on an empty database).

    python3 tools/port_from_tectora.py <tectora checkout> <module> [--only PATH ...]

What it cannot do is the domain work: anything about roofs that is left in the
result is reported by ``tools/check_names.py`` and has to be rewritten by hand.
The script refuses to overwrite a module that already exists, so hand-made
changes are never lost; pass ``--only`` to bring over single files later.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODULES = {
    "tectora_roof": "schldr_paint",
    "tectora_portal": "schldr_portal",
    "tectora_report_layout": "schldr_report_layout",
    "tectora_quote_builder": "schldr_quote_builder",
    "tectora_contact_type": "schldr_contact_type",
}

# Ordered: the first match wins, so the longer names come first.
REPLACEMENTS = [
    # layout: the roof edge becomes a neutral accent edge (before the modules:
    # "tectora_roof_letterhead" is not the module tectora_roof)
    ("roof_letterhead", "accent_letterhead"),
    ("met dakrand", "met accentrand"),
    ("Schldr-dakrand", "accentrand"),
    ("dakrandband", "lichte band"),
    ("dakrand", "accentrand"),
    ("roof-edge", "accent-edge"),
    ("roof edge", "accent edge"),
    ("roof line", "accent line"),
    ("roof's peak", "peak"),
    # modules
    *MODULES.items(),
    # models
    ("tectora.roof.project", "schldr.project"),
    ("tectora.roof.", "schldr."),
    ("tectora_roof_project", "schldr_project"),
    # fields, variables, files
    ("roof_project_ids", "schldr_project_ids"),
    ("roof_project_id", "schldr_project_id"),
    ("roof_project_info", "schldr_project_info"),
    ("roof_project", "schldr_project"),
    ("RoofProject", "SchldrProject"),
    ("roof_material", "schldr_material"),
    ("RoofMaterial", "SchldrMaterial"),
    ("roof_team", "schldr_team"),
    ("RoofTeam", "SchldrTeam"),
    ("roof_planning", "schldr_work_block"),
    ("RoofPlanning", "SchldrWorkBlock"),
    ("roof_measurement_line", "schldr_measurement_line"),
    ("roof_line_id", "schldr_line_id"),
    ("roof_form", "schldr_form"),
    # wording: the roofing project becomes a painting project
    ("dakprojecten", "schilderprojecten"),
    ("Dakprojecten", "Schilderprojecten"),
    ("dakproject", "schilderproject"),
    ("Dakproject", "Schilderproject"),
    ("Roof project", "Painting project"),
    ("roof project", "painting project"),
    ("roof measurement", "measurement"),
    ("Tectora Dakmeting", "Schldr"),
    ("Data Forge Dakmeting", "Data Forge Schldr"),
    ("dakmeting", "opmeting"),
    ("Dakmeting", "Schilderwerk"),
    ("dakplannen", "plannen"),
    ("Dakplannen", "Plannen"),
    ("dakplan", "plan"),
    ("Dakplan", "Plan"),
    ("DAK/", "SCH/"),
    # brand
    ("tectora.be", "schldr.be"),
    ("TECTORA", "SCHLDR"),
    ("Tectora", "Schldr"),
    ("tectora", "schldr"),
    # colours: Tectora teal -> Schldr blue (placeholder until the brand is set)
    ("#008B93", "#2F5D8A"),
    ("#008b93", "#2f5d8a"),
    ("#2D8D8F", "#3A6A99"),
    ("#2d8d8f", "#3a6a99"),
]

TEXT_SUFFIXES = {
    ".py", ".xml", ".js", ".scss", ".css", ".csv", ".md", ".svg", ".txt", ".json", ".po",
}
SKIP_DIRS = {"migrations", "__pycache__"}
VERSION = re.compile(r'("version"\s*:\s*")[^"]+(")')


def rename(text):
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    return text


def port_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix not in TEXT_SUFFIXES:
        shutil.copyfile(source, target)
        return
    text = rename(source.read_text(encoding="utf-8"))
    if source.name == "__manifest__.py":
        text = VERSION.sub(r"\g<1>20.0.1.0.0\g<2>", text)
    target.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("tectora", type=Path, help="checkout of DF-DataForge/Tectora")
    parser.add_argument("module", choices=sorted(MODULES))
    parser.add_argument(
        "--only", nargs="+", metavar="PATH", default=[],
        help="port only these files (paths inside the Tectora module)",
    )
    args = parser.parse_args()

    source_root = args.tectora / args.module
    target_root = ROOT / MODULES[args.module]
    if not source_root.is_dir():
        sys.exit("No such module: %s" % source_root)
    if target_root.exists() and not args.only:
        sys.exit("%s exists already; use --only to port single files" % target_root.name)

    if args.only:
        sources = [source_root / path for path in args.only]
    else:
        sources = [
            path for path in sorted(source_root.rglob("*"))
            if path.is_file() and not SKIP_DIRS & set(path.relative_to(source_root).parts)
        ]
    for source in sources:
        relative = Path(rename(str(source.relative_to(source_root))))
        target = target_root / relative
        if target.exists():
            sys.exit("%s exists already" % target.relative_to(ROOT))
        port_file(source, target)
        print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
