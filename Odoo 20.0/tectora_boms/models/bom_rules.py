# -*- coding: utf-8 -*-
"""Read a Stuklijst export and match it onto the flat product catalogue.

Pure Python on purpose: no Odoo imports, so the parsing and the matching can be
exercised without a database. See ``docs/stuklijst_koppeling.md`` for the
analysis this is built on.

The export comes from a database that uses product variants: a component reads
``Buitenhoek DRBS (200mm, geanodiseerd)`` -- a template name with its attribute
values in brackets. This catalogue is flat and spells the same article
``Buitenhoek DRBS 200/80 Ano``. The two share no key and barely share a
vocabulary (matching on names alone finds 7 of 672 components), so the match is
built out of the structure of the names instead. Three keys, first hit wins:

``code``       a ``[article code]`` in the component name against a supplier
               code or a code embedded in a catalogue name, or an equal name;
``rule``       a keyword table, which is all the labour lines need;
``structure``  family tokens + the leading dimension + the finish class, which
               is how the catalogue encodes its profile ranges.
"""
import hashlib
import re
import unicodedata

# A match at or above AUTO is reliable enough to import unattended; between the
# two it is a proposal to review; below REVIEW there is no proposal at all.
AUTO = 0.70
REVIEW = 0.45

# BoM type in the export -> mrp.bom.type
BOM_TYPES = {
    "kit": "phantom",
    "produceer dit product": "normal",
    "manufacture this product": "normal",
    "normal": "normal",
    "phantom": "phantom",
}

COLUMNS = [
    "product", "series", "reference", "kind", "line", "qty", "component", "uom",
]


# --------------------------------------------------------------- text handling
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


def clean(value):
    return re.sub(r"\s+", " ", str(value)).strip() if value is not None else ""


VARIANT = re.compile(r"\s*\(([^()]*)\)\s*$")


def parse_variant(name):
    """``Serie 6 Binnenvoegstuk (120/60, RAL 9006)`` -> family, [attributes]."""
    match = VARIANT.search(name.strip())
    if not match:
        return name.strip(), []
    attributes = [p.strip() for p in match.group(1).split(",") if p.strip()]
    return name[: match.start()].strip(), attributes


ANODISED = re.compile(r"\b(geanodiseerd|anodic|ano|brut|bruut|naturel)\b")
LACQUERED = re.compile(r"\b(ral|9005|9006|7016|9010|structuur|satijn|mat|divers)\b")
COLOURS = ("antraciet", "quartz", "koper", "inox", "zwart", "wit")


def finish_class(text):
    """The finish, reduced to what the catalogue actually distinguishes.

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


# Digits glued to a unit still name a dimension ("200mm"), so this cannot lean
# on \b -- there is no word boundary inside "200mm".
NUMBER = re.compile(r"(?<![\d])(\d{2,4})(?![\d])")
# A RAL number is a colour, not a size; left in it would demand that the
# catalogue name carry "9006" as its leading dimension.
RAL_CODE = re.compile(r"\bral\s*\d{4}\b|\b(?:9005|9006|9010|7016|9007|9016)\b")


def dimensions(text):
    value = RAL_CODE.sub(" ", norm(text))
    return [m.group(1) for m in NUMBER.finditer(value)]


# Labour, and the components a keyword settles outright. The target is a
# catalogue product name.
RULES = [
    (r"werkuren.*(construction|opbouw)", "Werkuren opbouwwerken"),
    (r"werkuren.*afbraak|^afbraakwerken$", "Werkuren afbraakwerken"),
    (r"werkuren.*veiligheid", "Werkuren veiligheid"),
    (r"werkuren.*regie", "Werkuren in regie"),
    (r"^werkuren", "Werkuren opbouwwerken"),
]


# ------------------------------------------------------- units of measure
# The export's unit column is a packaging description, not a unit: "Doos 500
# stuks", "m per 3m element". Worse, the basis of the quantity flips between
# rows of one family -- the same dakrand sierplaat is 1 "m per 3m element" in
# anodised and 0,34 "St" in RAL 9006. So a factor is only ever offered, never
# applied silently.
BASE_UNITS = {"st", "stuk", "stuks", "uren", "uur", "lm", "m", "m2", "m²", "m3", "m³"}


def packaging_factor(unit):
    """How many base units one package holds, or None when it is already a base
    unit or the label cannot be read."""
    text = str(unit or "").replace(",", ".").strip()
    if not text or text.lower() in BASE_UNITS:
        return None
    for pattern, combine in (
        (r"doos\s*(\d+(?:\.\d+)?)", lambda m: float(m.group(1))),
        (r"plaat\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)",
         lambda m: float(m.group(1)) * float(m.group(2))),
        (r"rol\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)",
         lambda m: float(m.group(1)) * float(m.group(2))),
        (r"rol\s*(\d+(?:\.\d+)?)\s*m2", lambda m: float(m.group(1))),
        (r"rol\s*(\d+(?:\.\d+)?)", lambda m: float(m.group(1))),
        (r"per\s*(\d+(?:\.\d+)?)\s*m?\s*element", lambda m: float(m.group(1))),
    ):
        match = re.search(pattern, text, re.I)
        if match:
            value = round(combine(match), 4)
            return value if value > 0 else None
    return None


# ---------------------------------------------------------------- the parse
def parse_export(rows):
    """Group the flat export into BoMs.

    Only the first row of a BoM carries the product, the reference and the
    type; the rows under it are its component lines.
    """
    boms = []
    current = None
    for row in rows:
        values = dict(zip(COLUMNS, (list(row) + [None] * len(COLUMNS))))
        if clean(values["product"]):
            current = {
                "product": clean(values["product"]),
                "reference": clean(values["reference"]),
                "type": BOM_TYPES.get(clean(values["kind"]).lower(), "normal"),
                "lines": [],
            }
            boms.append(current)
        if current is None:
            continue
        component = clean(values["component"]) or clean(values["line"])
        if not component:
            continue
        try:
            qty = float(values["qty"]) if values["qty"] is not None else 0.0
        except (TypeError, ValueError):
            qty = 0.0
        current["lines"].append(
            {"component": component, "qty": qty, "uom": clean(values["uom"])}
        )
    return [b for b in boms if b["lines"]]


def variant_label(bom):
    """The attribute values that set this BoM apart from its siblings.

    The export has no variant column: what distinguishes the BoMs of one
    product is which variant of a component they pick, so the label is read
    back off the component names.
    """
    values = []
    for line in bom["lines"]:
        _family, attributes = parse_variant(line["component"])
        for attribute in attributes:
            if attribute not in values:
                values.append(attribute)
    return " / ".join(values)


def signature(bom):
    """Stable key for one BoM: same product, same lines -> same key.

    Used to make the import idempotent and to collapse the export's exact
    duplicates (36 of 692) instead of loading them twice.
    """
    parts = [bom["product"], bom["type"]] + sorted(
        "%s|%s|%s" % (line["component"], line["qty"], line["uom"])
        for line in bom["lines"]
    )
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- the match
def build_index(products):
    """products: [{"id", "code", "name", ...}] -> searchable index."""
    index = []
    for product in products:
        name = product.get("name") or ""
        index.append({
            "product": product,
            "tokens": tokens(name),
            "norm": norm(name),
            "finish": finish_class(name),
            "dims": dimensions(name),
        })
    return index


def _ratio(a, b):
    """Similarity of two normalised strings, 0..1 (difflib, imported lazily so
    the module stays cheap to import)."""
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def structural(component, index):
    """Score every catalogue entry on family, dimension and finish."""
    family, attributes = parse_variant(component)
    family_tokens = tokens(family)
    if not family_tokens:
        return 0.0, None, ""
    finish = finish_class(" ".join(attributes)) or finish_class(family)
    dims = dimensions(" ".join(attributes)) + dimensions(family)
    # The first number identifies the article: "DRB 60 met nuttige hoogte
    # onder oplegvlak: 45mm" is a 60, not a 45.
    leading = dims[0] if dims else None
    dim_set = set(dims)
    family_norm = norm(family)
    best = (0.0, None, "")
    for entry in index:
        if not entry["tokens"]:
            continue
        shared = family_tokens & entry["tokens"]
        if not shared:
            continue
        score = 0.45 * (len(shared) / len(family_tokens | entry["tokens"]))
        score += 0.25 * _ratio(family_norm, entry["norm"])
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
            best = (score, entry["product"], " + ".join(why) or "naam")
    return best


def match_component(component, index, by_supplier, by_namecode, by_name):
    """-> (score, product or None, method, why)."""
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
                for candidate, product in pool.items():
                    if candidate.lstrip("0") == bare:
                        return 0.90, product, "code", "artikelcode %s" % code
    for pattern, target in RULES:
        if re.search(pattern, value):
            product = by_name.get(norm(target))
            if product:
                return 0.90, product, "rule", "regel: %s" % target
    score, product, why = structural(component, index)
    return min(score, 1.0), product, "structure", why


def match_product(name, index):
    """BoM parent -> sales product, on name alone: the export carries no code."""
    query = tokens(name)
    if not query:
        return 0.0, None
    value = norm(name)
    best = (0.0, None)
    for entry in index:
        if not entry["tokens"]:
            continue
        jaccard = len(query & entry["tokens"]) / len(query | entry["tokens"])
        if not jaccard:
            continue
        score = 0.6 * jaccard + 0.4 * _ratio(value, entry["norm"])
        if score > best[0]:
            best = (score, entry["product"])
    return best


def confidence(score):
    if score >= AUTO:
        return "auto"
    return "review" if score >= REVIEW else "manual"
