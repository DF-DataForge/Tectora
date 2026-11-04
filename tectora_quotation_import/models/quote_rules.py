# -*- coding: utf-8 -*-
"""Reading the quotation export of the old system (Simpla, "Export Simpla").

Plain Python (no Odoo imports), so the rules can be checked against an export
outside Odoo as well.

The export has one row per quotation line; the quotation's own data
(number, date, validity, customer, reference, status) is repeated on every
line. The lines of a quotation come sorted alphabetically, so the chapter
titles of the old quotation (ALGEMENE WERKEN, AFBOUWWERKEN, ...) no longer
stand above their lines: they are recognised as text lines (no quantity, no
price, no amount) and kept apart.

Some lines carry an amount that is a whole multiple of quantity x price: the
old system multiplied the line (identical roofs, several units) in a column
the export leaves out. The amount is the truth (the quotation total was
built on it), so the quantity takes that factor.
"""
import html
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta

# Column aliases, lower-cased and stripped. The first hit wins.
COLUMN_ALIASES = OrderedDict([
    ("number", ["offertenummer", "offerte nummer", "offertenr", "nummer"]),
    ("validity", ["geldigheidstermijn", "geldigheid", "geldig (dagen)"]),
    ("date", ["offertedatum", "datum offerte", "datum"]),
    ("description", ["verkoop", "omschrijving", "artikel", "werkpost"]),
    ("quantity", ["aantal", "hoeveelheid"]),
    ("unit", ["eenheid", "maateenheid"]),
    ("discount", ["kortingspercentage", "korting %", "korting"]),
    ("vat_rate", ["btw-percentage", "btw percentage", "btw %", "btw-tarief"]),
    ("price", ["eenheidsprijs", "prijs", "eenheidsprijs excl btw"]),
    ("notes", ["opmerkingen", "opmerking"]),
    ("customer", ["klantnaam", "klant", "naam klant"]),
    ("customer_ref", ["referentie klant", "klantreferentie", "referentie"]),
    ("street", ["straat nr", "straat", "adres"]),
    ("zip", ["postcode"]),
    ("city", ["plaats", "gemeente", "woonplaats"]),
    ("vat", ["btw-nummer", "btw nummer", "ondernemingsnummer"]),
    ("total", ["totaal ex btw", "totaal excl btw", "totaal excl. btw"]),
    ("status", ["status"]),
])
REQUIRED_COLUMNS = ("number", "date", "description", "quantity", "price",
                    "customer", "status")
COLUMN_LABELS = {
    "number": "offertenummer",
    "date": "offertedatum",
    "description": "verkoop",
    "quantity": "aantal",
    "price": "eenheidsprijs",
    "customer": "klantnaam",
    "status": "status",
}

# Simpla marks lines with a colour after the unit ("st BLAUW", " ORANJE").
COLOUR_WORDS = {"blauw", "oranje", "rood", "groen", "geel", "paars", "grijs",
                "zwart", "wit"}

# Tolerance on an amount, in euro.
AMOUNT_TOLERANCE = 0.01


def clean(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def clean_text(value):
    """Plain text from the (sometimes HTML) text of the old system."""
    text = "" if value is None else str(value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr)\s*>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def number(value):
    """A float from a cell; '3,5' and '1.234,50' are read the Belgian way."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("€", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean(value)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def clean_unit(raw):
    """The unit without Simpla's colour marker: 'st BLAUW' -> 'st'."""
    words = [word for word in clean(raw).split(" ")
             if word and word.lower() not in COLOUR_WORDS]
    unit = " ".join(words)
    # A bare number or ',0' is a typing error in the unit column.
    if re.fullmatch(r"[-\d.,]*", unit):
        return ""
    return unit


def normalise_vat(raw):
    """'be 0723.806.575' -> 'BE0723806575'; a bare 0123456789 gets 'BE'."""
    vat = re.sub(r"[^0-9A-Za-z]", "", clean(raw)).upper()
    if not vat:
        return ""
    if vat.isdigit():
        if len(vat) == 9:
            vat = "0" + vat
        if len(vat) == 10:
            vat = "BE" + vat
    return vat


def map_columns(header):
    """Map the logical field names onto the sheet's column indexes."""
    lowered = [clean(cell).lower() for cell in header]
    columns = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered and lowered.index(alias) not in columns.values():
                columns[field] = lowered.index(alias)
                break
    missing = [COLUMN_LABELS[field] for field in REQUIRED_COLUMNS
               if field not in columns]
    if missing:
        raise ValueError(
            "Kolommen niet gevonden: %s. Gevonden kolommen: %s"
            % (", ".join(missing), ", ".join(clean(c) for c in header if c))
        )
    return columns


def _line(row, cell, stats):
    description = clean_text(cell(row, "description"))
    quantity = number(cell(row, "quantity"))
    price = number(cell(row, "price"))
    discount = number(cell(row, "discount"))
    total_raw = cell(row, "total")
    has_total = total_raw not in (None, "")
    total = number(total_raw) if has_total else None
    line = {
        "description": description,
        "quantity": quantity,
        "unit": clean_unit(cell(row, "unit")),
        "discount": discount,
        "vat_rate": number(cell(row, "vat_rate")),
        "price": price,
        "total": total,
        "kind": "product",
    }
    if not quantity and not price and not total:
        line["kind"] = "text"
        return line
    if total is None:
        line["total"] = quantity * price * (1 - discount / 100.0)
        return line
    factor = 1 - discount / 100.0
    expected = quantity * price * factor
    if abs(expected - total) <= AMOUNT_TOLERANCE:
        return line
    if quantity and price and factor:
        ratio = total / expected
        if ratio > 0 and abs(ratio - round(ratio)) < 0.001:
            # A line multiplied in the old system: the quantity takes the factor.
            line["quantity"] = quantity * round(ratio)
            stats["multiplied"] += 1
            return line
        line["price"] = total / (quantity * factor)
        stats["repriced"] += 1
        return line
    if quantity and factor:
        line["price"] = total / (quantity * factor)
    else:
        # An amount without quantity: one unit at that amount.
        line.update({"quantity": 1.0, "price": total, "discount": 0.0})
    stats["repriced"] += 1
    return line


def parse_rows(header, rows):
    """Group the rows into quotations.

    Returns ``(quotes, stats)``: ``quotes`` in the order of the file, each a
    dict with the quotation data, ``customer`` and its ``lines``; ``stats``
    counts what was read and corrected.
    """
    columns = map_columns(header)

    def cell(row, field):
        index = columns.get(field)
        if index is None or index >= len(row):
            return None
        return row[index]

    stats = {"rows": 0, "skipped_rows": 0, "multiplied": 0, "repriced": 0,
             "text_lines": 0, "product_lines": 0, "conflicts": [],
             "bad_dates": []}
    quotes = OrderedDict()
    for row in rows:
        if not row:
            continue
        number_ = clean(cell(row, "number"))
        if not number_ or number_.startswith("="):
            # Empty rows and the export's totals row (=SUM(...)).
            if any(value not in (None, "") for value in row):
                stats["skipped_rows"] += 1
            continue
        stats["rows"] += 1
        quote = quotes.get(number_)
        if quote is None:
            quote_date = parse_date(cell(row, "date"))
            if not quote_date:
                stats["bad_dates"].append(number_)
            validity = int(number(cell(row, "validity")))
            quote = quotes[number_] = {
                "number": number_,
                "date": quote_date,
                "validity_days": validity,
                "validity_date": (quote_date + timedelta(days=validity))
                if quote_date and validity else None,
                "status": clean(cell(row, "status")),
                "customer_ref": clean(cell(row, "customer_ref")),
                "notes": clean_text(cell(row, "notes")),
                "customer": {
                    "name": clean(cell(row, "customer")),
                    "street": clean(cell(row, "street")),
                    "zip": clean(cell(row, "zip")),
                    "city": clean(cell(row, "city")),
                    "vat": normalise_vat(cell(row, "vat")),
                    "vat_raw": clean(cell(row, "vat")),
                },
                "lines": [],
            }
        else:
            if clean(cell(row, "status")) != quote["status"] or (
                clean(cell(row, "customer")) != quote["customer"]["name"]
            ):
                stats["conflicts"].append(number_)
            # Remarks and reference can be on some lines only.
            quote["notes"] = quote["notes"] or clean_text(cell(row, "notes"))
            quote["customer_ref"] = quote["customer_ref"] or clean(cell(row, "customer_ref"))
        line = _line(row, cell, stats)
        if not line["description"] and line["kind"] == "text":
            continue
        stats["text_lines" if line["kind"] == "text" else "product_lines"] += 1
        quote["lines"].append(line)

    for quote in quotes.values():
        quote["total"] = sum(
            line["total"] or 0.0 for line in quote["lines"] if line["kind"] == "product"
        )
    stats["conflicts"] = sorted(set(stats["conflicts"]))
    return list(quotes.values()), stats


# ---------------------------------------------------------------- sections
# The export sorts the lines of a quotation alphabetically, so a chapter title
# no longer stands above its lines. The titles are recognised (capitals, no
# quantity, no price) and every line is put back under the title it most
# likely stood under: by the kind of work (general costs, safety, demolition,
# build-up, ...) and, where a quotation has several titles of that kind
# ("AFBOUWWERKEN THV HET PLAT DAK" and "... THV DE KOEPELS"), by the words the
# line shares with the title.

# Family of a title, by its words; the first rule that matches wins.
SECTION_RULES = [
    ("nota", ("nota",)),
    ("commercieel", ("tegemoetkom", "commerc", "korting", "actie")),
    ("optie", ("option", "optie", "variant", "meerwerk", "extra", "worst",
               "regie", "upgrade")),
    ("afbouw", ("afbouw", "afbraak", "afbreek")),
    ("opbouw", ("opbouw",)),
    ("veiligheid", ("veiligheid", "stelling", "valbeveilig")),
    ("algemeen", ("algemeen", "algemene", "voorrijd", "verplaatsing", "werkuren",
                  "materiaalgebruik")),
    ("koepel", ("koepel", "velux", "dakraam", "lichtstraat", "daklicht")),
    ("detail", ("afvoer", "randafwerk", "randaansl", "verdichting", "dampscherm",
                "coverboard", "isolatie", "timmerwerk", "dakdoorvoer", "tegelwerk",
                "dakbedekking", "dakrand", "kroonlijst", "werkzaamheden", "werken")),
]
# Where the families stand on the quotation.
FAMILY_RANK = {"algemeen": 0, "veiligheid": 1, "afbouw": 2, "opbouw": 2,
               "detail": 2, "koepel": 2, "other": 2, "optie": 3,
               "commercieel": 4, "nota": 5}
# Within one roof: demolition, build-up, its details, then the rest.
ROOF_ORDER = {"afbouw": 0, "opbouw": 1, "detail": 2, "koepel": 3, "other": 4}
# Families a line of a family may go to when the quotation has no title of
# its own family, in order.
FALLBACK = {
    "algemeen": ("veiligheid",),
    "veiligheid": ("algemeen",),
    "afbouw": ("opbouw", "detail", "koepel", "other"),
    "opbouw": ("detail", "koepel", "other", "afbouw"),
    "commercieel": ("optie",),
}
ROOF_FAMILIES = ("afbouw", "opbouw", "detail", "koepel", "other")

# Kind of work of a line, by its words.
LINE_RULES = [
    ("commercieel", ("korting", "tegemoetkoming", "actie maand", "promotie",
                     "commerciele")),
    ("veiligheid", ("ankerpunt", "balustrade", "veiligheid", "valbeveilig",
                    "stelling", "leuning", "borstwering", "veiligheidsnet",
                    "dakrandbeveilig")),
    ("algemeen", ("vaste kosten", "afvalverwerking", "afval", "verticaal transport",
                  "camionkraan", "kraan", "container", "parkeervergunning",
                  "openbaar domein", "werfinrichting", "voorrijkost", "verplaatsing",
                  "hoogtewerker", "ladderlift", "bouwlift", "werfkeet")),
]
DEMOLITION_VERBS = ("verwijderen", "afbreken", "uitbreken", "demonteren",
                    "wegnemen", "afbraak", "slopen", "uitnemen")

# Words of a title that say nothing about which roof it is about.
TITLE_STOPWORDS = {
    "thv", "het", "de", "van", "der", "den", "een", "plat", "platte", "dak",
    "daken", "boven", "aan", "op", "met", "en", "voor", "bij", "werken",
    "werkzaamheden", "afbouwwerken", "opbouwwerken", "afbraakwerken",
    "uitvoering", "tijdens",
}


# Words a line may share with a title without being in it: a title
# "AFVOER HEMELWATER" is about the outlets and downpipes, ...
TITLE_SYNONYMS = {
    "afvoer": {"tapbui", "spuwer", "noodsp", "bolroo", "bladva", "goot", "hemelw", "afvoer"},
    "hemelw": {"tapbui", "spuwer", "noodsp", "bolroo", "bladva", "goot", "afvoer"},
    "randaf": {"dakran", "opstan", "muurka", "solins", "binnen", "buiten", "boordp"},
    "randaa": {"dakran", "opstan", "muurka", "solins", "binnen", "buiten", "boordp"},
    "dampsc": {"dampre", "dampop"},
    "coverb": {"isolat", "coverb"},
    "isolat": {"isolat", "coverb"},
    "verdic": {"dakbed", "kimfix", "verank", "slabbe", "epdm"},
    "timmer": {"kepers", "multip", "spouwp", "regel", "latten", "boordp", "planke", "balken"},
    "zinkwe": {"zink", "solins", "anthra"},
    "muuraf": {"muuraf", "dekste", "dekpan"},
    "daklic": {"koepel", "velux", "dakraa", "lichts"},
    "koepel": {"koepel", "velux", "rwa"},
    "velux": {"velux", "dakraa"},
    "platda": {"velux", "dakraa", "koepel"},
}


def _fold(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _stems(text, stopwords=()):
    words = re.findall(r"[a-z]{3,}", _fold(text))
    return {word[:6] for word in words if word not in stopwords}


def is_title(text):
    """A chapter title: (mostly) capitals, or a numbered heading of a
    specification ('34.12.20 Isolatieplaten ...', 'Hoofdstuk 35 - ...')."""
    text = (text or "").strip()
    if re.match(r"^(\d+\.)+\d*\s", text) or re.match(r"(?i)^hoofdstuk\s", text):
        return True
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.8


def section_family(title):
    folded = _fold(title)
    for family, words in SECTION_RULES:
        if any(word in folded for word in words):
            return family
    return "other"


def line_family(line, chapter=None):
    """The kind of work of a product line; ``chapter`` is the family its
    catalogue product says (or None)."""
    folded = _fold(line["description"])
    if line["price"] < 0:
        return "commercieel"
    for family, words in LINE_RULES:
        if any(word in folded for word in words):
            return family
    if chapter:
        return chapter
    if folded.startswith(DEMOLITION_VERBS):
        return "afbouw"
    return "opbouw"


def arrange_sections(quote, chapter_of=None):
    """Put the lines of a quotation under its titles.

    Returns ``(blocks, notes, empty)``: ``blocks`` a list of
    ``(title or None, [lines])`` in quotation order (the first block, without
    title, holds the lines no title fits); ``notes`` the text lines that are
    no title; ``empty`` the titles that got no line.
    ``chapter_of(description)`` may give the family of a catalogue product.
    """
    sections = []
    notes = []
    for line in quote["lines"]:
        if line["kind"] != "text":
            continue
        if not is_title(line["description"]):
            notes.append(line)
            continue
        title_words = _stems(line["description"], TITLE_STOPWORDS)
        sections.append({
            "title": line["description"],
            "family": section_family(line["description"]),
            "words": title_words.union(*(TITLE_SYNONYMS.get(word, ()) for word in title_words)),
            "lines": [],
        })

    loose = []
    seen = {}
    for line in quote["lines"]:
        if line["kind"] == "text":
            continue
        family = line_family(line, chapter_of(line["description"]) if chapter_of else None)
        target = _pick_section(line, family, sections, seen)
        (target["lines"] if target else loose).append(line)

    # Notes stand under the notes title when the quotation has one.
    nota = next((s for s in sections if s["family"] == "nota"), None)
    if nota:
        nota["lines"].extend(notes)
        notes = []

    # Order: general, safety, then per roof its demolition and build-up,
    # options, commercial, notes. The roof of a title is what it names
    # besides its kind of work: nothing (the main flat roof), the domes, the
    # garage, ...
    def roof_of(section):
        if section["family"] == "koepel" or "koepel" in section["words"]:
            return frozenset({"koepel"})
        if section["family"] in ("afbouw", "opbouw"):
            return frozenset(section["words"])
        return None  # a detail title (DAMPSCHERM, ...): with the first roof

    roofs = []
    for section in sections:
        roof = roof_of(section)
        if section["family"] in ROOF_FAMILIES and roof is not None and roof not in roofs:
            roofs.append(roof)
    # The main roof first, the domes last; the others as they come.
    roofs.sort(key=lambda roof: (roof == frozenset({"koepel"}), len(roof)))

    def rank(item):
        index, section = item
        family = section["family"]
        if family in ROOF_FAMILIES:
            roof = roof_of(section)
            return (FAMILY_RANK[family], roofs.index(roof) if roof is not None else 0,
                    ROOF_ORDER[family], index)
        return (FAMILY_RANK[family], 0, 0, index)

    ordered = [section for _index, section in sorted(enumerate(sections), key=rank)]
    blocks = [(None, loose)] if loose else []
    blocks += [(s["title"], s["lines"]) for s in ordered if s["lines"]]
    empty = [s["title"] for s in ordered if not s["lines"]]
    return blocks, notes, empty


def _pick_section(line, family, sections, seen):
    """The title a line most likely stood under, or None.

    A title that names the line ("DAMPSCHERM" for the vapour barrier,
    "AFBOUWWERKEN THV DE KOEPELS" for removing a dome) wins; otherwise the
    most generic title of the line's kind of work, then of a related kind.
    The same line on several roofs goes to their titles in turn.
    """
    if not sections:
        return None
    words = _stems(line["description"])

    def score(section):
        return len(section["words"] & words)

    def pick(candidates, key_family):
        best = max(score(s) for s in candidates)
        best_ones = [s for s in candidates if score(s) == best]
        fewest = min(len(s["words"]) for s in best_ones)
        best_ones = [s for s in best_ones if len(s["words"]) == fewest]
        key = (_fold(line["description"]), key_family)
        count = seen.get(key, 0)
        seen[key] = count + 1
        return best_ones[count % len(best_ones)]

    if not line["quantity"] and line["price"]:
        # Not chosen (quantity 0): an option, when the quotation has options.
        options = [s for s in sections if s["family"] == "optie"]
        if options:
            return pick(options, "optie")
    if family in ROOF_FAMILIES:
        # Demolition never goes under build-up (or its details), nor
        # build-up under demolition.
        allowed = {"afbouw", "koepel", "other"} if family == "afbouw" \
            else {"opbouw", "detail", "koepel", "other"}
        named = [s for s in sections if s["family"] in allowed and score(s) > 0]
        if named:
            return pick(named, "named")
    for candidate_family in (family,) + FALLBACK.get(family, ()):
        candidates = [s for s in sections if s["family"] == candidate_family]
        if candidates:
            return pick(candidates, candidate_family)
    return None
