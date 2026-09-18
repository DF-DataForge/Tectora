#!/usr/bin/env python3
"""Generate data/labour_norms.json: the execution time per unit of every works
item, read off the labour lines of the Stuklijst export.

Every kit in ``data/bom_catalog.json`` carries one or two labour lines --
``werkuren construction`` on the build-up works, ``werkuren afbraak`` on the
demolition works, ``werkuren veiligheid`` on the safety measures -- in hours
per unit of the works item. That is Tectora's own time norm, and it is what
``tectora_roof`` needs in "Geschatte tijd per eenheid" (minutes) to estimate a
quotation and size the task Uitvoeringswerken.

The export names its products differently from the catalogue and knows one
product where the price list has a family (one "enkelvoudige dakrandprofiel"
against 28 heights x finishes), so the link is made here by hand, the way the
demo bills of materials are: an export product against the catalogue codes it
stands for, checked against the catalogue before anything is written. The 17
products whose names do match are taken automatically as well.

Per export product the hours of all its kits are summed per kit and the median
over the kits is taken (the variants of one product carry the same labour,
with a few exceptions where the median is the safe middle). Hours become
minutes, rounded to a tenth.

Run from the module root:

    python3 tools/build_labour_norms.py
"""
import importlib.util
import json
import os
import re
import statistics
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, os.pardir)
CATALOG = os.path.join(
    MODULE, os.pardir, "tectora_products", "data", "product_catalog.json"
)
BOM_CATALOG = os.path.join(MODULE, "data", "bom_catalog.json")
OUTPUT = os.path.join(MODULE, "data", "labour_norms.json")

_spec = importlib.util.spec_from_file_location(
    "bom_rules", os.path.join(MODULE, "models", "bom_rules.py")
)
bom_rules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bom_rules)

# A labour line: the werkuren of every kind, and the bare "Afbraakwerken"
# component some demolition kits use instead.
LABOUR = re.compile(r"werkuren|^afbraakwerken$")


def codes(*parts):
    """``codes("S00027-S00033", "S00060")`` -> the list of codes."""
    out = []
    for part in parts:
        if "-" in part:
            first, last = part.split("-")
            prefix = first[0]
            for number in range(int(first[1:]), int(last[1:]) + 1):
                out.append("%s%05d" % (prefix, number))
        else:
            out.append(part)
    return out


# export product -> the works items of the catalogue it is the norm for.
# Grouped as the price list is; the comment gives the hours the export holds.
MAPPING = OrderedDict([
    # --- afbraakwerken -------------------------------------------------------
    ("Verwijderen van de huidige dakbedekking type",
     codes("S00027", "S00028", "S00030-S00033")),                    # 0,20 u/m2
    ("Verwijderen van de sandwichpanelen", codes("S00034")),           # 0,35
    ("Verwijderen van bijkomende lagen roofing(prijs per laag) (m²)",
     codes("S00029")),                                                 # 0,02
    ("Verwijderen van het huidige isolatiepakket", codes("S00035")),   # 0,15
    ("Verwijderen van de huidige dakvloer type: houtvezelplaten (m²)",
     codes("S00036")),                                                 # 0,15
    ("Verwijderen van de huidige houten constructie (balken)",
     codes("S00037")),                                                 # 0,15
    ("verwijderen van de huidige hellingschape (m²)",
     codes("S00038-S00040")),                                          # 0,50
    ("Verwijderen van huidige ballastlaag", codes("S00024")),          # 0,16
    ("Verwijderen van de huidige terrasvloer", codes("S00025", "S00026")),  # 0,38
    ("Verwijderen van de dekstenen/dekpannen (lm)", codes("S00041")),  # 0,18
    ("Verwijderen van asbesthoudende dekstenen (lm)", codes("S00042")),  # 0,50
    ("Verwijderen van de dakrandprofielen", codes("S00043")),          # 0,10
    ("Verwijderen en herplaatsen van de nokpannen", codes("S00044")),  # 0,60
    ("Verwijderen en herplaatsen van de onderste rij pannen",
     codes("S00045")),                                                 # 0,35
    ("Verwijderen en herplaatsen van onderste rij leien", codes("S00046")),  # 0,60
    ("Verwijderen en herplaatsen van de onderste rij sidings",
     codes("S00047")),                                                 # 0,55
    ("Inkorten van de sidings/leien (horizontaal afschijven) ifv plaatsen "
     "solins (lm)", codes("S00048")),                                  # 0,25
    ("Verwijderen wandaansluitprofielen", codes("S00049")),            # 0,08
    ("Verwijderen van de koepelschaal exclusief koepelopstand",
     codes("S00050")),                                                 # 0,30
    ("Verwijderen van de koepelschaal inclusief koepelopstand",
     codes("S00051")),                                                 # 0,50
    ("Verwijderen van houten dakluik (daktoegangskoepel komt in de plaats "
     "hiervan: zie opbouwwerken)", codes("S00052")),                   # 0,75
    ("Verwijderen dakdoorvoer", codes("S00053")),                      # 0,10
    ("Af- en aankoppelen van Airco unit", codes("S00054")),            # 1,00
    ("Verwijderen van Afvoerbuis PVC", codes("S00057")),               # 0,07
    ("Verwijderen van de bakgoot", codes("S00058")),                   # 0,50
    ("Afbraak van de tapbuis", codes("S00059")),                       # 0,30
    ("Voorbereiding van de huidige dakbedekking om als dampscherm te "
     "voldoen", codes("S00060")),                                      # 0,03
    ("Betonboring voor de dakdoorvoer", codes("S00272")),              # 1,15
    ("Volgende boringen", codes("S00273")),                            # 0,70
    ("Boring voor noodspuwer in ytong/facade", codes("S00212")),       # 0,75
    # --- algemene werken en veiligheid ---------------------------------------
    ("Plaatsen van rolstelling (forfait)", codes("S00019")),           # 1,50
    ("Collectieve beschermingsmiddelen type Balustrades",
     codes("S00017", "S00023")),                                       # 0,25 u/m
    ("Leveren en plaatsen van het permanent ankerpunt",
     codes("S00011-S00014", "S00016", "S00337-S00339")),               # 0,375
    # --- hout en plaatmateriaal ----------------------------------------------
    ("Leveren en plaatsen van de draagstructuur van het dak in baddens",
     codes("S00061", "S00062")),                                       # 0,16
    ("Leveren en plaatsen van de hellingslatten - verval van 1cm / m (lm)",
     codes("S00063")),                                                 # 0,05
    ("Leveren en plaatsen van de dakvloer in OSB", codes("S00064", "S00065")),  # 0,28
    ("Leveren en plaatsen van CLS-latten om ophoging van de dakrand te "
     "voorzien om te kunnen isoleren (momenteel gebrek aan hoogte)",
     codes("S00066", "S00067")),                                       # 0,10
    ("[CONCLS] Leveren en plaatsen van CLS-latten om de ophoging van de "
     "koepelopstand te voorzien wegens gebrek aan hoogte ifv de isolatie",
     codes("S00284")),                                                 # 0,10
    ("Leveren en plaatsen van de spouwplank type: multiplex 15mm",
     codes("S00068")),                                                 # 0,20
    ("Leveren en plaatsen van spouwplank Type: garantiemultiplex - Solid "
     "John 15mm", codes("S00069")),                                    # 0,20
    ("Leveren en plaatsen van Trespa", codes("S00479", "S00480")),     # 0,10
    ("Uittimmeren van de dakopening voor de koepel", codes("S00283")),  # 0,15
    ("Uittimmeren van de dakopening voor het nieuwe dakraem", codes("S00324")),  # 0,15
    ("Uittimmeren van de dakopstand (onder lichte helling) voor het nieuwe "
     "dakraem", codes("S00325")),                                      # 0,08
    ("Uitisoleren van de dakopstand voor het dakraem met isolatie van 3cm "
     "dik + verdichting van de opstand met EPDM", codes("S00326")),    # 0,04
    # --- dakopbouw -----------------------------------------------------------
    ("Leveren en plaatsen van dampscherm type:",
     codes("S00122-S00126", "S00404", "S00405")),                      # 0,055
    ("Leveren en plaatsen isolatie type: PIR A-merk (Unilin,Recticel,Idelco)",
     codes("S00131-S00154", "S00340", "S00342", "S00344", "S00346",
           "S00348", "S00350", "S00352", "S00354", "S00356", "S00358",
           "S00360", "S00362", "S00364", "S00366", "S00368", "S00370",
           "S00372", "S00374", "S00376", "S00378", "S00380", "S00382",
           "S00384", "S00386", "S00388", "S00389", "S00494")),         # 0,13
    ("Leveren en plaatsen isolatie type: PIR A-merk (Unilin,Recticel,Idelco) "
     "(m²) met ballast",
     codes("S00341", "S00343", "S00345", "S00347", "S00349", "S00351",
           "S00353", "S00355", "S00357", "S00359", "S00361", "S00363",
           "S00365", "S00367", "S00369", "S00371", "S00373", "S00375",
           "S00377", "S00379", "S00381", "S00383", "S00385", "S00387",
           "S00390")),                                                 # 0,18 (losliggend)
    ("Leveren en plaatsen van de isolatieaanzet thv de opgaande gevel ifv "
     "aansluiting met de gevelisolatie, hoogte 20cm/Dikte isolatie",
     codes("S00127-S00130")),                                          # 0,20
    ("Leveren en plaatsen van de hellingsisolatie", codes("S00155-S00159")),  # 0,25 u/m (ingewerkte goot)
    ("Leveren en plaatsen EPDM verkleefd type:", codes("S00177", "S00178")),  # 0,33
    ("Leveren en plaatsen EPDM Type: Met ballast", codes("S00179", "S00180")),  # 0,15
    ("Leveren en plaatsen van de KIMFIXATIE thv de volledige omranding van "
     "het plat dak. Conform voorschriften van Buildwise (bouwnormen!) (lm)",
     codes("S00182")),                                                 # 0,10
    ("Leveren en plaatsen van de ballastlaag met keien 16/32 inclusief "
     "geotextiel en grindvanger", codes("S00183", "S00468")),          # 0,10
    # --- dakranden -----------------------------------------------------------
    ("Leveren en plaatsen van de 2-delige aluminium dakrandprofielen",
     codes("S00070", "S00071", "S00400")),                             # 0,12
    ("Leveren en plaatsen van binnenhoeken voor bovenstaande 2-delige "
     "dakranden", codes("S00072", "S00336", "S00401")),                # 0,12
    ("Leveren en plaatsen van buitenhoeken voor bovenstaande 2-delige "
     "dakranden", codes("S00335", "S00391", "S00402")),                # 0,12
    ("Leveren en plaatsen van eindstukken voor bovenstaande muurkappen",
     codes("S00403")),                                                 # 0,33
    ("Leveren en plaatsen van het enkelvoudige dakrandprofiel",
     codes("S00073-S00076", "S00406-S00409", "S00413-S00416",
           "S00420-S00423")),                                          # 0,08 (DRB tot 100)
    ("Leveren en plaatsen van de hoge dakrandprofielen DRBS",
     codes("S00077-S00079", "S00410-S00412", "S00417-S00419",
           "S00424-S00426")),                                          # 0,08 (150+)
    ("Leveren en plaatsen van de binnenhoeken voor DRB-dakrandprofiel",
     codes("S00080-S00083", "S00427-S00430", "S00434-S00437",
           "S00440-S00443")),                                          # 0,08
    ("Leveren en plaatsen van de buitenhoek voor DRB-dakrandprofiel",
     codes("S00392-S00395", "S00447-S00450", "S00454-S00457",
           "S00461-S00464")),                                          # 0,08
    ("Leveren en plaatsen van binnenhoeken voor bovenstaande hoge dakranden "
     "DRBS", codes("S00084-S00086", "S00431-S00433", "S00438", "S00439",
                   "S00444-S00446")),                                  # 0,16
    ("Leveren en plaatsen van buitenhoeken voor bovenstaande hoge dakranden "
     "DRBS", codes("S00396-S00398", "S00451-S00453", "S00458-S00460",
                   "S00465-S00467")),                                  # 0,20
    ("Leveren en plaatsen van de dakranden type: zinken kraal",
     codes("S00087", "S00088", "S00481", "S00484", "S00487", "S00490")),  # 0,08
    ("Leveren en plaatsen van de binnenhoeken voor bovenstaande kralen",
     codes("S00089", "S00090", "S00482", "S00486", "S00488", "S00491")),  # 0,10
    ("Leveren en plaatsen van de buitenhoeken voor bovenstaande kralen",
     codes("S00399", "S00483", "S00485", "S00489", "S00492")),         # 0,10
    ("Leveren en plaatsen van de 2-delige aluminium kralen type: ICONIK",
     codes("S00091")),                                                 # 0,10
    ("Leveren en plaatsen van binnenhoeken voor bovenstaande alu-kralen "
     "(ICONIK)", codes("S00092")),                                     # 0,12
    ("Leveren en plaatsen van buitenhoeken voor bovenstaande alu-kralen. "
     "(ICONIK)", codes("S00093")),                                     # 0,12
    ("Leveren en plaatsen van de enkelvoudige aluminium kralen type: AE "
     "28-15/60", codes("S00094")),                                     # 0,09
    ("Leveren en plaatsen van binnenhoeken voor bovenstaande alu-kralen - "
     "AE-28-15-60", codes("S00095")),                                  # 0,12
    ("Leveren en plaatsen van buitenhoek voor bovenstaande alu-kralen - "
     "AE-28-15-60", codes("S00096")),                                  # 0,12
    # --- randaansluitingen ---------------------------------------------------
    ("Randaansluiting type: solins in anthrazink (inslijpen in de muur incl. "
     "plastische elastische voeg) (lm)", codes("S00097")),             # 0,33
    ("Leveren en plaatsen van L-profiel om ophoging van de dakopbouw weg te "
     "werken hoogte 150 mm kleur: idem dakrand =", codes("S00098")),   # 0,10
    ("Randaansluiting type: aansluiting van de EPDM op de slabben die "
     "geplaatst werden door de metser", codes("S00099")),              # 0,15
    ("Randaansluiting type: aansluiting van EPDM onder bestaand lood (lm)",
     codes("S00100")),                                                 # 0,08
    ("Randaansluiting type: aansluiting op het dak van de buren met resitrix",
     codes("S00101")),                                                 # 0,20
    ("Randaansluiting type: aansluiting op het dak van de buren met naadtape",
     codes("S00102")),                                                 # 0,06
    ("Randaansluiting type: aansluiting van de EPDM in de zinken/PVC goot",
     codes("S00103", "S00104")),                                       # 0,20
    ("Randaansluiting type: aansluiting van de EPDM op de dekpannen die "
     "behouden worden met plaklood en naadtape (lm)",
     codes("S00105", "S00106")),                                       # 0,16
    ("Randaansluiting type: aansluiting van de EPDM op de verandaplaten",
     codes("S00107", "S00108")),                                       # 0,25
    ("Randaansluiting type: aansluiting van de EPDM thv de gevelbekleding of "
     "sidings: optrekken EPDM en inslijpen solin (incl. plastische voeg)",
     codes("S00109", "S00110")),                                       # 0,20
    ("Randaansluiting type: onderkapping van de opgaande gevel (=aansluiting "
     "tot op binnenspouwblad en voorzien van stootvoegen) met lood",
     codes("S00111")),                                                 # 0,50
    ("Randaansluiting type: aansluiting met zinken profiel op het onderdak "
     "van het hellend vlak", codes("S00112", "S00113")),               # 0,12
    ("Randaansluiting type: aansluiting van de EPDM thv de lichtstraat",
     codes("S00114")),                                                 # 0,25
    ("Randaansluiting type: aansluiting van de EPDM thv de dorpel aan het "
     "raam/de deur. Nota: inpakken dorpel is hierbij noodzakelijk",
     codes("S00115")),                                                 # 0,30
    ("Leveren en plaatsen slabben in EPDM met een ontvouwing van",
     codes("S00116-S00121")),                                          # 0,10
    # --- doorvoeren en schoorsteen -------------------------------------------
    ("Leveren en plaatsen van geïsoleerde dakdoorvoer",
     codes("S00274-S00279")),                                          # 0,25
    ("Afdichten van de bestaande dakdoorvoer die behouden kan worden",
     codes("S00280")),                                                 # 0,25
    ("Afdichten van de dakdoorvoer geleverd door derden",
     codes("S00281", "S00282")),                                       # 0,75
    ("inpakken van de schouw met EPDM incl. verdichting",
     codes("S00184", "S00187")),                                       # 0,50
    ("Inpakken van de schouw met isolatie 3cm dik & EPDM",
     codes("S00185", "S00188")),                                       # 1,00
    ("Inpakken van de schouw met isolatie 6cm dik & EPDM",
     codes("S00474-S00477")),                                          # 1,00
    ("Inpakken van de schouw met multiplex 15mm dik & EPDM",
     codes("S00186", "S00189")),                                       # 1,00
    # --- regenwaterafvoer ----------------------------------------------------
    ("Leveren en plaatsen van de PE-tapbuis incl. zelfklevende slab",
     codes("S00190-S00196", "S00204-S00209")),                         # 0,50
    ("Leveren en plaatsen van de noodspuwer in PE",
     codes("S00202", "S00210", "S00211")),                             # 0,50
    ("Leveren en plaatsen van de bolrooster / bladvanger type INOX",
     codes("S00197-S00201")),                                          # 0,01
    ("Dichtmetsen van de opening rond de tapbuis (met cement)",
     codes("S00203")),                                                 # 0,75
    ("Leveren en plaatsen van de afvoerbuis in PE", codes("S00246-S00253")),  # 0,25
    ("Leveren en plaatsen van de U-profielen om overheen de ingewerkte "
     "PE-afvoerbuis te plaatsen", codes("S00254-S00265")),             # 0,17 (ingewerkt)
    ("Leveren en plaatsen van afvoerbuis Type: zink rond",
     codes("S00213", "S00215", "S00217", "S00219", "S00221", "S00223",
           "S00225", "S00227")),                                       # 0,16
    ("Leveren en plaatsen van afvoerbuis Type: zink vierkant",
     codes("S00214", "S00216", "S00218", "S00220", "S00222", "S00224",
           "S00226", "S00228")),                                       # 0,16
    ("Leveren en plaatsen van de zinken bocht onderaan de afvoerbuis rond",
     codes("S00229", "S00231", "S00233", "S00235", "S00237", "S00239",
           "S00241", "S00243")),                                       # 0,30
    ("Leveren en plaatsen van de zinken bocht onderaan de afvoerbuis "
     "vierkant",
     codes("S00230", "S00232", "S00234", "S00236", "S00238", "S00240",
           "S00242", "S00244")),                                       # 0,30
    ("Inkorten van de afvoerbuis die uitmondt op het plat dak gezien het "
     "dakoppervlak door de isolatie hoger komt te liggen", codes("S00245")),  # 0,50
    ("Leveren en plaatsen van het gootsysteem breedte 25cm tbv optimale "
     "afwatering naar tapbuis & het behoud van een verlaagde dakrand l/M",
     codes("S00266-S00271")),                                          # 0,25 (plooiwerk)
    # --- koepels, dakramen, terras -------------------------------------------
    ("Afnemen, herverdichten en terugplaatsen van de bestaande koepel",
     codes("S00286")),                                                 # 1,00
    ("Leveren van de draaistok om de koepel manueel open te draaien",
     codes("S00314", "S00315")),                                       # 0,05
    ("Leveren en plaatsen van de kunststof regelbare tegeldragers om de "
     "terrasvloer mooi waterpas te kunnen plaatsen )en om de druk op de "
     "isolatie te verdelen)", codes("S00328-S00332", "S00469")),      # 0,05
    ("leveren en plaatsen van de rubbertegels 50x50", codes("S00056")),  # 0,10
])


def load_catalog():
    with open(CATALOG, encoding="utf-8") as handle:
        data = json.load(handle)
    return {entry["code"]: entry for entry in data["products"]}


def labour_hours(boms):
    """export product -> (median hours per unit over its kits, kits, kinds)."""
    per_product = {}
    for bom in boms:
        hours = 0.0
        kinds = set()
        for line in bom["lines"]:
            if LABOUR.search(bom_rules.norm(line["component"])):
                hours += float(line["qty"])
                kinds.add(line["component"])
        if hours > 0:
            entry = per_product.setdefault(bom["product"], {"hours": [], "kinds": set()})
            entry["hours"].append(hours)
            entry["kinds"] |= kinds
    return {
        product: (statistics.median(entry["hours"]), len(entry["hours"]),
                  sorted(entry["kinds"]))
        for product, entry in per_product.items()
    }


def build(products, norms):
    """Apply the mapping, then the automatic name matches for what is left."""
    out = OrderedDict()
    problems = []
    for source, targets in MAPPING.items():
        if source not in norms:
            problems.append("export product not found or without labour: %s" % source)
            continue
        hours, kits, kinds = norms[source]
        for code in targets:
            entry = products.get(code)
            if entry is None:
                problems.append("%s: unknown code %s" % (source[:40], code))
                continue
            if not entry["is_service"]:
                problems.append("%s: %s is a raw material" % (source[:40], code))
                continue
            if code in out:
                problems.append("%s: %s already set from %s"
                                % (source[:40], code, out[code]["source"]))
                continue
            out[code] = {
                "code": code,
                "product": entry["name"],
                "uom": entry["uom"],
                "minutes": round(hours * 60, 1),
                "hours": round(hours, 4),
                "source": source,
                "kits": kits,
                "kinds": kinds,
                "method": "mapping",
            }
    # The names that do match, for export products the mapping does not name.
    sellable = bom_rules.build_index([
        {"id": code, "code": code, "name": entry["name"]}
        for code, entry in products.items() if entry["is_service"]
    ])
    mapped_sources = set(MAPPING)
    for source, (hours, kits, kinds) in norms.items():
        if source in mapped_sources:
            continue
        score, match = bom_rules.match_product(source, sellable)
        if not match or score < bom_rules.AUTO or match["code"] in out:
            continue
        out[match["code"]] = {
            "code": match["code"],
            "product": match["name"],
            "uom": products[match["code"]]["uom"],
            "minutes": round(hours * 60, 1),
            "hours": round(hours, 4),
            "source": source,
            "kits": kits,
            "kinds": kinds,
            "method": "name (%.2f)" % score,
        }
    return out, problems


def main():
    products = load_catalog()
    with open(BOM_CATALOG, encoding="utf-8") as handle:
        boms = json.load(handle)["boms"]
    norms = labour_hours(boms)
    out, problems = build(products, norms)
    if problems:
        for problem in problems:
            print("FOUT:", problem, file=sys.stderr)
        raise SystemExit("%d problemen, niets weggeschreven" % len(problems))
    entries = sorted(out.values(), key=lambda entry: entry["code"])
    unused = sorted(set(norms) - {entry["source"] for entry in entries})
    data = {
        "source": "Stuklijst_Tectora.xlsx, werkurenregels (via tools/build_labour_norms.py)",
        "norms": entries,
        "stats": {
            "products": len(entries),
            "by_mapping": sum(1 for e in entries if e["method"] == "mapping"),
            "by_name": sum(1 for e in entries if e["method"] != "mapping"),
            "export_products_with_labour": len(norms),
            "export_products_unused": len(unused),
        },
        "unused_export_products": unused,
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    services = sum(1 for entry in products.values() if entry["is_service"])
    print("%(products)s verkoopproducten met een tijdnorm (%(by_mapping)s via "
          "de mapping, %(by_name)s op naam) van %(export_products_with_labour)s "
          "exportproducten met werkuren" % data["stats"])
    print("%d van de %d verkoopproducten gedekt; %d exportproducten zonder "
          "tegenhanger" % (len(entries), services, len(unused)))
    print("geschreven: %s" % os.path.abspath(OUTPUT))


if __name__ == "__main__":
    main()
