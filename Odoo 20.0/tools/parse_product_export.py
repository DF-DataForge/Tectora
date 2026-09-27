#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the shipped product catalogue from a supplier export.

Usage:
    python3 tools/parse_product_export.py <producten_export.xlsx> [output.json]

Offline counterpart of the in-app "Catalogus importeren" wizard: both use the
classification and normalisation rules in
``tectora_products/models/catalog_rules.py``, so the shipped
``data/product_catalog.json`` and a manual import behave identically.
"""
import json
import os
import sys

import openpyxl

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                    "tectora_products", "models")
)
import catalog_rules  # noqa: E402

SHEET = "Export Simpla"


def build(path, options=None):
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    sheet = workbook[SHEET] if SHEET in workbook.sheetnames else workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    entries, stats = catalog_rules.parse_rows(rows[0], rows[1:], options or {})
    return {
        "root_category": "Dakwerken",
        "markup": (options or {}).get("markup") or catalog_rules.DEFAULT_MARKUP,
        "suppliers": sorted(stats["suppliers"]),
        "products": entries,
        "stats": {
            key: value for key, value in stats.items() if key != "suppliers"
        },
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    output = (
        sys.argv[2] if len(sys.argv) > 2
        else "tectora_products/data/product_catalog.json"
    )
    data = build(sys.argv[1])
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    stats = data["stats"]
    print("%s products -> %s" % (stats["products"], output))
    print("category signals:", stats["signals"])
    print("services (verkoopproducten): %s | goods (grondstoffen): %s"
          % (stats["services"], stats["goods"]))
    print("computed sales prices (x %.2f): %s"
          % (data["markup"], stats["computed_prices"]))
    print("suppliers:", len(data["suppliers"]))
    per_category = {}
    for entry in data["products"]:
        per_category[entry["category_path"]] = per_category.get(
            entry["category_path"], 0) + 1
    for path, count in sorted(per_category.items(), key=lambda kv: -kv[1]):
        print("   %5d  %s" % (count, path))


if __name__ == "__main__":
    main()
