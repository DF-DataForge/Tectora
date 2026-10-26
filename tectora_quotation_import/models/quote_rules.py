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
