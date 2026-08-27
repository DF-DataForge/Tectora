#!/usr/bin/env python3
"""Turn a Stuklijst export (.xlsx) into the JSON the module ships.

The module loads ``data/bom_catalog.json`` on install and on upgrade, the same
way tectora_products loads its product catalogue. Regenerate it whenever
Tectora sends a new export:

    python tools/parse_bom_export.py Stuklijst_Tectora.xlsx

The parsing itself lives in ``models/bom_rules.py`` so the module and this tool
cannot drift apart.
"""
import argparse
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Loaded by path: importing the models package would pull in mrp_bom, which
# needs Odoo, and this tool runs standalone.
_spec = importlib.util.spec_from_file_location(
    "bom_rules", os.path.join(HERE, "..", "models", "bom_rules.py")
)
bom_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bom_rules)

DEFAULT_OUT = os.path.join(HERE, "..", "data", "bom_catalog.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", help="Stuklijst_Tectora.xlsx")
    parser.add_argument("-o", "--out", default=DEFAULT_OUT)
    parser.add_argument("--sheet", default=None)
    args = parser.parse_args()

    import openpyxl

    workbook = openpyxl.load_workbook(args.export, data_only=True, read_only=True)
    sheet = workbook[args.sheet] if args.sheet else workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    if len(rows) < 2:
        raise SystemExit("Het tabblad bevat geen gegevens.")
    boms = bom_rules.parse_export(rows[1:])
    if not boms:
        raise SystemExit("Geen stuklijsten gevonden in %s." % args.export)

    data = {
        "source": os.path.basename(args.export),
        "boms": boms,
        "stats": {
            "boms": len(boms),
            "lines": sum(len(b["lines"]) for b in boms),
            "products": len({b["product"] for b in boms}),
            "components": len(
                {line["component"] for b in boms for line in b["lines"]}
            ),
        },
    }
    out = os.path.abspath(args.out)
    with open(out, "w") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    print(
        "%(boms)s stuklijsten, %(lines)s regels, %(products)s producten, "
        "%(components)s componenten" % data["stats"]
    )
    print("geschreven: %s" % out)


if __name__ == "__main__":
    main()
