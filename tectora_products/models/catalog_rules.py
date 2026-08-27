# -*- coding: utf-8 -*-
"""Classification and normalisation rules for the product catalogue.

Plain Python (no Odoo imports) so both the import wizard and the offline
generator in ``tools/parse_product_export.py`` use the same single source of
truth.

Products are classified with three signals, in order of reliability:

1. an explicit product-category column (when the export has one);
2. the export's product group, mapped onto the existing category tree;
3. keywords in the Dutch product name, then the supplier — whose assortment
   is homogeneous (Bendec sells roof edges, Cintralux domes, ...).
"""
import re
from collections import OrderedDict

PLACEHOLDER_NAMES = ("opnieuw te gebruiken",)

# Median (and modal) sale/purchase ratio of the catalogue's own priced rows.
DEFAULT_MARKUP = 1.85

# Column aliases, lower-cased and stripped. The first hit wins.
COLUMN_ALIASES = OrderedDict([
    ("code", ["interne referentie", "productcode", "default_code", "referentie",
              "artikelcode", "code"]),
    ("name", ["naam nl", "naam", "productnaam", "name", "omschrijving"]),
    ("category", ["productcategorie", "product categorie", "categorie",
                  "product category", "categ_id", "productcategory"]),
    ("group", ["productgroup", "productgroep", "productgroep naam"]),
    ("cost", ["aankoopprijs excl btw", "aankoopprijs", "kostprijs",
              "standard_price", "cost"]),
    ("sale", ["verkoopprijs excl btw", "verkoopprijs", "list_price",
              "sales price"]),
    ("advice", ["adviesprijs voor verkoop excl btw", "adviesprijs"]),
    ("uom", ["eenheid", "maateenheid", "uom", "uom_id"]),
    ("supplier", ["leverancier", "vendor", "supplier"]),
    ("supplier_code", ["productcode leverancier", "leverancierscode",
                       "leveranciercode", "vendor code"]),
    ("barcode", ["ean-nummer", "ean nummer", "ean", "barcode"]),
    ("weight", ["gewicht", "weight"]),
    ("brand", ["merk", "brand"]),
    ("pack", ["aantal stuks per omdoos", "aantal per omdoos", "omdoos"]),
    ("type", ["product type", "producttype", "soort", "type"]),
])

# Raw materials get the same chapter structure, but under their own branch:
# a service can be sold, a raw material cannot, and mixing the two in one
# category makes that impossible to see (and impossible to whitelist per
# category for the drawing's product picker).
GOODS_BRANCH = "Grondstoffen"


def branch_path(path, is_service):
    """The full category path of a product: services keep the chapter path,
    raw materials get the same path under the Grondstoffen branch."""
    path = str(path or "").strip().strip("/")
    if is_service or not path:
        return path
    if path == GOODS_BRANCH or path.startswith(GOODS_BRANCH + "/"):
        return path  # already branched
    return "%s/%s" % (GOODS_BRANCH, path)


def chapter_path(path):
    """The chapter path without the Grondstoffen branch, for comparisons."""
    path = str(path or "").strip().strip("/")
    if path == GOODS_BRANCH:
        return ""
    if path.startswith(GOODS_BRANCH + "/"):
        return path[len(GOODS_BRANCH) + 1:]
    return path


# Category paths under the root category. Existing works categories are
# reused; material families become sub-categories of the build-up chapter.
CATEGORY_PATHS = OrderedDict([
    ("algemene_werken", "01. Algemene werken"),
    ("dakranden", "02. Dakranden"),
    ("veiligheid", "02. Verplichte veiligheidsvoorzieningen"),
    ("afbraak", "03. Afbraakwerken plat dak"),
    ("opbouw", "04. Opbouwwerken plat dak"),
    ("afvoer", "04. Opbouwwerken plat dak/Afvoer"),
    ("isolatie", "04. Opbouwwerken plat dak/Isolatie"),
    ("afdichting", "04. Opbouwwerken plat dak/Afdichting"),
    ("bevestiging", "04. Opbouwwerken plat dak/Bevestigingsmaterialen"),
    ("hout", "04. Opbouwwerken plat dak/Hout & plaatmateriaal"),
    ("doorvoer", "04. Opbouwwerken plat dak/Doorvoeren & schoorsteen"),
    ("gereedschap", "04. Opbouwwerken plat dak/Gereedschap & klein materiaal"),
    ("koepels", "05. Koepels"),
    ("dakramen", "06. Dakramen"),
    ("oversteken", "07. Oversteken"),
    ("terrasvloer", "08. Terrasvloer"),
    ("worst_case", "09. Worst case scenario"),
    ("notas", "10. Algemene nota's"),
    ("garantie", "11. Garantiepakket EPDM Solutions"),
    ("andere", "12. Andere werken"),
    ("upsale", "13. Upsale"),
    # Sub-categories of the demolition chapter, keyed on what gets removed.
    ("afbraak_dakbedekking", "03. Afbraakwerken plat dak/Dakbedekking"),
    ("afbraak_isolatie", "03. Afbraakwerken plat dak/Isolatie & hellingschape"),
    ("afbraak_dakvloer", "03. Afbraakwerken plat dak/Dakvloer & draagstructuur"),
    ("afbraak_ballast", "03. Afbraakwerken plat dak/Ballast & terrasvloer"),
    ("afbraak_dakranden", "03. Afbraakwerken plat dak/Dakranden & muurkappen"),
    ("afbraak_gevel", "03. Afbraakwerken plat dak/Aansluitende dak- & gevelwerken"),
    ("afbraak_afvoer", "03. Afbraakwerken plat dak/Afvoer & doorvoeren"),
    ("afbraak_koepels", "03. Afbraakwerken plat dak/Koepels & dakluiken"),
    ("afbraak_installaties", "03. Afbraakwerken plat dak/Installaties"),
])

# Second stage: once the chapter is known, refine it on the product name.
# Ordered, first match wins; no match leaves the product in the chapter itself
# (which is where the werkuren belong).
SUBCATEGORY_RULES = {
    "afbraak": [
        ("afbraak_koepels", r"koepel|dakluik|lichtstraat"),
        ("afbraak_installaties", r"airco|zonnepane|warmtepomp|antenne|schotel"),
        ("afbraak_afvoer", r"afvoerbuis|tapbuis|dakdoorvoer|spuwer|boring"),
        ("afbraak_dakranden", r"dakrand|dekste|muurkap|solin|wandaansluit"),
        # "rij pannen" without "dak" in front is the same work; the roof-edge
        # rule above already claimed the dekpannen.
        ("afbraak_gevel", r"dakpan|nokpan|\bpannen\b|leien|siding|bakgoot|gevel"),
        ("afbraak_ballast", r"ballast|rolgrind|kiezel|terrasvloer|tegel|dallen|"
                            r"bankirai"),
        # hellingschape / hellingsschape / hellingschappe all occur.
        ("afbraak_isolatie", r"isolatie|hellingsch|chape|afschot"),
        ("afbraak_dakvloer", r"dakvloer|roostering|balken|houtvezelplaat"),
        ("afbraak_dakbedekking", r"dakbedekking|roofing|epdm|pvc|resitrix|"
                                 r"sandwichpanel|zink"),
    ],
}

GROUP_MAP = {
    "ALGEMEEN": "algemene_werken",
    "VEILIGHEID": "veiligheid",
    "AFBRAAK": "afbraak",
    "DAKRANDEN": "dakranden",
    "AFVOER": "afvoer",
    "ISOLATIE": "isolatie",
    "AFDICHTING": "afdichting",
    "BEVESTIGINGSMATERIALEN": "bevestiging",
    "HOUT MASSIEF": "hout",
    "HOUT PLAATWERK": "hout",
    "DOORVOER": "doorvoer",
    "SCHOUW/SCHOORSTEEN": "doorvoer",
    "KOEPELS": "koepels",
    "DAKRAMEN": "dakramen",
    "DAKBELEVING": "terrasvloer",
    "GEREEDSCHAP": "gereedschap",
}
GROUP_IGNORE = {"GEIMPORTEERDE PRODUCTEN", "GEÏMPORTEERDE PRODUCTEN",
                "DIVERSEN", "DIVERS"}

NAME_RULES = [
    ("koepels", r"koepel|skylux|lichtkoepel|lichtstraat|spindel|dakluik|daktoegang"),
    ("dakramen", r"dakra[ae]?m|velux|platdakraam"),
    ("dakranden", r"dakrand|drbs?|drbr|muurkap|kraal|daktrim|binnenhoek|"
                  r"buitenhoek|eindstuk"),
    ("afvoer", r"afvoer|aflooppijp|afleider|bocht|aflopen|hemelwater|tapbuis|"
               r"spuwer|noodoverloop|bladvanger|wavin|wafix|geberit|pp buis|"
               r"steekmof|t-stuk|regenwater|regenpijp|goot|zink"),
    ("isolatie", r"isolatie|utherm|pir |pir-|eps|xps|rockwool|isover|resol|"
                 r"hellingsisolatie|afschot|isolfoam"),
    ("doorvoer", r"doorvoer|schoorsteen|schouw|dakdoorvoer|ventilatie|"
                 r"verluchting|ontluchting"),
    ("afdichting", r"epdm|elevate|resitrix|roofing|bitumen|dampscherm|primer|"
                   r"kleefstof|bladlood|franaglass|franaline|aluflexx|sopra|"
                   r"glasvlies|pb v3|lijm|flashing|slab|\bkit\b|kitpatroon|"
                   r"mastiek|band|folie|membraan|coating|waterdicht|sealant|"
                   r"ms 500|worst"),
    ("veiligheid", r"ankerpunt|wallfix|abs-lock|valbeveiliging|balustrade|"
                   r"harnas|leeflijn|stelling|hoogwerker|weight angel|"
                   r"safetybull|doorfix|veiligheid"),
    ("bevestiging", r"slagplug|plug |plug\b|schroef|bout|nagel|bevestig|ring |"
                    r"moer|tapschroef|parco|reca |bit |zaagblad|boor"),
    ("hout", r"osb|multiplex|douglas|sls |cls |plaatmateriaal|balk|lat |latten|"
             r"spouwplank|houtvezel|triplex|profiply|geschaafd|c24"),
    ("gereedschap", r"borstel|roller|steel |telescoop|beugel|handvat|emmer|"
                    r"gereedschap|mes |spatel|brander|gasfles|kitpistool|pistool"),
    ("terrasvloer", r"terras|tegeldrager|rubbertegel|tegel|dallen|bankirai|"
                    r"vlonder|grind|kiezel|ballast|groendak|substraat|sedum"),
    ("oversteken", r"\boversteek"),
    ("afbraak", r"verwijderen|afbraak|uitbreken|slopen"),
    ("algemene_werken", r"werkuren|transport|werfinrichting|afvalverwerking|"
                        r"container|voorrijd|parkeervergunning|vaste kosten|"
                        r"werftoilet|klein materiaal|forfait"),
]

SUPPLIER_MAP = {
    "BENDEC": "dakranden",
    "BERTEC": "afdichting",
    "ASPHALT EQUIPMENT": "dakranden",
    "MODDE HEULE": "afvoer",
    "DEFRANCQ BOUWSPECIALITEITEN": "afvoer",
    "DEFRANCQ": "afvoer",
    "STG": "afvoer",
    "COFAPRO": "afvoer",
    "CINTRALUX": "koepels",
    "RECA BELUX": "bevestiging",
    "NOGEL": "bevestiging",
    "FRP": "afdichting",
    "VC WOOD": "hout",
    "BRUSH N ROLL": "gereedschap",
    "EYECATCHER": "veiligheid",
    "BRANDSTOFFEN TOON DEGRAUWE": "gereedschap",
}

SUPPLIER_ALIASES = {"DEFRANCQ": "DEFRANCQ BOUWSPECIALITEITEN"}

UOM_RULES = [
    ("m2", r"^\d*\s*(m2|m²)$"),
    ("m", r"^\d*\s*(lm|ml|m)$"),
    ("hour", r"^(uur|u)$"),
    ("day", r"^(per dag|dag)$"),
    ("forfait", r"^(sog|forfait|vh)$"),
    ("kg", r"^kg$"),
]
UOM_NAMES = {
    "unit": "Stuk",
    "m": "m",
    "m2": "m²",
    "kg": "kg",
    "hour": "Uur",
    "day": "Dag",
    "forfait": "Forfait",
}
PLAIN_UNIT_WORDS = {"st", "stk", "stuk", "stuks", "1 stuk", "1stuk", "1lm",
                    "stuk(s)", "unit", "units", "pce"}

# Words that mark a row as a service when the type column is used.
SERVICE_WORDS = {"dienst", "diensten", "service", "services", "werk", "werkuren",
                 "uren", "arbeid", "labour", "labor"}
GOODS_WORDS = {"grondstof", "grondstoffen", "materiaal", "materialen",
               "voorraad", "voorraadproduct", "goods", "product", "artikel",
               "consu", "storable"}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def number(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def normalise_uom(raw):
    unit = clean(raw).lower()
    for key, pattern in UOM_RULES:
        if re.match(pattern, unit):
            return key
    return "unit"


def map_columns(header):
    """Map our logical field names onto the sheet's column indexes."""
    lowered = [clean(cell).lower() for cell in header]
    columns = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                columns[field] = lowered.index(alias)
                break
    return columns


def refine(key, name):
    """Refine a chapter key to one of its sub-categories, on the name.

    Kept separate from ``classify`` so it can also be applied to products that
    were categorised elsewhere -- the price book maps its own chapter keys, and
    already-imported products are re-filed with the same rules.
    """
    rules = SUBCATEGORY_RULES.get(key)
    if not rules:
        return key
    lowered = clean(name).lower()
    for sub_key, pattern in rules:
        if re.search(pattern, lowered):
            return sub_key
    return key


def classify(name, group, supplier):
    """Return (category key, signal) from the group, name and supplier."""
    group = clean(group).upper()
    if group and group not in GROUP_IGNORE:
        key = GROUP_MAP.get(group)
        if key:
            return refine(key, name), "productgroep"
    lowered = clean(name).lower()
    for key, pattern in NAME_RULES:
        if re.search(pattern, lowered):
            return refine(key, name), "naam"
    supplier = clean(supplier).upper()
    if supplier in SUPPLIER_MAP:
        return refine(SUPPLIER_MAP[supplier], name), "leverancier"
    return "andere", "restcategorie"


def is_service_row(row_type, supplier, type_mode):
    """Services are the sales/works items, goods the purchasable materials."""
    if type_mode == "service":
        return True
    if type_mode == "goods":
        return False
    if type_mode == "column":
        value = clean(row_type).lower()
        if value:
            if any(word in value for word in SERVICE_WORDS):
                return True
            if any(word in value for word in GOODS_WORDS):
                return False
    # Automatic: everything that can be purchased carries a supplier.
    return not clean(supplier)


def parse_rows(header, rows, options=None):
    """Turn sheet rows into catalogue entries.

    ``options`` keys: ``category_mode`` ('auto'|'column'), ``type_mode``
    ('auto'|'column'|'service'|'goods'), ``markup`` (float), ``root_category``.
    """
    options = options or {}
    category_mode = options.get("category_mode") or "auto"
    type_mode = options.get("type_mode") or "auto"
    markup = options.get("markup") or DEFAULT_MARKUP
    columns = map_columns(header)
    if "name" not in columns:
        raise ValueError(
            "Geen productnaam-kolom gevonden (verwacht bv. 'naam NL' of 'naam')."
        )

    def cell(row, field):
        index = columns.get(field)
        if index is None or index >= len(row):
            return ""
        return row[index]

    entries = []
    seen_codes = {}
    seen_barcodes = set()
    stats = {"signals": {}, "skipped": 0, "computed_prices": 0,
             "services": 0, "goods": 0, "duplicates": 0}
    suppliers = {}

    for row in rows:
        name = clean(cell(row, "name"))
        if not name or any(word in name.lower() for word in PLACEHOLDER_NAMES):
            stats["skipped"] += 1
            continue
        code = clean(cell(row, "code"))
        if code and code in seen_codes:
            stats["duplicates"] += 1
            continue

        supplier = clean(cell(row, "supplier"))
        supplier = SUPPLIER_ALIASES.get(supplier.upper(), supplier)
        group = clean(cell(row, "group"))

        # Category: an explicit column wins when the user asks for it.
        signal = "kolom"
        category_path = clean(cell(row, "category"))
        if category_mode != "column" or not category_path:
            key, signal = classify(name, group, supplier)
            category_path = CATEGORY_PATHS[key]

        cost = number(cell(row, "cost"))
        sale = number(cell(row, "sale"))
        advice = number(cell(row, "advice"))
        price_source = "verkoopprijs"
        if sale <= 0:
            if advice > 0:
                sale, price_source = advice, "adviesprijs"
            elif cost > 0:
                sale = round(cost * markup, 2)
                price_source = "berekend"
                stats["computed_prices"] += 1
            else:
                price_source = "geen"

        is_service = is_service_row(cell(row, "type"), supplier, type_mode)
        stats["services" if is_service else "goods"] += 1
        stats["signals"][signal] = stats["signals"].get(signal, 0) + 1
        if supplier:
            suppliers[supplier] = suppliers.get(supplier, 0) + 1

        unit_raw = clean(cell(row, "uom"))
        uom = normalise_uom(unit_raw)
        description = []
        if unit_raw and uom == "unit" and unit_raw.lower() not in PLAIN_UNIT_WORDS:
            description.append("Verpakking/eenheid: %s" % unit_raw)
        pack = clean(cell(row, "pack"))
        if pack and pack not in ("0", "1"):
            description.append("Aantal per omdoos: %s" % pack)
        brand = clean(cell(row, "brand"))
        if brand:
            description.append("Merk: %s" % brand)

        barcode = re.sub(r"\D", "", clean(cell(row, "barcode")))
        if barcode and (len(barcode) < 8 or barcode in seen_barcodes):
            barcode = ""
        if barcode:
            seen_barcodes.add(barcode)

        entry = {
            "code": code,
            "name": name[:180],
            "category_path": category_path,
            "category_signal": signal,
            "uom": uom,
            "list_price": round(sale, 2),
            "standard_price": round(cost, 2),
            "price_source": price_source,
            "supplier": supplier,
            "supplier_code": clean(cell(row, "supplier_code")),
            "is_service": is_service,
            "barcode": barcode,
            "weight": number(cell(row, "weight")),
            "description": " · ".join(description),
            "tags": (["Prijs berekend"] if price_source == "berekend" else [])
            + (["Prijs op aanvraag"] if sale <= 0 else []),
        }
        if code:
            seen_codes[code] = entry
        entries.append(entry)

    stats["products"] = len(entries)
    stats["suppliers"] = suppliers
    stats["without_code"] = sum(1 for entry in entries if not entry["code"])
    return entries, stats
