#!/usr/bin/env python3
"""Match a Stuklijst (bill of materials) export onto the Tectora catalogue.

The export (``Stuklijst_Tectora.xlsx``) comes from a database that uses product
variants: a component reads ``Buitenhoek DRBS (200mm, geanodiseerd)`` -- a
template name with its attribute values in brackets. The catalogue in this
repository is flat and spells the same article ``Buitenhoek DRBS 200/80 Ano``.
So the two sides share no key and barely share a vocabulary; matching has to be
built out of the structure of the names.

Three keys are tried per component, first hit wins:

1. ``code``      -- a ``[article code]`` in the component name against a
                    supplier code or a code embedded in a catalogue name, or an
                    exactly equal name;
2. ``rule``      -- a small keyword table, which is all the labour lines need
                    (``werkuren construction`` -> ``Werkuren opbouwwerken``);
3. ``structure`` -- family tokens + leading dimension + finish class, because
                    that is how the catalogue encodes its profile ranges.

Everything the three leave below the review threshold is a human decision; the
point of the score is to sort that queue by how much of the export it unblocks.

Usage:
    python match_bom_export.py Stuklijst_Tectora.xlsx [-o out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CATALOGUE = os.path.join(DATA, "product_catalog.json")
PRICE_BOOK = os.path.join(DATA, "price_book.json")

# A match at or above this is reliable enough to import unattended; between the
# two it is a proposal to review; below the lower one there is no proposal.
AUTO = 0.70
REVIEW = 0.45


# --------------------------------------------------------------------- helpers
def strip_accents(text):
    text = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(c for c in text if not unicodedata.combining(c))


def norm(text):
    text = strip_accents(text).lower().replace("²", "2")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/,.]+", " ", text)).strip()


def tokens(text):
    return {t for t in norm(text).replace("/", " ").replace(",", " ").split() if t}


def canon(text):
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())


VARIANT = re.compile(r"\s*\(([^()]*)\)\s*$")


def parse_variant(name):
    """``Serie 6 Binnenvoegstuk (120/60, RAL 9006)`` -> family, [attrs]."""
    match = VARIANT.search(name.strip())
    if not match:
        return name.strip(), []
    attrs = [part.strip() for part in match.group(1).split(",") if part.strip()]
    return name[: match.start()].strip(), attrs


ANODISED = re.compile(r"\b(geanodiseerd|anodic|ano|brut|bruut|naturel)\b")
LACQUERED = re.compile(r"\b(ral|9005|9006|7016|9010|structuur|satijn|mat|divers)\b")
COLOURS = ("antraciet", "quartz", "koper", "inox", "zwart", "wit")


def finish_class(text):
    """The finish axis, reduced to what the catalogue actually distinguishes.

    Per profile range the catalogue carries an anodised article and a "Ral
    divers" one; a specific RAL is not a separate article. So every RAL, satin
    and structure finish collapses onto one class.
    """
    value = norm(text)
    for colour in COLOURS:
        if colour in value:
            return colour
    if LACQUERED.search(value):
        return "ral"
    if ANODISED.search(value):
        return "ano"
    return ""


NUMBER = re.compile(r"\b(\d{2,4})\b")


def dimensions(text):
    return [m.group(1) for m in NUMBER.finditer(norm(text))]


# Labour and the few components a keyword settles outright.
RULES = [
    (r"werkuren.*(construction|opbouw)", "Werkuren opbouwwerken"),
    (r"werkuren.*afbraak|^afbraakwerken$", "Werkuren afbraakwerken"),
    (r"werkuren.*veiligheid", "Werkuren veiligheid"),
    (r"werkuren.*regie", "Werkuren in regie"),
    (r"^werkuren", "Werkuren opbouwwerken"),
]


# ------------------------------------------------------------------- the parse
def read_export(path):
    """Group the flat export into BoMs. Only the first row of a BoM carries the
    product, the reference and the type; the rows under it are its lines."""
    import openpyxl

    sheet = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    boms = []
    current = None
    for row in sheet.iter_rows(min_row=2, values_only=True):
        product, series, reference, kind, line, qty, component, uom = (
            list(row) + [None] * 8
        )[:8]

        def clean(value):
            return re.sub(r"\s+", " ", str(value)).strip() if value is not None else ""

        if clean(product):
            current = {
                "product": clean(product),
                "series": series,
                "reference": clean(reference),
                "kind": clean(kind),
                "lines": [],
            }
            boms.append(current)
        if current is None:
            continue
        name = clean(component) or clean(line)
        if name or qty is not None:
            current["lines"].append({"component": name, "qty": qty, "uom": clean(uom)})
    return boms


# ------------------------------------------------------------------- the match
def build_index(rows):
    return [
        {
            "row": row,
            "tokens": tokens(row["name"]),
            "norm": norm(row["name"]),
            "finish": finish_class(row["name"]),
            "dims": dimensions(row["name"]),
        }
        for row in rows
    ]


def structural(component, index):
    """Score every catalogue row on family, dimension and finish."""
    family, attrs = parse_variant(component)
    family_tokens = tokens(family)
    if not family_tokens:
        return 0.0, None, ""
    finish = finish_class(" ".join(attrs)) or finish_class(family)
    dims = dimensions(" ".join(attrs)) + dimensions(family)
    # The first number is the one that identifies the article ("DRB 60 met
    # nuttige hoogte onder oplegvlak: 45mm" is a 60, not a 45).
    leading = dims[0] if dims else None
    dim_set = set(dims)
    best = (0.0, None, "")
    for entry in index:
        if not entry["tokens"]:
            continue
        shared = family_tokens & entry["tokens"]
        if not shared:
            continue
        score = 0.45 * (len(shared) / len(family_tokens | entry["tokens"]))
        score += 0.25 * SequenceMatcher(None, norm(family), entry["norm"]).ratio()
        why = []
        if finish and entry["finish"]:
            if finish == entry["finish"]:
                score += 0.18
                why.append("finish %s" % finish)
            else:
                score -= 0.15
        if dim_set and entry["dims"]:
            if leading and leading == entry["dims"][0]:
                score += 0.25
                why.append("maat %s" % leading)
            elif dim_set & set(entry["dims"]):
                score += 0.12
                why.append("maat " + ",".join(sorted(dim_set & set(entry["dims"]))))
            else:
                score -= 0.18
        if score > best[0]:
            best = (score, entry["row"], " + ".join(why) or "naam")
    return best


def match_component(component, index, by_supplier, by_namecode, by_name):
    value = norm(component)
    if value in by_name:
        return 1.0, by_name[value], "code", "exacte naam"
    for code in re.findall(r"\[([^\]]+)\]", component):
        key = canon(code)
        for pool in (by_supplier, by_namecode):
            if key in pool:
                return 0.95, pool[key], "code", "artikelcode %s" % code
            bare = key.lstrip("0")
            if bare:
                for candidate, row in pool.items():
                    if candidate.lstrip("0") == bare:
                        return 0.90, row, "code", "artikelcode %s" % code
    for pattern, target in RULES:
        if re.search(pattern, value):
            row = by_name.get(norm(target))
            if row:
                return 0.90, row, "rule", "regel: %s" % target
    score, row, why = structural(component, index)
    return score, row, "structure", why


def match_product(name, book):
    """BoM parent -> sales product, on name alone: the export carries no code."""
    query = tokens(name)
    if not query:
        return 0.0, None
    best = (0.0, None)
    for row in book:
        row_tokens = tokens(row["name"])
        if not row_tokens:
            continue
        jaccard = len(query & row_tokens) / len(query | row_tokens)
        if not jaccard:
            continue
        ratio = SequenceMatcher(None, norm(name), norm(row["name"])).ratio()
        score = 0.6 * jaccard + 0.4 * ratio
        if score > best[0]:
            best = (score, row)
    return best


def bucket(score):
    if score >= AUTO:
        return "automatisch"
    return "nakijken" if score >= REVIEW else "handmatig"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", help="Stuklijst_Tectora.xlsx")
    parser.add_argument("-o", "--out", default="bom_matching.json")
    args = parser.parse_args()

    boms = read_export(args.export)
    catalogue = json.load(open(CATALOGUE))["products"]
    book = json.load(open(PRICE_BOOK))["products"]

    index = build_index(catalogue)
    by_name = {}
    by_supplier = {}
    by_namecode = {}
    for row in catalogue:
        by_name.setdefault(norm(row["name"]), row)
        if row.get("supplier_code"):
            by_supplier.setdefault(canon(row["supplier_code"]), row)
        for code in re.findall(r"\b\d{6,}\b", row["name"]):
            by_namecode.setdefault(canon(code), row)

    usage = Counter(l["component"] for b in boms for l in b["lines"])
    components = []
    for component, uses in usage.most_common():
        score, row, method, why = match_component(
            component, index, by_supplier, by_namecode, by_name
        )
        family, attrs = parse_variant(component)
        components.append(
            {
                "component": component,
                "family": family,
                "variant": ", ".join(attrs),
                "uses": uses,
                "score": round(min(score, 1.0), 3),
                "method": method,
                "why": why,
                "confidence": bucket(score),
                "code": (row or {}).get("code"),
                "match": (row or {}).get("name"),
                "uom": (row or {}).get("uom"),
            }
        )

    products = []
    for name in sorted({b["product"] for b in boms}):
        score, row = match_product(name, book)
        products.append(
            {
                "product": name,
                "boms": sum(1 for b in boms if b["product"] == name),
                "score": round(score, 3),
                "confidence": bucket(score),
                "code": (row or {}).get("code"),
                "match": (row or {}).get("name"),
            }
        )

    result = {"boms": boms, "products": products, "components": components}
    with open(args.out, "w") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=1)

    lines = sum(len(b["lines"]) for b in boms)
    print("%s stuklijsten, %s regels" % (len(boms), lines))
    for label, rows, weight in (
        ("producten", products, None),
        ("componenten", components, "uses"),
    ):
        counts = Counter(r["confidence"] for r in rows)
        print(
            "  %-12s %s"
            % (
                label,
                "  ".join("%s: %s" % (k, counts[k]) for k in
                          ("automatisch", "nakijken", "handmatig")),
            )
        )
        if weight:
            weighted = Counter()
            for r in rows:
                weighted[r["confidence"]] += r[weight]
            print(
                "  %-12s %s"
                % (
                    "regels",
                    "  ".join(
                        "%s: %s (%.0f%%)" % (k, weighted[k], weighted[k] / lines * 100)
                        for k in ("automatisch", "nakijken", "handmatig")
                    ),
                )
            )
    print("geschreven: %s" % args.out)


if __name__ == "__main__":
    main()
