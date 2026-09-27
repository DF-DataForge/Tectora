#!/usr/bin/env python3
"""Generate data/demo_boms.json: demo bills of materials on the works items.

The real export (data/bom_catalog.json) names its components by variant name
and its quantities in packaging units, so only a quarter of it can be loaded
with confidence -- and what does load is mostly labour lines. That is not
enough to show what the material list does. This file builds, from the
catalogue itself, one complete bill of materials per works item that has a
counterpart among the raw materials: the membrane with its adhesive, tape,
primer and sealant; the insulation with its foam or its screws and plates;
a roof edge with its profile, couplers, screws and sealant; an outlet with its
primer and sealant, a downpipe with its hooks, and so on.

Every quantity is a consumption norm per unit of the works item (per m2, per
lm, per piece) in the unit of the raw material as the catalogue carries it,
which is exactly what mrp.bom expects. The norms are the usual roofer's
figures (10% overlap and cutting loss on a membrane, 3% on insulation, a
20-litre pot of bonding adhesive per 60-65 m2, one Isolfoam can per 7 m2, a
coupler per 3 m profile, a hook per 1,7 m of downpipe, ...), rounded to what
a crew would actually count. Labour is deliberately left out: the material
list is what the crew loads on the van, and hours are tracked on the project.

Run from the module root:

    python3 tools/build_demo_boms.py

Every code is checked against tectora_products/data/product_catalog.json --
the parent must be a works item (service), every component a raw material
(goods) -- and the expected article name is checked for the codes that are
easy to mix up (a 150 mm profile in the wrong finish is exactly the mistake
this exists to prevent). On any problem nothing is written.
"""
import json
import os
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, os.pardir)
CATALOG = os.path.join(
    MODULE, os.pardir, "tectora_products", "data", "product_catalog.json"
)
OUTPUT = os.path.join(MODULE, "data", "demo_boms.json")

# The BoM reference every demo bill of materials carries, so it is tellable
# apart from the imported export and from what the office makes by hand.
REFERENCE = "Demo"

# ------------------------------------------------------------ raw materials
# Named the way a roofer would say them, so a recipe below reads as a list of
# what goes on the van. The code is the catalogue's internal reference.

# EPDM and its accessories (Elevate, via Modde Heule)
EPDM_11 = "P00444"            # EPDM 1,1 mm, rol 15,25 x 30,5 m (m2)
EPDM_15 = "P00442"            # EPDM 1,5 mm, rol 15,25 x 30,5 m (m2)
EPDM_STROOK = "P00458"        # EPDM 1,1 mm, rol 1,68 x 30,5 m (m2), detailwerk
BONDING = "P00459"            # Bonding adhesive BA-2012, pot 20 l
SPLICE_3 = "P00461"           # Splice tape 3" (7,62 cm), per m
SPLICE_6 = "P00537"           # QuickSeam splice tape 6" (15,2 cm), per m
QUICKPRIME = "P00462"         # QuickPrime Plus, gallon 3,8 l
LAP_SEALANT = "P00539"        # Lap sealant, koker
FORMFLASH_22 = "P00471"       # FormFlash zelfklevend 22 cm, per m
FORMFLASH_30 = "P00472"       # FormFlash zelfklevend 30 cm, per m
SA_FLASHING_45 = "P00540"     # EPDM zelfklevende flashing 45 cm, per m
PIPE_FLASHING = "P00533"      # QuickSeam pipe flashing 25-152 mm
WATERBLOCK = "P00543"         # Water block seal
RMA_STRIP = "P01349"          # RMA strip 25 cm, per m (over de batten bar)
BATTEN_BAR = "P00463"         # Batten bar kimfixatie, per m
SILIRUB = "P01077"            # Soudal Silirub EPDM zwart 310 ml

# Bitumen (Soprema, via Modde Heule; Franaline via Defrancq)
SOPRASTICK_VENTI = "P00474"   # zelfklevende onderlaag (m2)
SOPRALENE_TECHNO = "P00475"   # toplaag met leislag, zwart (m2)
SOPRAGLASS_V3 = "P00473"      # dampscherm klasse E3 (m2)
SOPRAGLASS_V4 = "P00542"      # dampscherm klasse E4 (m2)
BITUMEN_PRIMER = "P01335"     # sneldrogende bitumenprimer, pot 25 l
ALUFLEXX = "P01333"           # Franaline Aluflexx zwart 32 cm, rol 5 m
RESITRIX = "P01332"           # Resitrix SKW full bond, rol 1 x 10 m
RESITRIX_PRIMER = "P00493"    # Resitrix hechtprimer FG35, bus 12,5 kg

# Vapour barriers
DBR = "P01434"                # Bauder DBR, zelfklevend op hout (m2)
KSD = "P01435"                # Bauder KSD, zelfklevend op beton (m2)
SA_PRIMER = "P01436"          # hechtprimer zelfklevende folies, drukvat 13,7 l
ALUTRIX = "P01057"            # Alutrix 600 (m2)
PE_FOLIE = "P00536"           # PE dampscherm 50 x 2 m (m2)

# Ballast
GRIND = "P01066"              # keien rolgrind 16/32 (kg)
GEOTEXTIEL = "P01425"         # geotextiel 300 g, rol 2 x 50 m
GRINDVANGER = "P01438"        # alu grindvangprofiel 6 cm, per m

# Insulation
ISOLFOAM = "P01023"           # Isolfoam lijmschuim 750 ml (7 m2 per bus)
PIR = {                       # Utherm Roof L 600 x 1200, per dikte in mm (m2)
    20: "P00528", 30: "P00527", 40: "P00509", 50: "P00508", 60: "P00507",
    70: "P00526", 80: "P00506", 100: "P00513", 120: "P00512", 140: "P00511",
    160: "P00510", 180: "P00525", 200: "P00524",
}
PIR_SPONNING = {              # Utherm Flat Roof L 1200 x 2400 met sponning (m2)
    100: "P00529", 120: "P00530", 140: "P00531", 160: "P00532",
}
ROCKWOOL = {                  # Rockwool Rhinoxx 1000 x 600, per dikte in mm (m2)
    50: "P01078", 60: "P01079", 70: "P01080", 80: "P01081", 90: "P01082",
    100: "P01083", 110: "P01084", 120: "P01085", 130: "P01086", 140: "P01087",
    150: "P01088", 160: "P01089",
}
ISO_SCREW = {                 # isolatieschroeven 4,8 mm, per lengte in mm
    60: "P01424", 80: "P01423", 100: "P01417", 140: "P01418", 180: "P01419",
    220: "P01420", 260: "P01421", 300: "P01422",
}
ISO_PLAATJE = "P01416"        # isolatieplaatjes / onderlegringen 70 mm

# Fasteners and small material
SCHROEF_45x45 = "P00988"      # Parco schroef 4,5 x 45 TX25
SCHROEF_5x60 = "P00989"       # Parco schroef 5 x 60 TX25
SCHROEF_6x130 = "P00992"      # Parco schroef 6 x 130 TX30
SCHROEF_6x180 = "P00994"      # Parco schroef 6 x 180 TX30
SLAGPLUG_6x40 = "P00979"      # Parco slagplug 6 x 40
PIANO_42x25 = "P00999"        # Parco pianos 4,2 x 25 (zink en alu plooiwerk)
SCHIJFBLAD = "P01016"         # doorslijpschijf 125 mm inox (inslijpen solins)

# Timber and boards
OSB_18 = "P00623"             # OSB 3 18 mm tand & groef (m2)
OSB_22 = "P01364"             # OSB 3 22 mm tand & groef (m2)
MULTIPLEX_15 = "P01350"       # multiplex meranti 15 mm (m2)
SOLID_JOHN_15 = "P01062"      # Solid John spouwplaat 15 mm (m2)
CLS = "P01351"                # CLS 38 x 58 geschaafd geimpregneerd, per m
BADDENS_18x7 = "P01353"       # baddens 18 x 7 cm douglas, per m
BALKSCHOEN = "P01340"         # balkschoen type A 63 x 100

# Safety
ANKER_XSRB = "P01400"         # ankerpunt ABS-Lock X-SR-B (beton)
ANKER_T21 = "P01401"          # ankerpunt ABS-Lock T-21 (steeldeck)
ANKER_XH16 = "P01402"         # ankerpunt ABS-Lock X-H-16 (hout)
ANKER_LOOP = "P01204"         # ankerpunt ABS-Lock Loop
WALLFIX = "P01208"            # Wallfix
WALLFIX_BOUT = "P01399"       # M10 ankerbouten voor Wallfix
MANCHET_BITUMEN_48 = "P01182"  # afdichtingsmanchet < 48 mm, bitumen granulaat

# Drainage
PE_TAPBUIS_SA = {             # Elevate PE afvoer met zelfklevende slab, L 60 cm
    50: "P00465", 63: "P01053", 75: "P00466", 90: "P00467", 110: "P00468",
    125: "P00469", 160: "P00470", 200: "P01058",
}
PE_TAPBUIS_ROOFING = {        # PE afvoer met roofingslab, L 60 cm
    50: "P00501", 75: "P00500", 90: "P00499", 110: "P00504", 125: "P00503",
    160: "P00502",
}
ALU_SPUWER_ROOFING = "P00505"  # Soprema Draini alu spuwer 50 met roofingslab
BOLROOSTER = {80: "P01440", 100: "P01442", 120: "P01441", 150: "P01443",
              200: "P01444"}  # bladvanger (bolrooster) galva
PE_BUIS = {                   # Geberit PE buis, per m
    50: "P00603", 63: "P01384", 75: "P00604", 90: "P00605", 110: "P00613",
    125: "P00614", 160: "P01386", 200: "P01387",
}
PE_BEUGEL = {                 # Geberit galva beugel M8/M10
    50: "P00608", 63: "P01385", 75: "P00621", 90: "P00609", 110: "P00602",
    125: "P00615",
}
PE_MOF = {                    # Geberit elektrolasmof
    50: "P00594", 63: "P00595", 75: "P00596", 90: "P00597", 110: "P00607",
    125: "P00606",
}
# (kleur, vorm, maat) -> buis per m, scharnierhaak, bocht onderaan
ZINK_BUIS = {
    ("naturel", "rond", 80): "P00400", ("naturel", "vierkant", 80): "P00407",
    ("naturel", "rond", 100): "P00415", ("naturel", "vierkant", 100): "P00419",
    ("anthra", "rond", 80): "P00413", ("anthra", "vierkant", 80): "P00408",
    ("anthra", "rond", 100): "P00416", ("anthra", "vierkant", 100): "P00420",
    ("quartz", "rond", 80): "P00403", ("quartz", "vierkant", 80): "P00405",
    ("quartz", "rond", 100): "P00414", ("quartz", "vierkant", 100): "P00418",
    ("koper", "rond", 80): "P00401", ("koper", "vierkant", 80): "P00402",
    ("koper", "rond", 100): "P00422", ("koper", "vierkant", 100): "P00423",
}
HAAK = {
    ("naturel", "rond", 80): "P01285", ("naturel", "vierkant", 80): "P01264",
    ("naturel", "rond", 100): "P01295", ("naturel", "vierkant", 100): "P01398",
    ("anthra", "rond", 80): "P01289", ("anthra", "vierkant", 80): "P01239",
    ("anthra", "rond", 100): "P01299", ("anthra", "vierkant", 100): "P01301",
    ("quartz", "rond", 80): "P01283", ("quartz", "vierkant", 80): "P01262",
    ("quartz", "rond", 100): "P01293", ("quartz", "vierkant", 100): "P01398",
    ("koper", "rond", 80): "P01395", ("koper", "vierkant", 80): "P01397",
    ("koper", "rond", 100): "P01394", ("koper", "vierkant", 100): "P01396",
}
BOCHT = {
    ("naturel", "rond", 80): "P00426", ("naturel", "vierkant", 80): "P00430",
    ("naturel", "rond", 100): "P00434", ("naturel", "vierkant", 100): "P00438",
    ("anthra", "rond", 80): "P00425", ("anthra", "vierkant", 80): "P00432",
    ("anthra", "rond", 100): "P00437", ("anthra", "vierkant", 100): "P00440",
    ("quartz", "rond", 80): "P00429", ("quartz", "vierkant", 80): "P00431",
    ("quartz", "rond", 100): "P00436", ("quartz", "vierkant", 100): "P00439",
    ("koper", "rond", 80): "P00427", ("koper", "vierkant", 80): "P01291",
    ("koper", "rond", 100): "P00435", ("koper", "vierkant", 100): "P00441",
}

# Roof edges: the two-part clip system (Modde Heule) is the "2-delige dakrand"
CLIPS_BASIS = "P00483"               # basisprofiel brut, per m
CLIPS_BASIS_VERBINDING = "P00484"    # verbinding inwendig
CLIPS_BASIS_HOEK_BINNEN = "P00485"
CLIPS_BASIS_HOEK_BUITEN = "P00486"
# afwerking -> (overzetstuk per m, verbinding uitwendig, hoek binnen, hoek buiten)
OVERZETSTUK = {
    "ral": ("P01371", "P01370", "P01374", "P01373"),
    "9005": ("P00487", "P00488", "P00489", "P00490"),
    "ano": ("P01367", "P01366", "P01368", "P01369"),
}
# Single profiles (Bendec): DRB up to 100 mm, DRBS from 150 mm. Per height:
# afwerking -> (profiel per m, binnenhoek, buitenhoek, koppelplaatjes)
DRB = {
    45: {"ral": ("P00793", "P00843", "P00818", "P00865"),
         "ano": ("P00632", "P00672", "P00652", "P00689"),
         "stock": ("P00882", "P00932", "P00907", "P00954"),
         "brut": ("P00704", "P00754", "P00729", "P00776")},
    60: {"ral": ("P00794", "P00844", "P00819", "P00866"),
         "ano": ("P00633", "P00673", "P00653", "P00690"),
         "stock": ("P00883", "P00933", "P00908", "P00955"),
         "brut": ("P00705", "P00755", "P00730", "P00777")},
    80: {"ral": ("P00795", "P00845", "P00820", "P00867"),
         "ano": ("P00634", "P00674", "P00654", "P00691"),
         "stock": ("P00884", "P00934", "P00909", "P00956"),
         "brut": ("P00706", "P00756", "P00731", "P00778")},
    100: {"ral": ("P00796", "P00846", "P00821", "P00868"),
          "ano": ("P00635", "P00675", "P00655", "P00692"),
          "stock": ("P00885", "P00935", "P00910", "P00957"),
          "brut": ("P00707", "P00757", "P00732", "P00779")},
    150: {"ral": ("P00802", "P00852", "P00827", "P00870"),
          "ano": ("P00641", "P00681", "P00661", "P00694"),
          "stock": ("P00891", "P00941", "P00916", "P00959"),
          "brut": ("P00713", "P00763", "P00738", "P00781")},
    175: {"ral": ("P00803", "P00853", "P00828", "P00871"),
          "ano": ("P00642", "P00682", "P00662", "P00695"),
          "stock": ("P00892", "P00942", "P00917", "P00960"),
          "brut": ("P00714", "P00764", "P00739", "P00782")},
    200: {"ral": ("P00804", "P00854", "P00829", "P00872"),
          "ano": ("P00643", "P00683", "P00663", "P00696"),
          "stock": ("P00893", "P00943", "P00918", "P00961"),
          "brut": ("P00715", "P00765", "P00740", "P00783")},
}
ICONIK_BASIS = "P01207"              # basisprofiel 3 m, per m
ICONIK_SIERLIJST = "P00479"          # sierlijst 3 m, per m
ICONIK_VOEGCLIPS = "P00534"
ICONIK_BASIS_BINNEN = "P01404"
ICONIK_BASIS_BUITEN = "P00497"
ICONIK_SIER_BINNEN = "P01344"
ICONIK_SIER_BUITEN = "P01055"
AE_KRAAL_9005 = "P01409"             # alu kraal 28.15/60 zwart structuur, per m
AE_HOEK_9005 = "P01413"
ZINK_KRAAL = {"naturel": "P01321", "anthra": "P01322", "quartz": "P01323"}
ZINK_KRAAL_HOEK = {
    ("naturel", "binnen"): "P01310", ("naturel", "buiten"): "P01309",
    ("anthra", "binnen"): "P01312", ("anthra", "buiten"): "P01311",
    ("quartz", "binnen"): "P01314", ("quartz", "buiten"): "P01313",
}
DRUIPLIJST = {"naturel": "P01325", "anthra": "P01324", "quartz": "P01326"}
DRUIPLIJST_HOEK = {
    ("naturel", "binnen"): "P01316", ("naturel", "buiten"): "P01315",
    ("anthra", "binnen"): "P01320", ("anthra", "buiten"): "P01319",
    ("quartz", "binnen"): "P01318", ("quartz", "buiten"): "P01317",
}

# Wall connections
ZINK_SOLIN = "P01352"                # zink solin model 6, 1 m
SOLINKRAMMEN = "P01336"              # solinkrammen 30 mm galva, emmer 5 kg
BLADLOOD = "P01334"                  # bladlood 30 cm 1,25 mm (kg)
LOODVERVANGER = "P01011"             # loodvervanger zwart 190 mm, per m
ALU_WANDPROFIEL = "P01327"           # plooiwerk alu geanodiseerd ontw. 250, per m
ZINK_PLOOIWERK_150 = "P01321"        # plooiwerk ontw. 150 zink, per m
ZINK_PLOOIWERK_100_ANTHRA = "P01324"

# Penetrations (Cofapro, flashing SA = for EPDM)
DOORVOER_SA = {80: "P01172", 110: "P01173", 125: "P01174", 160: "P01175"}
KABELDOORVOER_SA = {80: "P01166", 125: "P01167"}

# Terrace and domes
TEGELDRAGER = {"23-35": "P01447", "35-50": "P01448", "50-80": "P01449",
               "80-110": "P01450", "110-140": "P01451", "140-170": "P01452"}
SPINDEL = {"buis": "P01457", "buis dubbel": "P01458", "oog": "P01459",
           "oog dubbel": "P01460"}
DRAAISTOK = {"haak": "P01382", "gleuf": "P01381"}

# Codes that are easy to get one off: the article name must contain this.
EXPECT = {
    EPDM_11: "1,1MM (15,25", EPDM_15: "1,5MM (15,25", EPDM_STROOK: "1,68X30,5",
    BONDING: "BA-2012 20L", SPLICE_3: "SPLICE TAPE 7,62", SPLICE_6: "6\"/152MM",
    QUICKPRIME: "QUICKPRIME", LAP_SEALANT: "LAP SEALANT", RMA_STRIP: "RMA STRIP",
    BATTEN_BAR: "BATTEN BAR", SOPRASTICK_VENTI: "SOPRASTICK VENTI",
    SOPRALENE_TECHNO: "SOPRALENE TECHNO", DBR: "Bauder DBR", KSD: "Bauder KSD",
    SA_PRIMER: "drukvat", ALUTRIX: "ALUTRIX", GRIND: "ROLGRIND",
    GEOTEXTIEL: "GEOTEXTIEL", GRINDVANGER: "grindvang", ISOLFOAM: "Isolfoam",
    ISO_PLAATJE: "Isolatieplaatjes", SCHROEF_45x45: "4,5x45",
    SCHROEF_5x60: "5x60", SCHROEF_6x130: "6x130", SCHROEF_6x180: "6x180",
    SLAGPLUG_6x40: "Slagplug 6x40", PIANO_42x25: "Pianos 4,2x25",
    OSB_18: "18mm", OSB_22: "22MM", MULTIPLEX_15: "MULTIPLEX MERANTI 15MM",
    SOLID_JOHN_15: "SOLID JOHN SPOUWPLAAT", CLS: "CLS 38X 58",
    BADDENS_18x7: "BADDENS 18 X 7", ANKER_XSRB: "X-SR-B", ANKER_T21: "T-21",
    ANKER_XH16: "X-H-16", ANKER_LOOP: "Loop", MANCHET_BITUMEN_48: "<48mm BITUMEN",
    ALU_SPUWER_ROOFING: "DRAINI", CLIPS_BASIS: "BASISPROFIEL BRUT 3M",
    ICONIK_BASIS: "basisprofiel 3m", ICONIK_SIERLIJST: "sierlijst 3m",
    AE_KRAAL_9005: "28.15/60 mm zwart structuur", ZINK_SOLIN: "SOLIN MODEL 6",
    BLADLOOD: "BLADLOOD", LOODVERVANGER: "Loodvervanger Zwart",
    ALU_WANDPROFIEL: "ALU ANODISE", SILIRUB: "SILIRUB EPDM",
}
for _mm, _code in PIR.items():
    EXPECT[_code] = "UTHERM ROOF L %dMM" % _mm
for _mm, _code in PIR_SPONNING.items():
    EXPECT[_code] = "FLAT ROOF L %d mm" % _mm
for _mm, _code in ROCKWOOL.items():
    EXPECT[_code] = "RHINOXX %dMM" % _mm
for _mm, _code in ISO_SCREW.items():
    EXPECT[_code] = "4,8 x %dmm" % _mm
for _mm, _code in PE_TAPBUIS_SA.items():
    EXPECT[_code] = "PE %dMM MET ZELFKLEVENDE" % _mm
for _mm, _code in PE_TAPBUIS_ROOFING.items():
    EXPECT[_code] = "PE DIA %d L 60CM MET ROOFINGSLAB" % _mm
for _mm, _code in BOLROOSTER.items():
    EXPECT[_code] = "Bladvanger (bolrooster) galva %dmm" % _mm
for _mm, _code in PE_BUIS.items():
    EXPECT[_code] = "PE buis %d x" % _mm
for _mm, _code in PE_BEUGEL.items():
    EXPECT[_code] = "beugel M8/M10 x %d mm" % _mm if _mm != 63 else "beugel M10 x 63"
for _mm, _code in PE_MOF.items():
    EXPECT[_code] = "elektrolasmof FF %d x" % _mm
for _height, _finishes in DRB.items():
    _family = "DRB %d/62" % _height if _height <= 120 else "DRBS %d/80" % _height
    _labels = {"ral": "Ral divers", "ano": "Ano", "stock": "Stock kleur",
               "brut": "Brut"}
    for _finish, (_profile, _inner, _outer, _coupler) in _finishes.items():
        EXPECT[_profile] = "Dakrand %s %s" % (_family, _labels[_finish])
        EXPECT[_inner] = "Binnenhoek %s %s" % (_family, _labels[_finish])
        EXPECT[_outer] = "Buitenhoek %s %s" % (_family, _labels[_finish])
        EXPECT[_coupler] = "Koppelplaatjes %d %s" % (_height, _labels[_finish])
for _colour, _code in ZINK_KRAAL.items():
    EXPECT[_code] = "PLOOIWERK ONTW 150"
for _colour, _code in DRUIPLIJST.items():
    EXPECT[_code] = "PLOOIWERK ONTW 100"
for (_colour, _side), _code in ZINK_KRAAL_HOEK.items():
    EXPECT[_code] = "%sHOEK ONTW 150" % _side.upper()
for (_colour, _side), _code in DRUIPLIJST_HOEK.items():
    EXPECT[_code] = "%sHOEK ONTW 100" % _side.upper()
for _mm, _code in DOORVOER_SA.items():
    EXPECT[_code] = "VERLUCHTING + SLAB + KAP & LIJMMOF Flashing SA - L%d" % _mm
for _mm, _code in KABELDOORVOER_SA.items():
    EXPECT[_code] = "KABELDOORVOER + SLAB + KAP Flashing SA diam %d" % _mm

# ------------------------------------------------------------------ norms
# Consumption per unit of the works item. Kept in one place so the figures
# can be discussed (and tuned) without reading the recipes.
MEMBRANE_LOSS = 1.10          # m2 EPDM per m2 dak, verkleefd: overlap + snijverlies
MEMBRANE_LOSS_BALLAST = 1.08  # losliggend: minder details in de overlap
BONDING_PER_M2 = 0.016        # pot 20 l per ~62 m2 (0,32 l/m2, beide vlakken)
SEAM_PER_M2 = 0.15            # m naad per m2 dak (rollen van 15,25 m + details)
PRIMER_PER_M_SEAM = 0.02      # gallon per m naad (~0,075 l/m, beide zijden)
SEALANT_PER_M_SEAM = 0.1      # koker per m naadeinde/detail
BITUMEN_LOSS = 1.12           # m2 per m2: overlap 10 cm op een rol van 1 m
INSULATION_LOSS = 1.03        # m2 per m2: snijverlies
FOAM_PER_M2 = 0.15            # Isolfoam, 1 bus per 7 m2
PIR_FASTENERS_PER_M2 = 5.5    # 4 per plaat 600 x 1200 (0,72 m2)
ROCKWOOL_FASTENERS_PER_M2 = 6.0  # 4 per plaat 1000 x 600 (0,60 m2)
PROFILE_COUPLERS_PER_M = 0.34  # 1 per element van 3 m
PROFILE_SCREWS_PER_M = 4.0    # om de 25 cm
PROFILE_SEALANT_PER_M = 0.05  # koker per 20 m (voegen)
CORNER_SEALANT = 0.1          # koker per hoek
HOOKS_PER_M = 0.6             # scharnierhaken, 1 per ~1,7 m afvoerbuis
PE_BRACKETS_PER_M = 0.7       # beugels, 1 per ~1,4 m
PE_SLEEVES_PER_M = 0.2        # elektrolasmof, 1 per buis van 5 m
GRIND_KG_PER_M2 = 85.0        # laag van 5 cm rolgrind 16/32
GEOTEXTIEL_PER_M2 = 0.011     # rol van 100 m2, 10% overlap
DECK_SCREWS_PER_M2 = 12.0     # OSB op kepers om 60 cm, schroef om 30 cm
BOARD_SCREWS_PER_M2 = 8.0     # spouwplaat / multiplex
LEAD_KG_PER_M = 4.5           # bladlood 30 cm x 1,25 mm = 4,3 kg/m + overlap


def screw_for(total_mm):
    """Shortest insulation screw that anchors 30 mm below the insulation."""
    for length in sorted(ISO_SCREW):
        if length >= total_mm + 30:
            return ISO_SCREW[length]
    return ISO_SCREW[max(ISO_SCREW)]


# ----------------------------------------------------------------- recipes
def seams(m2=1.0):
    """Naden van de EPDM per m2 dakvlak: tape, primer, lap sealant."""
    seam = SEAM_PER_M2 * m2
    return [(SPLICE_3, seam), (QUICKPRIME, seam * PRIMER_PER_M_SEAM),
            (LAP_SEALANT, seam * SEALANT_PER_M_SEAM)]


def detail(metres=1.0, tape=SPLICE_6):
    """Een EPDM-aansluiting per lm: 6"-tape (of een flashing), primer, sealant."""
    return [(tape, 1.05 * metres), (QUICKPRIME, PRIMER_PER_M_SEAM * metres),
            (LAP_SEALANT, SEALANT_PER_M_SEAM * metres)]


def sa_accessory(qty_seal=0.15):
    """Wat een zelfklevende slab (tapbuis, doorvoer) nog nodig heeft."""
    return [(QUICKPRIME, 0.02), (LAP_SEALANT, qty_seal)]


def upstand(height_m=0.4):
    """Een opstand tegen een muur, per lm: een strook EPDM uit de rol,
    verkleefd, met een 6"-naad onderaan."""
    return [(EPDM_STROOK, height_m * 1.05), (BONDING, 0.01)] + detail()


def wrap(metres=1.0):
    """Een doorvoer opnieuw inpakken met FormFlash (per stuk)."""
    return [(FORMFLASH_22, metres), (WATERBLOCK, 0.5)] + sa_accessory()


def profile(code, couplers, m=1.0):
    return [(code, 1.0 * m), (couplers, PROFILE_COUPLERS_PER_M * m),
            (SCHROEF_45x45, PROFILE_SCREWS_PER_M * m),
            (SILIRUB, PROFILE_SEALANT_PER_M * m)]


def corner(code, couplers=None):
    lines = [(code, 1.0), (SCHROEF_45x45, 4.0), (SILIRUB, CORNER_SEALANT)]
    if couplers:
        lines.append((couplers, 2.0))
    return lines


def pir_layers(thicknesses, sponning=()):
    """Een of twee lagen PIR: (m2 per laag) met snijverlies."""
    lines = []
    for index, mm in enumerate(thicknesses):
        code = PIR_SPONNING[mm] if index in sponning else PIR[mm]
        lines.append((code, INSULATION_LOSS))
    return lines


def glued(layers):
    return layers + [(ISOLFOAM, FOAM_PER_M2 * len(layers))]


def mechanical(layers, total_mm, per_m2=PIR_FASTENERS_PER_M2):
    return layers + [(screw_for(total_mm), per_m2), (ISO_PLAATJE, per_m2)]


def chimney(extra=()):
    """Schouw inpakken met EPDM, per m2 opstandvlak."""
    return [(EPDM_STROOK, 1.15), (BONDING, 0.02), (SPLICE_3, 0.6),
            (QUICKPRIME, 0.015), (LAP_SEALANT, 0.1), (SILIRUB, 0.15)] + list(extra)


# ------------------------------------------------------------- the demo set
# works item -> list of (raw material, quantity per unit of the works item)
BOMS = OrderedDict()


def bom(code, *lines):
    if code in BOMS:
        raise SystemExit("works item %s is defined twice" % code)
    merged = OrderedDict()
    for chunk in lines:
        for component, qty in chunk:
            merged[component] = merged.get(component, 0.0) + float(qty)
    BOMS[code] = [(component, round(qty, 3)) for component, qty in merged.items()]


# --- dakbedekking (per m2) -------------------------------------------------
bom("S00177", [(EPDM_11, MEMBRANE_LOSS), (BONDING, BONDING_PER_M2)], seams())
bom("S00178", [(EPDM_15, MEMBRANE_LOSS), (BONDING, BONDING_PER_M2)], seams())
bom("S00179", [(EPDM_11, MEMBRANE_LOSS_BALLAST)], seams())
bom("S00180", [(EPDM_15, MEMBRANE_LOSS_BALLAST)], seams())
bom("S00181", [(SOPRASTICK_VENTI, BITUMEN_LOSS), (SOPRALENE_TECHNO, BITUMEN_LOSS)])
# kimfixatie (per lm): batten bar om de 30 cm vastgezet, afgedekt met RMA-strip
bom("S00182", [(BATTEN_BAR, 1.0), (ISO_SCREW[60], 3.5), (RMA_STRIP, 1.05),
               (QUICKPRIME, 0.01), (LAP_SEALANT, 0.05)])
bom("S00183", [(GRIND, GRIND_KG_PER_M2), (GEOTEXTIEL, GEOTEXTIEL_PER_M2)])
bom("S00468", [(GRINDVANGER, 1.02), (LAP_SEALANT, 0.02)])

# --- dampschermen (per m2) -------------------------------------------------
bom("S00122", [(PE_FOLIE, 1.15)])
bom("S00123", [(ALUTRIX, MEMBRANE_LOSS), (SA_PRIMER, 0.008)])   # op hout
bom("S00124", [(ALUTRIX, MEMBRANE_LOSS), (SA_PRIMER, 0.012)])   # op beton
bom("S00125", [(SOPRAGLASS_V3, BITUMEN_LOSS), (BITUMEN_PRIMER, 0.012)])
bom("S00126", [(SOPRAGLASS_V4, BITUMEN_LOSS), (BITUMEN_PRIMER, 0.012)])
bom("S00404", [(DBR, MEMBRANE_LOSS), (SA_PRIMER, 0.008)])       # op hout
bom("S00405", [(KSD, MEMBRANE_LOSS), (SA_PRIMER, 0.012)])       # op beton

# --- isolatie (per m2) -----------------------------------------------------
PIR_SINGLE = [20, 30, 40, 50, 60, 70, 80, 100, 120, 140, 160, 180, 200]
for code, mm in zip(range(131, 144), PIR_SINGLE):
    bom("S%05d" % code, glued(pir_layers([mm])))                      # verkleefd
for code, mm in zip(range(340, 365, 2), PIR_SINGLE):
    bom("S%05d" % code, mechanical(pir_layers([mm]), mm))             # mechanisch
for code, mm in zip(range(341, 366, 2), PIR_SINGLE):
    bom("S%05d" % code, pir_layers([mm]))                             # losliggend
PIR_STAGGERED = {144: (50, 50), 145: (60, 60), 146: (70, 70), 147: (80, 80),
                 148: (100, 100), 389: (100, 80)}
for code, layers in PIR_STAGGERED.items():
    bom("S%05d" % code, glued(pir_layers(layers)))
for code, layers in {366: (50, 50), 368: (60, 60), 370: (70, 70), 372: (80, 80),
                     374: (100, 100), 388: (100, 80)}.items():
    bom("S%05d" % code, mechanical(pir_layers(layers), sum(layers)))
for code, layers in {367: (50, 50), 369: (60, 60), 371: (70, 70), 373: (80, 80),
                     375: (100, 100), 390: (100, 80)}.items():
    bom("S%05d" % code, pir_layers(layers))
# 1200 x 2400 met sponning; een geschrankt pakket legt een 600 x 1200 onder
PIR_LARGE = {149: ((100,), (0,)), 150: ((120,), (0,)), 151: ((140,), (0,)),
             152: ((160,), (0,)), 153: ((80, 100), (1,)), 154: ((100, 100), (0, 1))}
for code, (layers, sponning) in PIR_LARGE.items():
    bom("S%05d" % code, glued(pir_layers(layers, sponning)))
for code, (layers, sponning) in zip(
        (376, 378, 380, 382, 384, 386), PIR_LARGE.values()):
    bom("S%05d" % code, mechanical(pir_layers(layers, sponning), sum(layers)))
for code, (layers, sponning) in zip(
        (377, 379, 381, 383, 385, 387), PIR_LARGE.values()):
    bom("S%05d" % code, pir_layers(layers, sponning))
# Rockwool Rhinoxx: mechanisch bevestigd
for code, mm in zip(range(160, 172), sorted(ROCKWOOL)):
    bom("S%05d" % code, mechanical([(ROCKWOOL[mm], INSULATION_LOSS)], mm,
                                   ROCKWOOL_FASTENERS_PER_M2))
for code, layers in {172: (80, 100), 173: (100, 100), 174: (100, 120),
                     175: (120, 120), 176: (120, 140)}.items():
    bom("S%05d" % code, mechanical(
        [(ROCKWOOL[mm], INSULATION_LOSS) for mm in layers], sum(layers),
        ROCKWOOL_FASTENERS_PER_M2))
# aanzet muurisolatie 20 cm hoog (per lm) en ingewerkte goot ca. 25 cm (per lm)
for code, mm in zip(range(127, 131), (100, 120, 140, 160)):
    bom("S%05d" % code, [(PIR[mm], 0.21), (ISOLFOAM, 0.05)])
for code, mm in zip(range(155, 159), (30, 40, 60, 80)):
    bom("S%05d" % code, [(PIR[mm], 0.27), (ISOLFOAM, 0.04)])

# --- dakranden -------------------------------------------------------------
# 2-delig (per lm en per hoek): basisprofiel + overzetstuk in de afwerking
for finish, (per_m, inner, outer) in {
        "ral": ("S00400", "S00401", "S00402"),
        "9005": ("S00070", "S00072", "S00391"),
        "ano": ("S00071", "S00336", "S00335")}.items():
    top, joint, corner_in, corner_out = OVERZETSTUK[finish]
    bom(per_m, [(CLIPS_BASIS, 1.0), (top, 1.0),
                (CLIPS_BASIS_VERBINDING, PROFILE_COUPLERS_PER_M),
                (joint, PROFILE_COUPLERS_PER_M),
                (SCHROEF_45x45, PROFILE_SCREWS_PER_M),
                (SILIRUB, PROFILE_SEALANT_PER_M)])
    bom(inner, [(CLIPS_BASIS_HOEK_BINNEN, 1.0), (corner_in, 1.0),
                (CLIPS_BASIS_VERBINDING, 2.0), (joint, 2.0),
                (SCHROEF_45x45, 4.0), (SILIRUB, CORNER_SEALANT)])
    bom(outer, [(CLIPS_BASIS_HOEK_BUITEN, 1.0), (corner_out, 1.0),
                (CLIPS_BASIS_VERBINDING, 2.0), (joint, 2.0),
                (SCHROEF_45x45, 4.0), (SILIRUB, CORNER_SEALANT)])
# enkelvoudig: hoogte x afwerking -> (profiel, binnenhoek, buitenhoek)
HEIGHTS = (45, 60, 80, 100, 150, 175, 200)
SINGLE_EDGES = {
    "ral": (range(73, 80), range(80, 87), range(392, 399)),
    "ano": (range(406, 413), range(427, 434), range(447, 454)),
    # RAL stock has no 175 mm inner corner in the price list
    "stock": (range(413, 420), (434, 435, 436, 437, 438, None, 439),
              range(454, 461)),
    "brut": (range(420, 427), range(440, 447), range(461, 468)),
}
for finish, (profiles, inners, outers) in SINGLE_EDGES.items():
    for height, s_profile, s_inner, s_outer in zip(HEIGHTS, profiles, inners, outers):
        p_profile, p_inner, p_outer, p_coupler = DRB[height][finish]
        bom("S%05d" % s_profile, profile(p_profile, p_coupler))
        if s_inner is not None:
            bom("S%05d" % s_inner, corner(p_inner, p_coupler))
        bom("S%05d" % s_outer, corner(p_outer, p_coupler))
# zinken kralen: plooiwerk ontw. 150, met of zonder druiplijst (ontw. 100)
for colour, per_m, inner, outer, per_m_drip, inner_drip, outer_drip in (
        ("naturel", "S00088", "S00090", "S00399", "S00087", "S00089", None),
        ("anthra", "S00487", "S00488", "S00489", "S00490", "S00491", "S00492"),
        ("quartz", "S00481", "S00482", "S00483", "S00484", "S00486", "S00485")):
    kraal = [(ZINK_KRAAL[colour], 1.0), (SCHROEF_45x45, PROFILE_SCREWS_PER_M),
             (SILIRUB, PROFILE_SEALANT_PER_M)]
    drip = [(DRUIPLIJST[colour], 1.0), (PIANO_42x25, 3.0)]
    bom(per_m, kraal)
    bom(per_m_drip, kraal, drip)
    for side, plain, with_drip in (("binnen", inner, inner_drip),
                                   ("buiten", outer, outer_drip)):
        hoek = [(ZINK_KRAAL_HOEK[(colour, side)], 1.0), (SCHROEF_45x45, 3.0),
                (SILIRUB, CORNER_SEALANT)]
        bom(plain, hoek)
        if with_drip:
            bom(with_drip, hoek, [(DRUIPLIJST_HOEK[(colour, side)], 1.0)])
# aluminium kralen: Iconik (2-delig) en de enkelvoudige AE-kraal in RAL 9005
bom("S00091", [(ICONIK_BASIS, 1.0), (ICONIK_SIERLIJST, 1.0),
               (ICONIK_VOEGCLIPS, PROFILE_COUPLERS_PER_M),
               (SCHROEF_45x45, PROFILE_SCREWS_PER_M),
               (SILIRUB, PROFILE_SEALANT_PER_M)])
bom("S00092", [(ICONIK_BASIS_BINNEN, 1.0), (ICONIK_SIER_BINNEN, 1.0),
               (SCHROEF_45x45, 4.0), (SILIRUB, CORNER_SEALANT)])
bom("S00093", [(ICONIK_BASIS_BUITEN, 1.0), (ICONIK_SIER_BUITEN, 1.0),
               (SCHROEF_45x45, 4.0), (SILIRUB, CORNER_SEALANT)])
bom("S00094", [(AE_KRAAL_9005, 1.0), (SCHROEF_45x45, PROFILE_SCREWS_PER_M),
               (SILIRUB, PROFILE_SEALANT_PER_M)])
bom("S00095", [(AE_HOEK_9005, 1.0), (SCHROEF_45x45, 3.0), (SILIRUB, CORNER_SEALANT)])
bom("S00096", [(AE_HOEK_9005, 1.0), (SCHROEF_45x45, 3.0), (SILIRUB, CORNER_SEALANT)])

# --- hout en plaatmateriaal ------------------------------------------------
bom("S00063", [(CLS, 1.05), (SCHROEF_6x130, 2.0)])              # hellingslatten, per lm
bom("S00064", [(OSB_18, 1.08), (SCHROEF_45x45, DECK_SCREWS_PER_M2)])
bom("S00065", [(OSB_22, 1.08), (SCHROEF_5x60, DECK_SCREWS_PER_M2)])
bom("S00066", [(CLS, 2.1), (SCHROEF_6x130, 3.0)])               # ophogen 10-12 cm
bom("S00067", [(CLS, 3.15), (SCHROEF_6x180, 3.0)])              # ophogen 14-16 cm
bom("S00068", [(MULTIPLEX_15, 1.10), (SCHROEF_45x45, BOARD_SCREWS_PER_M2)])
bom("S00069", [(SOLID_JOHN_15, 1.10), (SCHROEF_45x45, BOARD_SCREWS_PER_M2)])
bom("S00284", [(CLS, 2.1), (SCHROEF_6x130, 3.0)])               # koepel ophogen
# dakopening voor koepel of dakraam: raveelwerk in baddens (per lm)
for code in ("S00283", "S00324"):
    bom(code, [(BADDENS_18x7, 2.1), (BALKSCHOEN, 1.0), (SCHROEF_6x130, 6.0)])
# dakopstand voor het dakraam (per lm) en zijn isolatie + EPDM
bom("S00325", [(CLS, 2.1), (MULTIPLEX_15, 0.35), (SCHROEF_6x130, 4.0),
               (SCHROEF_45x45, 6.0)])
bom("S00326", [(PIR[30], 0.35), (ISOLFOAM, 0.05), (EPDM_STROOK, 0.5),
               (BONDING, 0.01)], detail(tape=SPLICE_3))

# --- veiligheid (per stuk) -------------------------------------------------
for code, anchor in (("S00012", ANKER_XSRB), ("S00013", ANKER_T21),
                     ("S00014", ANKER_XH16)):
    bom(code, [(anchor, 1.0), (PIPE_FLASHING, 1.0)], sa_accessory(0.2))   # EPDM
bom("S00016", [(ANKER_LOOP, 1.0)], wrap(0.6))                            # lus: ingepakt
for code, anchor in (("S00338", ANKER_XSRB), ("S00337", ANKER_T21),
                     ("S00339", ANKER_XH16)):
    bom(code, [(anchor, 1.0), (MANCHET_BITUMEN_48, 1.0)])                 # roofing
bom("S00011", [(WALLFIX, 1.0), (WALLFIX_BOUT, 4.0)])

# --- regenwaterafvoer ------------------------------------------------------
for code, mm in zip(range(190, 197), (63, 75, 90, 110, 125, 160, 200)):
    bom("S%05d" % code, [(PE_TAPBUIS_SA[mm], 1.0)], sa_accessory())
for code, mm in zip(range(204, 210), (50, 75, 90, 110, 125, 160)):
    bom("S%05d" % code, [(PE_TAPBUIS_ROOFING[mm], 1.0)])
bom("S00202", [(PE_TAPBUIS_SA[50], 1.0)], sa_accessory())       # noodspuwer EPDM
bom("S00210", [(PE_TAPBUIS_ROOFING[50], 1.0)])                  # noodspuwer roofing
bom("S00211", [(ALU_SPUWER_ROOFING, 1.0)])
for code, mm in zip(range(197, 202), (80, 100, 120, 150, 200)):
    bom("S%05d" % code, [(BOLROOSTER[mm], 1.0)])
PE_SIZES = (50, 63, 75, 90, 110, 125, 160, 200)
for code, mm in zip(range(246, 254), PE_SIZES):
    lines = [(PE_BUIS[mm], 1.05)]
    if mm in PE_BEUGEL:
        lines.append((PE_BEUGEL[mm], PE_BRACKETS_PER_M))
    if mm in PE_MOF:
        lines.append((PE_MOF[mm], PE_SLEEVES_PER_M))
    bom("S%05d" % code, lines)
# incl. isolatie achter de buis en een EPDM-slab errond (per lm)
for code, mm in zip(range(254, 260), PE_SIZES[:6]):
    bom("S%05d" % code, BOMS["S%05d" % (code - 8)],
        [(PIR[30], 0.3), (ISOLFOAM, 0.05), (EPDM_STROOK, 0.6), (BONDING, 0.01),
         (SPLICE_3, 0.5), (QUICKPRIME, 0.01)])
# zink en koper: buis met scharnierhaken (per lm), bocht onderaan (per stuk)
METAL_PIPES = [(colour, shape, size)
               for colour in ("naturel", "anthra", "quartz", "koper")
               for shape, size in (("rond", 80), ("vierkant", 80),
                                   ("rond", 100), ("vierkant", 100))]
for code, key in zip(range(213, 229), METAL_PIPES):
    bom("S%05d" % code, [(ZINK_BUIS[key], 1.0), (HAAK[key], HOOKS_PER_M)])
for code, key in zip(range(229, 245), METAL_PIPES):
    bom("S%05d" % code, [(BOCHT[key], 1.0)])

# --- doorvoeren en schoorsteen ---------------------------------------------
for code, mm in zip(range(274, 278), (80, 110, 125, 160)):
    bom("S%05d" % code, [(DOORVOER_SA[mm], 1.0)], sa_accessory())
for code, mm in (("S00278", 80), ("S00279", 125)):
    bom(code, [(KABELDOORVOER_SA[mm], 1.0)], sa_accessory())
for code in ("S00280", "S00281", "S00282"):
    bom(code, wrap())                       # bestaande of vreemde doorvoer inpakken
WANDPROFIEL = [(ALU_WANDPROFIEL, 0.5), (SLAGPLUG_6x40, 1.5)]   # onder de deksteen
bom("S00184", chimney(), WANDPROFIEL)
bom("S00185", chimney([(PIR[30], 1.05), (ISOLFOAM, FOAM_PER_M2)]), WANDPROFIEL)
bom("S00186", chimney([(MULTIPLEX_15, 1.05), (SCHROEF_45x45, BOARD_SCREWS_PER_M2)]),
    WANDPROFIEL)
bom("S00187", chimney())
bom("S00188", chimney([(PIR[30], 1.05), (ISOLFOAM, FOAM_PER_M2)]))
bom("S00189", chimney([(MULTIPLEX_15, 1.05), (SCHROEF_45x45, BOARD_SCREWS_PER_M2)]))
for code, mm in zip(range(474, 478), (40, 60, 80, 100)):
    bom("S%05d" % code, chimney([(PIR[mm], 1.05), (ISOLFOAM, FOAM_PER_M2)]))

# --- randaansluitingen (per lm) --------------------------------------------
bom("S00097", [(ZINK_PLOOIWERK_100_ANTHRA, 1.0), (SOLINKRAMMEN, 0.005),
               (SILIRUB, 0.15), (SCHIJFBLAD, 0.1)])            # solins anthrazink
bom("S00098", [(ALU_WANDPROFIEL, 1.0), (SLAGPLUG_6x40, 3.0), (SILIRUB, 0.15),
               (LAP_SEALANT, 0.1)])
bom("S00099", detail())                                          # op slabben metser
bom("S00100", upstand(0.3), [(SILIRUB, 0.1)])                   # onder bestaand lood
bom("S00101", [(RESITRIX, 0.05), (RESITRIX_PRIMER, 0.01)])       # buren, Resitrix
bom("S00102", detail())                                          # buren, nadentape
bom("S00103", detail(tape=FORMFLASH_22), [(SILIRUB, 0.05)])     # EPDM in de goot
bom("S00104", [(ALUFLEXX, 0.21), (BITUMEN_PRIMER, 0.01)])        # roofing in de goot
bom("S00105", [(LOODVERVANGER, 1.05)], upstand(0.3))
bom("S00106", [(LOODVERVANGER, 1.05), (ALUFLEXX, 0.21), (BITUMEN_PRIMER, 0.01)])
bom("S00107", detail(tape=FORMFLASH_30), [(SILIRUB, 0.1)])      # op verandaplaten
bom("S00108", [(ALUFLEXX, 0.21), (BITUMEN_PRIMER, 0.01), (SILIRUB, 0.1)])
SOLIN = [(ZINK_SOLIN, 1.0), (SILIRUB, 0.15), (SCHIJFBLAD, 0.1)]  # inslijpen + voeg
bom("S00109", upstand(0.4), SOLIN)                              # EPDM thv gevel
bom("S00110", [(ALUFLEXX, 0.21), (BITUMEN_PRIMER, 0.01)], SOLIN)
bom("S00111", [(BLADLOOD, LEAD_KG_PER_M), (SOLINKRAMMEN, 0.01), (SILIRUB, 0.15)],
    upstand(0.4))                                                # onderkapping lood
for code in ("S00112", "S00113"):                                # onder het onderdak
    bom(code, [(ZINK_PLOOIWERK_150, 1.05), (PIANO_42x25, 4.0)], upstand(0.3))
bom("S00114", detail(tape=FORMFLASH_30), [(SILIRUB, 0.1)])      # thv lichtstraat
bom("S00115", [(EPDM_STROOK, 0.4), (BONDING, 0.01), (SILIRUB, 0.15)],
    detail(1.5))                                                 # dorpel, inpakken
# EPDM-slabben per ontwikkeling: tot 50 cm een zelfklevende flashing, daarboven
# een strook uit de rol, verkleefd en met een naad
bom("S00116", detail(tape=SA_FLASHING_45))
for code, width in zip(range(117, 122), (0.6, 0.7, 0.8, 0.9, 1.0)):
    bom("S%05d" % code, [(EPDM_STROOK, width * 1.05), (BONDING, 0.015)],
        detail(tape=SPLICE_3))

# --- terrasvloer en koepels (per stuk) -------------------------------------
for code, rng in zip((328, 329, 330, 331, 332, 469),
                     ("23-35", "35-50", "50-80", "80-110", "110-140", "140-170")):
    bom("S%05d" % code, [(TEGELDRAGER[rng], 1.0)])
for code, kind in zip(range(470, 474), ("buis", "buis dubbel", "oog", "oog dubbel")):
    bom("S%05d" % code, [(SPINDEL[kind], 1.0)])
bom("S00314", [(DRAAISTOK["haak"], 1.0)])
bom("S00315", [(DRAAISTOK["gleuf"], 1.0)])


# ------------------------------------------------------------------- build
def load_catalog():
    with open(CATALOG, encoding="utf-8") as handle:
        data = json.load(handle)
    return {entry["code"]: entry for entry in data["products"]}


def check(products):
    """Fail loudly rather than ship a bill of materials that loads the wrong
    article on the van."""
    problems = []
    for code, expected in EXPECT.items():
        entry = products.get(code)
        if entry is None:
            problems.append("unknown code %s (expected '%s')" % (code, expected))
        elif expected.lower() not in entry["name"].lower():
            problems.append("%s is '%s', expected '%s'"
                            % (code, entry["name"], expected))
    for parent, lines in BOMS.items():
        entry = products.get(parent)
        if entry is None:
            problems.append("%s: unknown works item" % parent)
            continue
        if not entry["is_service"]:
            problems.append("%s: %s is a raw material, not a works item"
                            % (parent, entry["name"]))
        if not lines:
            problems.append("%s: no lines" % parent)
        for component, qty in lines:
            item = products.get(component)
            if item is None:
                problems.append("%s: unknown component %s" % (parent, component))
                continue
            if item["is_service"]:
                problems.append("%s: component %s (%s) is a works item, not a "
                                "raw material" % (parent, component, item["name"]))
            if qty <= 0:
                problems.append("%s: %s has quantity %s" % (parent, component, qty))
    return problems


def build(products):
    boms = []
    for parent, lines in BOMS.items():
        entry = products[parent]
        boms.append({
            "code": parent,
            "product": entry["name"],
            "uom": entry["uom"],
            "category": entry["category_path"],
            "type": "phantom",
            "lines": [
                {
                    "code": component,
                    "component": products[component]["name"],
                    "qty": qty,
                    "uom": products[component]["uom"],
                }
                for component, qty in lines
            ],
        })
    return boms


def summary(boms, products):
    """What the demo covers, per chapter, and the material cost it implies."""
    by_chapter = OrderedDict()
    for bom_ in boms:
        chapter = bom_["category"].split("/")[0]
        by_chapter.setdefault(chapter, [0, 0])
        by_chapter[chapter][0] += 1
    for entry in products.values():
        if entry["is_service"]:
            chapter = entry["category_path"].split("/")[0]
            by_chapter.setdefault(chapter, [0, 0])
            by_chapter[chapter][1] += 1
    lines = ["%-45s %5s / %-5s" % ("hoofdstuk", "demo", "posten")]
    for chapter, (covered, total) in by_chapter.items():
        lines.append("%-45s %5d / %-5d" % (chapter, covered, total))
    return "\n".join(lines)


def main():
    products = load_catalog()
    problems = check(products)
    if problems:
        for problem in problems:
            print("FOUT:", problem, file=sys.stderr)
        raise SystemExit("%d problemen, niets weggeschreven" % len(problems))
    boms = build(products)
    components = {line["code"] for bom_ in boms for line in bom_["lines"]}
    data = {
        "source": "tectora_boms/tools/build_demo_boms.py",
        "reference": REFERENCE,
        "boms": boms,
        "stats": {
            "boms": len(boms),
            "lines": sum(len(b["lines"]) for b in boms),
            "components": len(components),
        },
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print("%(boms)s stuklijsten, %(lines)s regels, %(components)s grondstoffen"
          % data["stats"])
    print(summary(boms, products))
    print("geschreven: %s" % os.path.abspath(OUTPUT))


if __name__ == "__main__":
    main()
