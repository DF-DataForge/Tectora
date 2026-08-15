#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parse the GOOD_LUCK price-book workbook into tectora_products seed data.

Usage:
    python3 tools/parse_price_book.py <price_book.xlsx> [output.json]

The workbook has one sheet per project type (RENOVATIE / NIEUWBOUW /
INDUSTRIE). On every sheet:

* bold ALL-CAPS rows are section headers ("1) ALGEMENE WERKEN:");
* a product starts on a row with a numeric selling price in column C (or a
  quantity in B but no price: "price on request" items) and its name/spec
  continues on the text-only rows below it;
* column B is the default quantity, column D the unit (often empty on the
  NIEUWBOUW/INDUSTRIE sheets, where the unit hides in the name suffix).

Products are de-duplicated across sheets on their full normalised text.  The
RENOVATIE price (already indexed in the workbook) becomes the base list
price; deviating NIEUWBOUW/INDUSTRIE prices become pricelist rules.
"""
import json
import re
import sys
from collections import OrderedDict

import openpyxl

SHEET_TYPES = OrderedDict(
    [("RENOVATIE", "renovatie"), ("NIEUWBOUW", "nieuwbouw"), ("INDUSTRIE", "industrie")]
)

# Canonical categories: (match substring of the normalised header, key, name).
CATEGORIES = [
    ("ALGEMENE WERKEN", "algemene_werken", "01. Algemene werken"),
    ("VEILIGHEIDS", "veiligheid", "02. Verplichte veiligheidsvoorzieningen"),
    ("AFBOUWWERKEN", "afbraak", "03. Afbraakwerken plat dak"),
    ("OPBOUWWERKEN", "opbouw", "04. Opbouwwerken plat dak"),
    ("KOEPEL", "koepels", "05. Koepels"),
    ("DAKRA", "dakramen", "06. Dakramen"),
    ("OVERSTEKEN", "oversteken", "07. Oversteken"),
    ("TERRASVLOER", "terrasvloer", "08. Terrasvloer"),
    ("WORST CASE", "worst_case", "09. Worst case scenario"),
    ("NOTA", "notas", "10. Algemene nota's"),
    ("GARANTIE", "garantie", "11. Garantiepakket EPDM Solutions"),
    ("ANDERE WERKEN", "andere", "12. Andere werken"),
    ("UPSALE", "upsale", "13. Upsale"),
]

UNIT_MAP = {
    "M²": "m2", "M2": "m2",
    "LM": "m", "PER LM": "m",
    "STUK": "unit",
    "SOG": "forfait", "VH": "forfait",
    "PER DAG": "day",
    "€/U": "hour",
}

UOM_NAMES = {
    "unit": "Stuk",
    "m2": "m²",
    "m": "m",
    "forfait": "Forfait",
    "day": "Dag",
    "hour": "Uur",
    "week": "Week",
}


def norm(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def category_for(header):
    up = str(header or "").upper()
    for match, key, _name in CATEGORIES:
        if match in up:
            return key
    return "andere"


def unit_from_text(text):
    low = " " + norm(text)
    if re.search(r"\(m²\)|\(m2\)|per m²|per m2", low):
        return "m2"
    if re.search(r"\(lm\)|per lm|per lopende meter", low):
        return "m"
    if "per week" in low:
        return "week"
    if "per dag" in low:
        return "day"
    if re.search(r"per uur|/u\b", low):
        return "hour"
    if re.search(r"\(stuk\)|per stuk|per paneel", low):
        return "unit"
    return "unit"


def is_section_header(cell, price):
    if price is not None:
        return False
    value = str(cell.value or "").strip()
    if not value or not (cell.font and cell.font.bold):
        return False
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", value)
    return bool(letters) and letters == letters.upper()


def extract_sheet(ws, project_type):
    items = []
    section = None
    rows = list(ws.iter_rows(min_col=1, max_col=5))
    i = 0
    while i < len(rows):
        a, b, c, _d, e = rows[i]
        price = c.value if isinstance(c.value, (int, float)) else None
        if is_section_header(a, price):
            section = str(a.value).strip()
            i += 1
            continue
        name_first = str(a.value).strip() if a.value is not None else ""
        has_qty = isinstance(b.value, (int, float))
        if price is None and not has_qty:
            i += 1
            continue
        if not name_first:
            i += 1
            continue
        lines = [re.sub(r"^\+\s*", "", name_first)]
        notes = [str(e.value).strip()] if e.value else []
        j = i + 1
        while j < len(rows):
            a2, b2, c2, _d2, e2 = rows[j]
            text = str(a2.value).strip() if a2.value is not None else ""
            if (
                not text
                or isinstance(c2.value, (int, float))
                or isinstance(b2.value, (int, float))
                or (a2.font and a2.font.bold)
            ):
                break
            lines.append(text)
            if e2.value:
                notes.append(str(e2.value).strip())
            j += 1
        unit_cell = str(rows[i][3].value).strip().upper() if rows[i][3].value else ""
        unit = UNIT_MAP.get(unit_cell) or unit_from_text(" ".join(lines))
        items.append({
            "project_type": project_type,
            "section": section,
            "row": a.row,
            "lines": lines,
            "price": round(float(price), 2) if price is not None else None,
            "unit": unit,
            "note": " | ".join(notes),
        })
        i = j
    return items


def build(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    raw = []
    for sheet, project_type in SHEET_TYPES.items():
        raw.extend(extract_sheet(wb[sheet], project_type))

    products = OrderedDict()
    for item in raw:
        key = norm(" ".join(item["lines"]))
        product = products.setdefault(key, {
            "lines": item["lines"],
            "category": category_for(item["section"]),
            "unit": item["unit"],
            "note": item["note"],
            "prices": OrderedDict(),
            "first_row": item["row"],
        })
        if item["price"] is not None and item["project_type"] not in product["prices"]:
            product["prices"][item["project_type"]] = item["price"]
        if not product["note"] and item["note"]:
            product["note"] = item["note"]

    cat_order = {key: index for index, (_m, key, _n) in enumerate(CATEGORIES)}
    ordered = sorted(
        products.values(), key=lambda p: (cat_order.get(p["category"], 99), p["first_row"])
    )

    out_products = []
    for index, product in enumerate(ordered, start=1):
        lines = product["lines"]
        name = lines[0]
        if name.endswith(":") and len(lines) > 1:
            name = f"{name} {lines[1]}"
        prices = product["prices"]
        base = (
            prices.get("renovatie")
            if prices.get("renovatie") is not None
            else prices.get("nieuwbouw")
            if prices.get("nieuwbouw") is not None
            else prices.get("industrie")
        )
        deviations = {
            ptype: price
            for ptype, price in prices.items()
            if base is not None and abs(price - base) > 0.005
        }
        tags = []
        if product["category"] == "upsale":
            tags.append("Upsale")
        if base is None:
            tags.append("Prijs op aanvraag")
        out_products.append({
            "code": "DAK-%04d" % index,
            "name": name[:120],
            "description": "\n".join(lines),
            "category": product["category"],
            "uom": product["unit"],
            "list_price": base or 0.0,
            "prices": deviations,
            "note": product["note"],
            "tags": tags,
            "project_types": list(prices) or [p["project_type"] for p in raw
                                              if norm(" ".join(p["lines"])) == norm(" ".join(lines))],
        })

    return {
        "categories": [
            {"key": key, "name": name} for _match, key, name in CATEGORIES
        ],
        "uoms": UOM_NAMES,
        "pricelists": {
            "renovatie": "Renovatie",
            "nieuwbouw": "Nieuwbouw",
            "industrie": "Industrie",
        },
        "products": out_products,
    }


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    output = sys.argv[2] if len(sys.argv) > 2 else "tectora_products/data/price_book.json"
    data = build(sys.argv[1])
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
    rules = sum(len(p["prices"]) for p in data["products"])
    on_request = sum(1 for p in data["products"] if "Prijs op aanvraag" in p["tags"])
    print(f"{len(data['products'])} products, {rules} pricelist rules, "
          f"{on_request} price-on-request -> {output}")


if __name__ == "__main__":
    main()
