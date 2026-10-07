# -*- coding: utf-8 -*-
"""Generate data/quotation_templates.json from the shipped product catalogue.

Twenty starting points for a flat-roof quotation, ten for a renovation and ten
for new construction. They are written here rather than by hand in JSON so
every product reference is checked against data/product_catalog.json and every
roof edge is paired with the inner and outer corners that belong to it -- a
corner from another profile family is the mistake this file exists to prevent.

Run from the module root:

    python3 tools/build_quotation_templates.py

The quantities describe one reference roof so a freshly picked template already
totals something plausible: 100 m2 of surface, 40 lm of edge with one inner and
four outer corners, and two outlets. Sales overwrites them from the measurement
-- the drawing feeds the quotation -- but a template full of ones would make
the edge and corner lines meaningless.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, os.pardir, "data")
CATALOG = os.path.join(DATA, "product_catalog.json")
OUTPUT = os.path.join(DATA, "quotation_templates.json")

# The reference roof the quantities describe.
AREA = 100.0
PERIMETER = 40.0
INNER_CORNERS = 1.0
OUTER_CORNERS = 4.0
OUTLETS = 2.0

SECTION = "line_section"

# --------------------------------------------------------------- roof edges
# code -> (label, profile, inner corner, outer corner, end cap or None).
# The corners are the ones the catalogue names after this very profile; see
# the "voor bovenstaande" wording in the price list.
EDGES = {
    "alu2d_ral": ("2-delige aluminium dakrand in RAL naar keuze",
                  "S00400", "S00401", "S00402", "S00403"),
    "alu2d_9005": ("2-delige aluminium dakrand in RAL 9005 structuurlak",
                   "S00070", "S00072", "S00391", "S00403"),
    "alu2d_geanodiseerd": ("2-delige aluminium dakrand geanodiseerd",
                           "S00071", "S00336", "S00335", "S00403"),
    "enkel100_ral": ("enkelvoudige dakrand 100 mm in RAL naar keuze",
                     "S00076", "S00083", "S00395", None),
    "enkel150_ral": ("enkelvoudige dakrand 150 mm in RAL naar keuze",
                     "S00077", "S00084", "S00396", None),
    "enkel175_ral": ("enkelvoudige dakrand 175 mm in RAL naar keuze",
                     "S00078", "S00085", "S00397", None),
    "enkel200_ral": ("enkelvoudige dakrand 200 mm in RAL naar keuze",
                     "S00079", "S00086", "S00398", None),
    "enkel150_geanodiseerd": ("enkelvoudige dakrand 150 mm geanodiseerd",
                              "S00410", "S00431", "S00451", None),
    "kraal_naturel": ("zinken kraal in naturel zink",
                      "S00088", "S00090", "S00399", None),
    "kraal_anthra": ("zinken kraal in Anthra zink",
                     "S00487", "S00488", "S00489", None),
    "kraal_quartz": ("zinken kraal in Quartz zink",
                     "S00481", "S00482", "S00483", None),
    "kraal_iconik": ("2-delige aluminium kraal Iconik in RAL",
                     "S00091", "S00092", "S00093", None),
}

# ------------------------------------------------------------- fixed blocks
# Every template opens with the general works and the mandatory safety
# measures, whatever the roof looks like.
GENERAL_RENOVATION = [
    ("S00001", 1.0),          # algemene vaste kosten
    ("S00002", 1.0),          # verticaal transport manueel
    ("S00007", 1.0),          # afvalverwerking forfaitair
]
GENERAL_NEW_BUILD = [
    ("S00001", 1.0),
    ("S00003", 1.0),          # verticaal transport met camionkraan
    ("S00007", 1.0),
]
SAFETY = [
    ("S00012", 2.0),          # permanent ankerpunt ABS-Lock X-SR-B EPDM
    ("S00023", PERIMETER),    # tijdelijke balustrades op de opstand
]
SAFETY_BITUMEN = [
    ("S00338", 2.0),          # hetzelfde ankerpunt, uitvoering voor roofing
    ("S00023", PERIMETER),
]
DRAINAGE = [
    ("S00191", OUTLETS),      # PE-tapbuis dia 75 met zelfklevende slab
    ("S00197", OUTLETS),      # bolrooster dia 80
]
DRAINAGE_BITUMEN = [
    ("S00205", OUTLETS),      # PE-tapbuis dia 75 met roofingslab
    ("S00197", OUTLETS),
]
# Offered on every quotation, priced only when the site asks for it.
OPTIONS_COMMON = [
    ("S00009", 1.0),          # parkeervergunning / inname openbaar domein
    ("S00018", PERIMETER),    # stelling
    ("S00020", 1.0),          # keuren van de stelling
    ("S00010", 1.0),          # hoogwerker per dag
    ("S00202", 1.0),          # PE-noodspuwer dia 50
    ("S00248", 6.0),          # afvoerbuis PE dia 75
]
OPTIONS_SKYLIGHT = [
    ("S00287", 1.0),          # koepelschaal acrylaat dubbelwandig
    ("S00306", 1.0),          # vaste PVC koepelopstand
]
OPTIONS_ROOF_WINDOW = [
    ("S00325", 4.0),          # dakopstand voor het Dakraem
    ("S00327", 1.0),          # dakraam op maat
]

# ------------------------------------------------------------- the templates
# Each entry: the roof it describes, then the layers from the deck upwards.
# "demolition" is what comes off first and is what separates a renovation from
# new construction; everything else is shared.
TEMPLATES = [
    # ------------------------------------------------------------ renovatie
    {
        "key": "renovatie_roofing1_pir12_alu2d",
        "name": "Renovatie plat dak - roofing 1 laag, PIR 12 cm, "
                "EPDM 1,1 mm, 2-delige dakrand",
        "kind": "renovatie",
        "demolition": [("S00027", AREA), ("S00043", PERIMETER),
                       ("S00059", OUTLETS), ("S00060", AREA)],
        "vapour": "S00404",
        "insulation": "S00139",
        "membrane": "S00177",
        "edge": "alu2d_ral",
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "renovatie_roofing2_pir14_alu2d_9005",
        "name": "Renovatie plat dak - roofing 2 lagen, PIR 14 cm, "
                "EPDM 1,1 mm, 2-delige dakrand RAL 9005",
        "kind": "renovatie",
        "demolition": [("S00028", AREA), ("S00043", PERIMETER),
                       ("S00049", 8.0), ("S00059", OUTLETS), ("S00060", AREA)],
        "vapour": "S00405",
        "insulation": "S00140",
        "membrane": "S00177",
        "edge": "alu2d_9005",
        "extras": [("S00097", 8.0)],   # nieuwe solins in anthrazink
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "renovatie_epdm_pir16_enkel100",
        "name": "Renovatie plat dak - bestaande EPDM, PIR 16 cm, "
                "EPDM 1,5 mm, enkelvoudige dakrand 100 mm",
        "kind": "renovatie",
        "demolition": [("S00031", AREA), ("S00035", AREA),
                       ("S00043", PERIMETER), ("S00059", OUTLETS)],
        "vapour": "S00123",
        "insulation": "S00141",
        "membrane": "S00178",
        "edge": "enkel100_ral",
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "renovatie_grinddak_pir14_hoog150",
        "name": "Renovatie grinddak - PIR 14 cm, EPDM 1,1 mm geballast, "
                "dakrand 150 mm",
        "kind": "renovatie",
        "demolition": [("S00024", AREA), ("S00028", AREA),
                       ("S00043", PERIMETER), ("S00059", OUTLETS)],
        "vapour": "S00405",
        "insulation": "S00140",
        "membrane": "S00179",
        "edge": "enkel150_ral",
        # Geballast: het grind hoort bij de dakopbouw, niet bij de opties.
        "cover": [("S00183", AREA), ("S00468", PERIMETER)],
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "renovatie_zink_pir16_kraal_naturel",
        "name": "Renovatie plat dak - zinken bedekking, nieuwe dakvloer, "
                "PIR 16 cm, EPDM 1,5 mm, zinken kraal",
        "kind": "renovatie",
        "demolition": [("S00033", AREA), ("S00036", AREA),
                       ("S00043", PERIMETER), ("S00059", OUTLETS)],
        "deck": [("S00064", AREA)],    # nieuwe dakvloer OSB 18 mm
        "vapour": "S00404",
        "insulation": "S00141",
        "membrane": "S00178",
        "edge": "kraal_naturel",
        "extras": [("S00068", 12.0)],  # spouwplaat multiplex 15 mm
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "renovatie_roofing2_pir18_iconik",
        "name": "Renovatie plat dak - roofing 2 lagen, PIR 18 cm, "
                "EPDM 1,5 mm, aluminium kraal Iconik",
        "kind": "renovatie",
        "demolition": [("S00028", AREA), ("S00043", PERIMETER),
                       ("S00049", 8.0), ("S00059", OUTLETS), ("S00060", AREA)],
        "vapour": "S00405",
        "insulation": "S00142",
        "membrane": "S00178",
        "edge": "kraal_iconik",
        "extras": [("S00068", 12.0)],
        "options": OPTIONS_ROOF_WINDOW,
    },
    {
        "key": "renovatie_dakterras_pir16_hoog175",
        "name": "Renovatie dakterras - PIR 16 cm, EPDM 1,5 mm, "
                "keramische tegels, dakrand 175 mm",
        "kind": "renovatie",
        "demolition": [("S00025", AREA), ("S00028", AREA),
                       ("S00043", PERIMETER), ("S00059", OUTLETS)],
        "vapour": "S00405",
        "insulation": "S00141",
        "membrane": "S00178",
        "edge": "enkel175_ral",
        "finish": [("S00330", AREA), ("S00333", AREA)],
        "options": OPTIONS_COMMON,
    },
    {
        "key": "renovatie_sandwich_roofing_pir14_enkel150",
        "name": "Renovatie plat dak - sandwichpanelen, PIR 14 cm, "
                "2-laagse roofing, dakrand 150 mm geanodiseerd",
        "kind": "renovatie",
        "demolition": [("S00034", AREA), ("S00043", PERIMETER),
                       ("S00059", OUTLETS)],
        "deck": [("S00065", AREA)],    # dakvloer OSB 22 mm
        "vapour": "S00122",
        "insulation": "S00140",
        "membrane": "S00181",          # Soprema 2-laagse bitumineuze roofing
        "edge": "enkel150_geanodiseerd",
        "bitumen": True,
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "renovatie_rockwool16_alu2d_geanodiseerd",
        "name": "Renovatie plat dak - Rockwool 16 cm (onbrandbaar), "
                "EPDM 1,5 mm, 2-delige dakrand geanodiseerd",
        "kind": "renovatie",
        "demolition": [("S00028", AREA), ("S00043", PERIMETER),
                       ("S00059", OUTLETS), ("S00060", AREA)],
        "vapour": "S00405",
        "insulation": "S00171",        # Rockwool Rhinoxx 16 cm
        "membrane": "S00178",
        "edge": "alu2d_geanodiseerd",
        "options": OPTIONS_COMMON,
    },
    {
        "key": "renovatie_bijgebouw_pir12_kraal_anthra",
        "name": "Renovatie bijgebouw - roofing 1 laag, PIR 12 cm, "
                "EPDM 1,1 mm, zinken kraal Anthra",
        "kind": "renovatie",
        "demolition": [("S00027", AREA), ("S00043", PERIMETER),
                       ("S00057", 6.0), ("S00059", 1.0)],
        "vapour": "S00404",
        "insulation": "S00139",
        "membrane": "S00177",
        "edge": "kraal_anthra",
        "outlets": 1.0,
        "options": OPTIONS_COMMON,
    },
    # ------------------------------------------------------------ nieuwbouw
    {
        "key": "nieuwbouw_pir14_alu2d_ral",
        "name": "Nieuwbouw plat dak - PIR 14 cm, EPDM 1,1 mm, "
                "2-delige dakrand in RAL",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00140",
        "membrane": "S00177",
        "edge": "alu2d_ral",
        "extras": [("S00068", 12.0)],
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "nieuwbouw_pir16_alu2d_geanodiseerd",
        "name": "Nieuwbouw plat dak - PIR 16 cm, EPDM 1,5 mm, "
                "2-delige dakrand geanodiseerd",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00141",
        "membrane": "S00178",
        "edge": "alu2d_geanodiseerd",
        "extras": [("S00068", 12.0)],
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "nieuwbouw_pir18_enkel100",
        "name": "Nieuwbouw plat dak - PIR 18 cm, EPDM 1,5 mm, "
                "enkelvoudige dakrand 100 mm",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00142",
        "membrane": "S00178",
        "edge": "enkel100_ral",
        "extras": [("S00130", PERIMETER)],   # aanzet muurisolatie 16 cm
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "nieuwbouw_pir20_hoog200",
        "name": "Nieuwbouw plat dak - PIR 20 cm, EPDM 1,5 mm, "
                "dakrand 200 mm",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00143",
        "membrane": "S00178",
        "edge": "enkel200_ral",
        "extras": [("S00130", PERIMETER)],
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "nieuwbouw_pir16_kraal_naturel",
        "name": "Nieuwbouw plat dak - PIR 16 cm, EPDM 1,5 mm, "
                "zinken kraal in naturel zink",
        "kind": "nieuwbouw",
        "deck": [("S00064", AREA)],
        "vapour": "S00404",
        "insulation": "S00141",
        "membrane": "S00178",
        "edge": "kraal_naturel",
        "extras": [("S00068", 12.0)],
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "nieuwbouw_pir18_iconik",
        "name": "Nieuwbouw plat dak - PIR 18 cm, EPDM 1,5 mm, "
                "aluminium kraal Iconik",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00142",
        "membrane": "S00178",
        "edge": "kraal_iconik",
        "extras": [("S00069", 12.0)],  # spouwplaat Solid John 15 mm
        "options": OPTIONS_ROOF_WINDOW,
    },
    {
        "key": "nieuwbouw_pir16_geballast_hoog150",
        "name": "Nieuwbouw plat dak - PIR 16 cm, EPDM 1,1 mm geballast, "
                "dakrand 150 mm",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00141",
        "membrane": "S00179",
        "edge": "enkel150_ral",
        "cover": [("S00183", AREA), ("S00468", PERIMETER)],
        "options": OPTIONS_SKYLIGHT,
    },
    {
        "key": "nieuwbouw_dakterras_pir18_hoog175",
        "name": "Nieuwbouw dakterras - PIR 18 cm, EPDM 1,5 mm, "
                "keramische tegels, dakrand 175 mm",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00142",
        "membrane": "S00180",          # geballast: de tegelvloer ligt erop
        "edge": "enkel175_ral",
        "finish": [("S00330", AREA), ("S00333", AREA)],
        "options": OPTIONS_COMMON,
    },
    {
        "key": "nieuwbouw_rockwool16_enkel150",
        "name": "Nieuwbouw industriedak - Rockwool 16 cm (onbrandbaar), "
                "EPDM 1,5 mm, dakrand 150 mm geanodiseerd",
        "kind": "nieuwbouw",
        "vapour": "S00405",
        "insulation": "S00171",
        "membrane": "S00178",
        "edge": "enkel150_geanodiseerd",
        "options": OPTIONS_COMMON,
    },
    {
        "key": "nieuwbouw_carport_pir10_kraal_quartz",
        "name": "Nieuwbouw carport of bijgebouw - PIR 10 cm, EPDM 1,1 mm, "
                "zinken kraal Quartz",
        "kind": "nieuwbouw",
        "deck": [("S00064", AREA)],
        "vapour": "S00404",
        "insulation": "S00138",
        "membrane": "S00177",
        "edge": "kraal_quartz",
        "outlets": 1.0,
        "options": OPTIONS_COMMON,
    },
]

TERMS = (
    "<p>Prijzen zijn geldig gedurende 30 dagen en exclusief btw. De "
    "hoeveelheden worden bevestigd na opmeting ter plaatse; de eindafrekening "
    "gebeurt volgens de werkelijk uitgevoerde hoeveelheden.</p>"
    "<p>Werkuren in regie worden aangerekend aan het geldende uurtarief. "
    "Onvoorziene werken (bijkomende lagen dakbedekking, aangetaste "
    "draagstructuur, ...) worden vooraf gemeld en in meerwerk opgenomen.</p>"
)


def load_catalog():
    with open(CATALOG, encoding="utf-8") as handle:
        data = json.load(handle)
    return {entry["code"]: entry for entry in data["products"]}


def line(products, code, quantity, optional=False):
    entry = products[code]
    return {
        "code": code,
        "quantity": round(float(quantity), 2),
        "optional": optional,
        # Kept for the review of this file only; the loader reads the code.
        "label": entry["name"],
        "uom": entry["uom"],
        "price": entry["list_price"],
    }


def section(name, optional=False):
    return {"section": name, "optional": optional}


def build_one(spec, products):
    renovation = spec["kind"] == "renovatie"
    outlets = spec.get("outlets", OUTLETS)
    bitumen = spec.get("bitumen", False)
    label, profile, inner, outer, cap = EDGES[spec["edge"]]

    lines = [section("Algemene werken")]
    general = GENERAL_RENOVATION if renovation else GENERAL_NEW_BUILD
    lines += [line(products, code, qty) for code, qty in general]

    lines.append(section("Verplichte veiligheidsvoorzieningen"))
    safety = SAFETY_BITUMEN if bitumen else SAFETY
    lines += [line(products, code, qty) for code, qty in safety]

    if renovation:
        lines.append(section("Afbraakwerken"))
        lines += [line(products, code, qty) for code, qty in spec["demolition"]]

    lines.append(section("Dakopbouw"))
    for code, qty in spec.get("deck", []):
        lines.append(line(products, code, qty))
    lines.append(line(products, spec["vapour"], AREA))
    lines.append(line(products, spec["insulation"], AREA))
    lines.append(line(products, spec["membrane"], AREA))
    lines.append(line(products, "S00182", PERIMETER))   # kimfixatie
    for code, qty in spec.get("cover", []):
        lines.append(line(products, code, qty))

    lines.append(section("Dakranden en hoeken"))
    for code, qty in spec.get("extras", []):
        lines.append(line(products, code, qty))
    lines.append(line(products, profile, PERIMETER))
    lines.append(line(products, inner, INNER_CORNERS))
    lines.append(line(products, outer, OUTER_CORNERS))
    if cap:
        lines.append(line(products, cap, 2.0))

    if spec.get("finish"):
        lines.append(section("Terrasafwerking"))
        lines += [line(products, code, qty) for code, qty in spec["finish"]]

    lines.append(section("Regenwaterafvoer"))
    drainage = DRAINAGE_BITUMEN if bitumen else DRAINAGE
    lines += [line(products, code, outlets) for code, _qty in drainage]

    options = spec.get("options", [])
    if options is not OPTIONS_COMMON:
        options = list(options) + list(OPTIONS_COMMON)
    lines.append(section("Opties", optional=True))
    lines += [line(products, code, qty, optional=True) for code, qty in options]

    return {
        "key": spec["key"],
        "name": spec["name"],
        "kind": spec["kind"],
        "edge": spec["edge"],
        "edge_label": label,
        "number_of_days": 30,
        "note": TERMS,
        "lines": lines,
    }


def check(templates, products):
    """Fail loudly rather than ship a template that quotes the wrong thing."""
    problems = []
    seen_keys = set()
    seen_names = set()
    for template in templates:
        if template["key"] in seen_keys:
            problems.append("duplicate key %s" % template["key"])
        seen_keys.add(template["key"])
        if template["name"] in seen_names:
            problems.append("duplicate name %s" % template["name"])
        seen_names.add(template["name"])
        codes = [item["code"] for item in template["lines"] if "code" in item]
        for code in codes:
            entry = products.get(code)
            if entry is None:
                problems.append("%s: unknown code %s" % (template["key"], code))
            elif not entry["is_service"]:
                problems.append(
                    "%s: %s is a raw material, not a works item"
                    % (template["key"], code)
                )
        if len(codes) != len(set(codes)):
            duplicates = sorted({c for c in codes if codes.count(c) > 1})
            problems.append(
                "%s: repeated lines %s" % (template["key"], ", ".join(duplicates))
            )
        # The mandatory blocks.
        if "S00001" not in codes:
            problems.append("%s: no general works" % template["key"])
        if not ({"S00012", "S00338"} & set(codes)):
            problems.append("%s: no mandatory safety" % template["key"])
        demolition = [c for c in codes if products[c]["category_path"].startswith("03.")]
        if template["kind"] == "renovatie" and not demolition:
            problems.append("%s: renovation without demolition" % template["key"])
        if template["kind"] == "nieuwbouw" and demolition:
            problems.append(
                "%s: new build with demolition (%s)"
                % (template["key"], ", ".join(demolition))
            )
        # A section is a section: no product, no quantity.
        for item in template["lines"]:
            if "section" in item and "code" in item:
                problems.append("%s: section carries a product" % template["key"])
    problems += check_edges(products)
    return problems


def check_edges(products):
    """Every corner must name the profile family it was made for."""
    problems = []
    for key, (_label, profile, inner, outer, cap) in EDGES.items():
        for code in (profile, inner, outer) + ((cap,) if cap else ()):
            if code not in products:
                problems.append("edge %s: unknown code %s" % (key, code))
        if any(code not in products for code in (profile, inner, outer)):
            continue
        if products[profile]["uom"] != "m":
            problems.append("edge %s: profile %s is not sold per lm" % (key, profile))
        for code, side in ((inner, "binnenhoek"), (outer, "buitenhoek")):
            name = products[code]["name"].lower()
            if side not in name:
                problems.append(
                    "edge %s: %s is not a %s" % (key, code, side)
                )
            if not shares_family(products[profile]["name"], products[code]["name"]):
                problems.append(
                    "edge %s: corner %s does not match profile %s"
                    % (key, code, profile)
                )
    return problems


FAMILY_WORDS = {
    "2-delige", "enkelvoudige", "kralen", "kraal", "dakranden",
    "dakrandprofielen", "iconik", "naturel", "anthra", "quartz",
    "geanodiseerd", "brut", "structuurlak", "aluminium", "zinken",
    "45mm", "60mm", "80mm", "100mm", "150mm", "175mm", "200mm", "9005",
}
# The catalogue spells the same finish both ways.
SPELLINGS = {"stuctuurlak": "structuurlak"}


def words(name):
    found = {w for w in re.split(r"[^\w,]+", name.lower()) if w}
    found = {SPELLINGS.get(word, word) for word in found}
    return found & FAMILY_WORDS


def shares_family(profile_name, corner_name):
    """The corner carries the same distinguishing words as its profile.

    'binnenhoek voor de enkelvoudige dakrandprofielen hoogte: 150mm in RAL naar
    keuze' belongs to 'enkelvoudige dakrandprofielen hoogte: 150mm in RAL naar
    keuze'; the 200mm corner does not. Only the words that actually separate
    one family from another are compared -- the profile says "dakranden" where
    the corner says "dakrandprofielen", so a plain equality never holds.
    """
    profile = words(profile_name)
    corner = words(corner_name)
    sizes = {"45mm", "60mm", "80mm", "100mm", "150mm", "175mm", "200mm"}
    if (profile & sizes) != (corner & sizes):
        return False
    finishes = {"naturel", "anthra", "quartz", "geanodiseerd", "brut",
                "structuurlak", "9005", "iconik"}
    if (profile & finishes) != (corner & finishes):
        return False
    shapes = {"kralen", "kraal"}
    if bool(profile & shapes) != bool(corner & shapes):
        return False
    if ("enkelvoudige" in profile) != ("enkelvoudige" in corner):
        return False
    if ("2-delige" in profile) != ("2-delige" in corner):
        return False
    return True


def main():
    products = load_catalog()
    templates = [build_one(spec, products) for spec in TEMPLATES]
    problems = check(templates, products)
    if problems:
        for problem in problems:
            sys.stderr.write("ERROR %s\n" % problem)
        return 1
    payload = {
        "source": "product_catalog.json",
        "reference_roof": {
            "area": AREA,
            "perimeter": PERIMETER,
            "inner_corners": INNER_CORNERS,
            "outer_corners": OUTER_CORNERS,
            "outlets": OUTLETS,
        },
        "templates": templates,
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=False)
        handle.write("\n")
    total = sum(len(t["lines"]) for t in templates)
    renovation = sum(1 for t in templates if t["kind"] == "renovatie")
    print("%s templates (%s renovatie, %s nieuwbouw), %s lines -> %s"
          % (len(templates), renovation, len(templates) - renovation,
             total, OUTPUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
