# -*- coding: utf-8 -*-
"""Reading the project export of the old system (Simpla) and finding the
imported orders of every project.

Plain Python (no Odoo imports), like quote_rules.

The export names no quotation: a project is matched on its customer (name or
VAT number) and on its "totaal offertes ex BTW", which is the total of the
quotation(s) it was made from. One project can hold several quotations, so
combinations of up to MAX_ORDERS orders of the customer are tried.
"""
import itertools
import math
import re
import unicodedata
from collections import OrderedDict
from datetime import timedelta

from .quote_rules import clean, clean_text, normalise_vat, number, parse_date

COLUMN_ALIASES = OrderedDict([
    ("number", ["nummer", "projectnummer"]),
    ("name", ["naam", "projectnaam"]),
    ("customer", ["klantnaam"]),
    ("vat", ["btw-nummer klant", "btw-nummer"]),
    ("site_street", ["adres project"]),
    ("site_zip", ["postcode project"]),
    ("site_city", ["stad project"]),
    ("description", ["omschrijving"]),
    ("customer_ref", ["referentie voor klant", "referentie klant"]),
    ("status", ["status"]),
    ("deadline", ["deadline"]),
    ("responsible", ["verantwoordelijke gebruiker", "verantwoordelijke", "ploeg"]),
    ("total", ["totaal offertes ex btw", "totaal offertes"]),
])
REQUIRED_COLUMNS = ("number", "customer", "status", "total")

MAX_ORDERS = 3
TRUNCATED_AT = 240
AMOUNT_TOLERANCE = 0.05
LINE_TOLERANCE = 0.005

# Statuses of a project whose works are over. "afgesloten" closes the
# project; the others are executed but still being invoiced or handed over.
CLOSED_WORDS = ("afgesloten", "gesloten", "geannuleerd")
EXECUTED_WORDS = ("slotfactuur", "werk klaar", "oplevering", "uitgevoerd", "afgewerkt")


def _key(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w+]+", " ", text)).strip()


def map_columns(header):
    lowered = [clean(cell).lower() for cell in header]
    columns = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                columns[field] = lowered.index(alias)
                break
    missing = [field for field in REQUIRED_COLUMNS if field not in columns]
    if missing:
        raise ValueError(
            "Kolommen niet gevonden: %s. Gevonden kolommen: %s"
            % (", ".join(COLUMN_ALIASES[f][0] for f in missing),
               ", ".join(clean(c) for c in header if c))
        )
    return columns


def parse_rows(header, rows):
    """The projects of the export, in the order of the file."""
    columns = map_columns(header)

    def cell(row, field):
        index = columns.get(field)
        if index is None or index >= len(row):
            return None
        return row[index]

    projects = []
    for row in rows:
        if not row:
            continue
        number_ = clean(cell(row, "number"))
        if not number_ or number_.startswith("="):
            continue
        site = ", ".join(filter(None, [
            clean(cell(row, "site_street")),
            " ".join(filter(None, [clean(cell(row, "site_zip")), clean(cell(row, "site_city"))])),
        ]))
        # Simpla cuts the description off at about 255 characters, in the
        # middle of its HTML: only a description that is complete is kept.
        raw = str(cell(row, "description") or "")
        description = clean_text(raw) if len(raw) < TRUNCATED_AT and "<img" not in raw else ""
        projects.append({
            "number": number_,
            "name": clean(cell(row, "name")),
            "customer": clean(cell(row, "customer")),
            "vat": normalise_vat(cell(row, "vat")),
            "site": site,
            "description": description,
            "description_cut": bool(raw.strip()) and not description,
            "customer_ref": clean(cell(row, "customer_ref")),
            "status": clean(cell(row, "status")),
            "deadline": parse_date(cell(row, "deadline")),
            "responsible": clean(cell(row, "responsible")),
            "total": number(cell(row, "total")),
        })
    return projects


def phase(status):
    """'closed', 'executed' or 'open'."""
    key = _key(status)
    if any(word in key for word in CLOSED_WORDS):
        return "closed"
    if any(word in key for word in EXECUTED_WORDS):
        return "executed"
    return "open"


def match_projects(projects, orders):
    """Find the orders of every project.

    ``orders``: dicts with ``id``, ``names`` (customer names), ``vat``,
    ``total``, ``lines`` (number of priced lines), ``confirmed`` and
    ``project`` (the project number it is linked to already, or None).

    Returns ``(assignment, ambiguous)``: ``assignment`` maps a project number
    on the ids of its orders (projects without a match are left out),
    ``ambiguous`` lists the project numbers for which more than one equally
    good combination was found (the first is taken). Projects are matched in
    file order; an order goes to one project only.
    """
    by_name = {}
    by_vat = {}
    for order in orders:
        for name in order["names"]:
            by_name.setdefault(_key(name), []).append(order)
        if order["vat"]:
            by_vat.setdefault(order["vat"], []).append(order)
    taken = {order["id"]: order["project"] for order in orders if order["project"]}
    assignment = {}
    ambiguous = []
    for project in projects:
        candidates = {o["id"]: o for o in by_name.get(_key(project["customer"]), [])}
        for order in by_vat.get(project["vat"], []) if project["vat"] else []:
            candidates[order["id"]] = order
        candidates = [
            order for order in candidates.values()
            if taken.get(order["id"]) in (None, project["number"])
        ]
        if not candidates:
            continue
        best = None
        best_ones = []
        for size in range(1, min(MAX_ORDERS, len(candidates)) + 1):
            for combo in itertools.combinations(candidates, size):
                # Odoo rounds every line to the cent, the export does not.
                tolerance = AMOUNT_TOLERANCE + LINE_TOLERANCE * sum(
                    order.get("lines", 0) for order in combo
                )
                if abs(sum(order["total"] for order in combo) - project["total"]) > tolerance:
                    continue
                # Prefer the orders linked to this very project, then
                # confirmed orders, then fewer orders.
                score = (
                    sum(1 for order in combo if taken.get(order["id"]) == project["number"]),
                    sum(1 for order in combo if order["confirmed"]),
                    -size,
                )
                if best is None or score > best:
                    best, best_ones = score, [combo]
                elif score == best:
                    best_ones.append(combo)
            if best_ones and best[0] == 0 and size == 1:
                # A single order fits: larger combinations of the same
                # customer only add ambiguity.
                break
        if not best_ones:
            continue
        if len(best_ones) > 1:
            ambiguous.append(project["number"])
        chosen = best_ones[0]
        assignment[project["number"]] = [order["id"] for order in chosen]
        for order in chosen:
            taken[order["id"]] = project["number"]
    return assignment, ambiguous


def guess_teams(responsible, teams):
    """The teams (ids) of a 'verantwoordelijke gebruiker': every part
    ("TEAM 1 + TEAM 2") goes to the team whose name it is or holds; the
    longest name wins ("DRENICA TEAM 2" -> Drenica, not Team 2).
    ``teams``: (id, name) pairs."""
    found = []
    for part in re.split(r"\s\+\s|\s&\s(?=team)", _key(responsible)):
        part = part.strip()
        if not part:
            continue
        hits = [(len(_key(name)), team_id) for team_id, name in teams
                if _key(name) and (_key(name) == part
                                   or re.search(r"\b%s\b" % re.escape(_key(name)), part))]
        if hits:
            team_id = max(hits)[1]
            if team_id not in found:
                found.append(team_id)
    return found


def working_days_window(deadline, days):
    """(first day, last day) of ``days`` working days (Monday-Friday)
    ending on ``deadline`` (moved back to a Friday when it is a weekend)."""
    end = deadline
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    start = end
    remaining = max(1, int(math.ceil(days or 1))) - 1
    while remaining:
        start -= timedelta(days=1)
        if start.weekday() < 5:
            remaining -= 1
    return start, end
