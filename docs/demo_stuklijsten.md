# Demo-stuklijsten: de verkoopproducten verrijkt met hun grondstoffen

Demo-data om de **automatische materiaallijst** te tonen: bij het bevestigen
van een verkooporder ontbindt `tectora_roof` elk verkocht product via zijn
stuklijst in grondstoffen (zie `tectora_roof/README.md`, *Materiaallijst*).
Dat werkt alleen als de verkoopproducten een stuklijst hébben met echte
grondstoffen erin, en dat is met de geïmporteerde export nauwelijks het geval:
die koppelt op naam en levert vooral werkurenregels op
([`stuklijst_koppeling.md`](stuklijst_koppeling.md)).

De module `tectora_boms` levert daarom `data/demo_boms.json`: **373
stuklijsten met 1.196 regels op 355 verschillende grondstoffen**, één volledige
stuklijst per verkoopproduct dat een tegenhanger heeft bij de grondstoffen van
de catalogus. Alles is gekoppeld op **productcode** (`S…` verkoopproduct,
`P…` grondstof), dus er wordt niets geraden.

Reproduceren en controleren:

```bash
python3 tectora_boms/tools/build_demo_boms.py
```

Het script controleert elke code tegen `tectora_products/data/product_catalog.json`
(de ouder moet een verkoopproduct zijn, elke component een grondstof) en voor
de codes die makkelijk één verschuiven ook de artikelnaam (een profiel van
150 mm in de verkeerde afwerking is precies de fout waarvoor die controle
bestaat). Bij een fout schrijft het niets weg.

## Wat gedekt is

| Hoofdstuk | Demo / posten | Wat er in de stuklijst zit |
|---|---|---|
| 04. Opbouwwerken plat dak | 234 / 257 | dampschermen, isolatie (PIR verkleefd / mechanisch / losliggend, Rockwool), EPDM en bitumen, kimfixatie, ballast, afvoer, doorvoeren, schoorsteen, randaansluitingen, hout en plaatmateriaal |
| 02. Dakranden | 115 / 116 | 2-delige dakrand (3 afwerkingen), enkelvoudige dakrand (7 hoogtes × 4 afwerkingen, met hoeken), zinken kralen (3 kleuren, met of zonder druiplijst), Iconik, alu kraal |
| 02. Verplichte veiligheidsvoorzieningen | 8 / 18 | ankerpunten in EPDM- en roofinguitvoering, Wallfix |
| 05. Koepels | 7 / 43 | spindels en draaistokken |
| 06. Dakramen | 3 / 4 | dakopening, dakopstand en zijn isolatie + EPDM |
| 08. Terrasvloer | 6 / 10 | tegeldragers per hoogtebereik |
| 03. Afbraakwerken, 01. Algemene werken | 0 | bewust: geen materiaal |

**Bewust zonder stuklijst** (en dus, zoals de code het bedoelt, arbeid zonder
materiaal in de materiaallijst): de afbraakwerken en de algemene werken; huur
(hoogwerker, stelling, balustrades); de koepelschalen en -opstanden, het
dakraam, de keramische tegels en het groendak, die als artikel niet in de
catalogus staan; de PE-afvoer met geluidsisolatie en het U-profiel plooiwerk
op maat, waarvoor geen grondstof bestaat; de baddens 63×175 en 75×225, die de
catalogus in m² prijst terwijl de post per lm verkoopt; en het eindstuk van de
2-delige dakrand, dat het clipssysteem in de catalogus niet heeft.

**Werkuren zitten er niet in.** De brondata van Tectora zetten wel 0,25 u
"werkuren construction" in elke kit, maar de materiaallijst is wat de ploeg op
de camion laadt; uren worden op het project via urenstaten gevolgd en zouden
anders dubbel in de kost zitten.

## De verbruiksnormen

Elke regel is een verbruik **per eenheid van het verkoopproduct** (per m², per
lm, per stuk), uitgedrukt in de eenheid van de grondstof zoals de catalogus die
voert. Dat is precies wat `mrp.bom` verwacht en wat `explode()` vermenigvuldigt
met de verkochte hoeveelheid. De normen staan bovenaan `build_demo_boms.py`
bij elkaar, zodat ze te bespreken en bij te stellen zijn zonder de recepten te
lezen:

| Norm | Waarde | Waarom |
|---|---|---|
| EPDM verkleefd | 1,10 m²/m² | overlap en snijverlies |
| EPDM losliggend (ballast) | 1,08 m²/m² | minder details in de overlap |
| Bonding adhesive BA-2012 (pot 20 l) | 0,016 pot/m² | ~0,32 l/m², beide vlakken → 1 pot per ~62 m² |
| Naad (splice tape 3") | 0,15 m/m² | rollen van 15,25 m plus detailwerk |
| QuickPrime Plus (gallon 3,8 l) | 0,02 gal per m naad | ~75 ml/m, beide zijden |
| Lap sealant | 0,1 koker per m detail | naadeinden en aansluitingen |
| Bitumen (onder- en toplaag) | 1,12 m²/m² | overlap 10 cm op een rol van 1 m |
| Isolatie | 1,03 m²/m² | snijverlies |
| Isolfoam (750 ml) | 0,15 bus/m² | 7 m² per bus, per laag |
| PIR mechanisch | 5,5 schroeven + plaatjes/m² | 4 per plaat 600 × 1200 |
| Rockwool mechanisch | 6 schroeven + plaatjes/m² | 4 per plaat 1000 × 600 |
| Isolatieschroef | kortste lengte ≥ dikte + 30 mm | 30 mm verankering in de ondergrond |
| Dakrandprofiel | 0,34 koppelplaatjes/m, 4 schroeven/m, 0,05 koker/m | element van 3 m, schroef om 25 cm |
| Hoekstuk | 2 koppelplaatjes, 4 schroeven, 0,1 koker | |
| Kimfixatie | batten bar 1 m, 3,5 schroeven, RMA-strip 1,05 m | om de 30 cm vastgezet en afgedekt |
| Ballast | 85 kg rolgrind/m², 0,011 rol geotextiel/m² | laag van 5 cm; rol van 100 m² |
| Afvoerbuis zink/koper | 0,6 scharnierhaken/m | 1 haak per ~1,7 m |
| Afvoerbuis PE | 1,05 m buis, 0,7 beugels, 0,2 elektrolasmoffen/m | buis van 5 m |
| Tapbuis / doorvoer met zelfklevende slab | 0,02 gal primer, 0,15 koker sealant | |
| Dakvloer OSB | 1,08 m², 12 schroeven/m² | kepers om 60 cm, schroef om 30 cm |
| Spouwplaat / multiplex | 1,10 m², 8 schroeven/m² | |
| Bladlood 30 cm × 1,25 mm | 4,5 kg/m | 4,3 kg/m plus overlap |

Twee voorbeelden, zoals ze in Odoo verschijnen:

```
[Demo] Leveren en plaatsen van de dakbedekking type: Elevate Rubbergard EPDM 1,1mm dik verkleefd   (per m²)
   1,100 m²   ELEVATE EPDM FOLIE 1,1MM (15,25X30,5M)
   0,016 st   ELEVATE BONDING ADHESIVE BA-2012 20L/POT
   0,150 m    ELEVATE SPLICE TAPE 7,62CM 3"
   0,003 st   ELEVATE QUICKPRIME PLUS 1 GAL (3,8L)
   0,015 st   ELEVATE LAP SEALANT

[Demo] Leveren en plaatsen 2-delige alu dakrandprofielen in RAL naar keuze   (per lm)
   1,000 m    ALU DAKRAND CLIPS BASISPROFIEL BRUT 3M/ST
   1,000 m    ALU DAKRAND CLIPS ELEVATE OVERZETSTUK RAL KLEUR 3M/ST
   0,340 st   ALU DAKRAND CLIPS BASISPROFIEL BRUT VERBINDING INWENDIG
   0,340 st   ALU DAKRAND CLIPS ELEVATE OVERZETSTUK RAL KLEUR VERBINDING UITWENDIG
   4,000 st   Parco Schroef Zilver 4,5x45 TX25
   0,050 st   SOUDAL SILIRUB EPDM ZW 310ML
```

Voor het referentiedak van het eerste offertesjabloon (renovatie, 100 m²,
40 lm 2-delige dakrand, twee tapbuizen) geeft dat een materiaallijst van 40
regels op 26 verschillende grondstoffen: 110 m² EPDM, 1,6 pot bonding, 110 m²
dampscherm, 103 m² PIR, 15 bussen lijmschuim, 40 m basisprofiel en 40 m
overzetstuk met hun 4 buiten- en 1 binnenhoek, 180 dakrandschroeven, 40 m
batten bar met 140 schroeven, twee tapbuizen met bolroosters, enzovoort. De
afbraak- en algemene posten van dat sjabloon blijven arbeid en staan er niet
in.

### Keuzes in de recepten

* **2-delige dakrand** = het clipssysteem van Modde Heule (basisprofiel brut +
  overzetstuk), omdat dat precies de drie verkochte afwerkingen kent: RAL naar
  keuze, RAL 9005 structuur en geanodiseerd, elk met eigen hoeken en
  verbindingen.
* **Enkelvoudige dakrand** = Bendec DRB (…/62) tot 100 mm en DRBS (…/80) vanaf
  150 mm, in de vier afwerkingen van de prijslijst (RAL divers, Ano, Stock
  kleur, Brut), met de koppelplaatjes van dezelfde hoogte en afwerking.
* **Zinken kraal** = plooiwerk ontwikkeling 150 in de kleur (naturel, Anthra,
  Quartz) met de bijhorende geplooide hoeken; *incl. druiplijst* voegt het
  plooiwerk ontwikkeling 100 en zijn hoeken toe.
* **Ankerpunten**: de EPDM-uitvoering krijgt een QuickSeam pipe flashing, de
  roofinguitvoering een bitumen manchet Ø < 48 mm. De kostprijs in de catalogus
  (150,02 € voor de X-SR-B EPDM) is exact anker + flashing, wat de keuze
  bevestigt.
* **Bolroosters** = de galva bladvangers, niet de inox: de kostprijzen in de
  catalogus volgen die reeks.
* **Dampscherm** op hout krijgt minder hechtprimer (0,008 drukvat/m²) dan op
  beton (0,012).

## Twee prijzen in de catalogus staan per verpakking

De hoeveelheden zijn fysiek juist gehouden; twee grondstoffen dragen in de
catalogus een prijs per verpakking terwijl hun eenheid iets anders zegt. Tot
die prijzen (of eenheden) in de catalogus rechtgezet zijn, is de
**materiaalkost** van deze twee posten in het dashboard te hoog:

| Grondstof | Eenheid | Prijs | Lezing |
|---|---|---|---|
| P01066 Keien rolgrind 16/32 (40 kg/zak) | kg | 9,74 | prijs per **zak** van 40 kg → 0,24 €/kg |
| P01207 / P00479 Iconik basisprofiel / sierlijst 3 m | m | 46,13 | prijs per **element** van 3 m → 15,4 €/m |

## Tijdnormen uit de werkuren van de export

De kits van de export dragen elk een of twee werkurenregels: `werkuren
construction` op de opbouwwerken (610 regels), `werkuren afbraak` op de
afbraakwerken (68), `werkuren veiligheid` (6) en het losse component
`Afbraakwerken` (6), alle in uren per eenheid van de werkpost. Dat is de eigen
tijdnorm van Tectora, en precies wat het veld **Geschatte tijd per eenheid**
(minuten) van `tectora_roof` nodig heeft om een offerte te schatten en de taken
Afbraakwerken en Uitvoeringswerken op het project te dimensioneren.

```bash
python3 tectora_boms/tools/build_labour_norms.py
```

Het script somt per kit de werkuren, neemt per exportproduct de mediaan over
zijn kits (varianten dragen dezelfde tijd; 17 producten wijken af, de mediaan
is dan het veilige midden) en legt elk exportproduct met een **handmatige
mapping** op de catalogusfamilie waarvoor het staat, net als bij de
demo-stuklijsten: één *enkelvoudige dakrandprofiel* uit de export tegen de 28
hoogtes × afwerkingen van de prijslijst. Elke code wordt gecontroleerd; bij een
fout wordt niets geschreven. Resultaat in `tectora_boms/data/labour_norms.json`:
**415 van de 499 verkoopproducten** met een norm, uit 111 exportproducten; 72
exportproducten hebben geen tegenhanger in de catalogus (muurkappen, type C,
Engelse omschrijvingen) of zijn al gedekt door een zusterproduct.

Enkele normen, zoals ze op de productfiche komen:

| Werkpost | Norm |
|---|---|
| EPDM verkleefd (per m²) | 19,8 min |
| EPDM geballast (per m²) | 9 min |
| PIR verkleefd (per m²) | 7,8 min |
| Dampscherm (per m²) | 3,3 min |
| Kimfixatie (per lm) | 6 min |
| 2-delige dakrand (per lm) | 7,2 min |
| Enkelvoudige dakrand, hoek | 4,8 min |
| PE-tapbuis (per stuk) | 30 min |
| Ankerpunt (per stuk) | 22,5 min |
| Verwijderen dakbedekking (per m²) | 12 min |
| Verwijderen dakranden (per lm) | 6 min |

Rockwool Rhinoxx heeft in de export geen werkuren en krijgt dus geen norm.

De module laadt de normen bij installatie en upgrade en **laat een waarde die
het bureau zelf invulde staan**; *Verkoop → Configuratie → Tijdnormen laden uit
stuklijstexport* herlaadt en overschrijft. Het veld hoort bij `tectora_roof`;
zonder die module wordt er niets geladen.

## Hoe het geladen wordt

* Bij **installatie** (post_init_hook) en bij **upgrade** (migratie
  19.0.1.2.0), na de export.
* Elke demo-stuklijst is een **kit** (`phantom`) op het productsjabloon, met
  referentie **Demo** en sleutel `demo:<code>` in *Stuklijstsleutel (import)*.
  Opnieuw laden werkt bij in plaats van te verdubbelen.
* De demo-stuklijsten krijgen **volgorde 0**, vóór de geïmporteerde export
  (volgorde 1 en hoger): `sale.order._tectora_find_boms` neemt de eerste op
  `sequence, id`, dus de materiaallijst gebruikt de demo-stuklijst. Een
  stuklijst die het bureau zelf maakt staat ook op 0 en wint dan enkel als ze
  ouder is; zet ze desnoods vooraan in de lijst.
* **Verkoop → Configuratie → Demo-stuklijsten laden** herlaadt de set (na een
  aanpassing van het JSON-bestand); **Demo-stuklijsten verwijderen** haalt
  alles met sleutel `demo:…` weer weg, voor een database die live gaat. In de
  shell: `env["mrp.bom"]._tectora_import_demo_boms()` en
  `env["mrp.bom"]._tectora_remove_demo_boms()`.

## De demo

1. Maak een offerte uit een van de twintig sjablonen (*Verkoop → Configuratie
   → Offertesjablonen*), of teken een dak en genereer de offerte vanuit de
   opmeting.
2. Bevestig de order: het dakproject wordt aangemaakt en de materiaallijst
   opgebouwd (bericht "Materiaallijst bijgewerkt uit S00xxx: n
   materiaallijn(en)" op het project).
3. Open het project: tab **Materiaallijst** toont per grondstof de benodigde
   hoeveelheid, het verkoopproduct waaruit ze komt en de stuklijst
   (`[Demo] …`); het dashboard toont **Materiaalkost** (hoeveelheid ×
   kostprijs) en **Marge**.
4. Verander een hoeveelheid op de order of voeg een post toe en bevestig
   opnieuw: de lijst wordt herrekend.
