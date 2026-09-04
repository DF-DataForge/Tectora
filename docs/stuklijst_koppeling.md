# Stuklijsten koppelen aan de producten

Analyse van `Stuklijst_Tectora.xlsx` en het voorstel om die stuklijsten aan de
producten in deze database te hangen.

Reproduceren:

```bash
python tectora_products/tools/match_bom_export.py Stuklijst_Tectora.xlsx -o bom_matching.json
```

Het reviewbestand met alle voorstellen staat in
[`Stuklijst_matching_voorstel.xlsx`](Stuklijst_matching_voorstel.xlsx).

## Wat er in het bestand zit

| | |
|---|---|
| Stuklijsten | 692 |
| Stuklijstregels | 3.276 |
| Verschillende stuklijstproducten | 188 |
| Verschillende componenten | 672 (205 families × varianten) |
| Stuklijstsoort | 679 × `Kit` (phantom), 13 × `Produceer dit product` (normal) |
| Regels per stuklijst | mediaan 5, maximaal 10 |

## De kern: de bron werkt met varianten, deze database niet

Componentnamen zijn Odoo-*variantnamen*: sjabloon + attribuutwaarden tussen
haakjes.

```
Buitenhoek DRBS (200mm, geanodiseerd)      <- bron: sjabloon + 2 attributen
Buitenhoek DRBS 200/80 Ano **              <- deze catalogus: één platte naam
```

Daardoor is er geen gemeenschappelijke sleutel én nauwelijks een
gemeenschappelijk vocabulaire:

* op naam matchen levert 7 van de 672 componenten op;
* op artikelcode kan bijna niet: slechts 12 componentnamen dragen een `[code]`;
* 71 van de 188 producten hebben meerdere stuklijsten die enkel in kleur of maat
  verschillen (grootste reeks: 65 stuklijsten voor één product).

De koppeling moet dus uit de *structuur* van de namen komen.

## De drie sleutels van de matcher

Per component, eerste die aanslaat wint:

1. **`code`** — een `[artikelcode]` tegen de leverancierscode of een code die in
   een catalogusnaam zit, of een exact gelijke naam.
2. **`rule`** — een kleine trefwoordtabel; de werkuren hebben niets meer nodig
   (`werkuren construction` → `Werkuren opbouwwerken`).
3. **`structure`** — familietokens + de *eerste* maat + de afwerkingsklasse.
   Dit werkt omdat de catalogus zijn profielreeksen zo benoemt. De eerste maat
   telt zwaarder: `DRB 60 met nuttige hoogte onder oplegvlak: 45mm` is een 60,
   geen 45.

De afwerkingsas wordt teruggebracht tot wat de catalogus écht onderscheidt: per
profielreeks bestaat een geanodiseerd artikel (`Ano`) en een gelakt artikel
(`Ral divers`). **Een specifieke RAL bestaat niet als apart artikel** — `RAL
9006`, `RAL 7016` en `RAL naar keuze` vallen dus samen op één klasse.

## Resultaat

| | producten (188) | componenten (672) | stuklijstregels (3.276) |
|---|---|---|---|
| automatisch (≥ 0,70) | 88 | 63 | 806 (25%) |
| nakijken (0,45–0,70) | 68 | 161 | 251 (8%) |
| handmatig (< 0,45) | 32 | 448 | 2.219 (68%) |

Van de 88 automatische producten zijn er 39 letterlijk dezelfde naam.

Het handmatige deel lijkt groot maar is scheef verdeeld: **de tien zwaarste
componenten dekken 1.419 van die 2.219 regels.** Met die tien met de hand
gemapt staat de dekking op 76%, met dertig op 81%.

| regels | component |
|---|---|
| 324 | FRP Primer Semi-Adhesive (blauw) - 3.80 L |
| 305 | Parco Pianos 4 x 17 |
| 290 | Rubberkit voor afkitten tapes 305ml |
| 273 | [08.03.127.3050] Cover tape 5"- dakrandentape 127 mm x 30,5m |
| 90 | ISOL FOAM 750ml lijmschuim 7m² per bus brandklasse B1 |
| 41 | FRP Bonding contactlijm (3000) |
| 31 | Nadentape zelfklevend - breedte 76 mm |
| 24 | Flashingtape 30cm |
| 23 + 18 | UTHERM FLAT ROOF PIR L (dikte 10cm / 3cm) |

## Twee zaken die het bestand niet kan beslissen

### 1. De eenheden zijn verpakkingen, geen Odoo-eenheden

30% van de regels (973) staat in een verpakkingseenheid: `Doos 500 stuks`,
`m- rol 30,5m`, `m² per plaat 2,40 x 1,20`, `m per 3m element`. De catalogus
kent `unit`, `m`, `m2`, `hour`, `kg`.

Erger: **de basis van het aantal wisselt per regel**, binnen één stuklijstfamilie.
Uit de stuklijst van de 2-delige dakrand (per m):

| aantal | eenheid | component | lezing |
|---|---|---|---|
| 1 | `m per 3m element` | Dakrand sierplaat 70mm (geanodiseerd) | aantal in **meter** — het label is enkel verpakkingsinfo |
| 0,34 | `St` | Dakrand sierplaat 70mm (RAL 9006) | aantal in **stuks** — ⅓ van een element van 3 m |

Zelfde artikel, andere afwerking, andere eenheidsbasis. Dit is per regel een
menselijke keuze; automatisch omrekenen zou een deel van de stuklijsten stil
verkeerd zetten.

### 2. 32 producten bestaan hier niet

`Afbraak schoorsteen`, `Bekleding oversteek`, `Af- en aankoppelen van Airco
unit`, … hebben geen tegenhanger in de 226 verkoopproducten. Ofwel worden die
nog aangemaakt, ofwel horen ze niet in dit prijsboek.

## Voorstel voor de varianten

Odoo staat meerdere stuklijsten per product toe en `_bom_find` neemt de eerste
op `sequence`. Dat is genoeg om het hele bestand nu te laden zonder de
productstructuur te wijzigen:

* **één stuklijst per product** (117 van de 188): rechtstreeks koppelen;
* **meerdere stuklijsten** (71): allemaal importeren op hetzelfde product, met de
  variant in het veld `code` van de stuklijst (`RAL 9006`, `DRB 120`), en
  `sequence` zo dat de standaardvariant (geanodiseerd) vooraan staat. De
  materiaallijst pakt dan de standaard; wie een andere kleur verkoopt, kiest de
  andere stuklijst.

Echte productvarianten (`product.attribute` "Afwerking" / "Maat") zijn de
getrouwe modellering en passen op zich in de app — het tekenblad wijst al
`product.product` toe, dus varianten. Maar ze maken de productkiezer op de
tekening zwaar (65 regels voor één dakrandproduct) en ze vragen dat de
catalogus eerst de kleurvarianten als artikel kent, wat vandaag niet zo is.
Aanbeveling: eerst de stuklijsten laden zoals hierboven, en varianten pas
invoeren voor de families waar de kleur de materiaalprijs echt verandert.

## Waar de componenten terechtkomen

De catalogus staat in twee takken: de hoofdstukken zelf houden de
**verkoopproducten** (diensten, wat op een offerte kan), en dezelfde
hoofdstukstructuur onder **Grondstoffen** houdt de materialen (niet
verkoopbaar, wel aankoopbaar). De componenten van een stuklijst zijn per
definitie grondstoffen; de stuklijst zelf hangt aan een verkoopproduct.

## De implementatie

De module `tectora_boms` (installeert zichzelf zodra Productcatalogus én
Manufacturing aanwezig zijn) laadt de export bij **installatie en bij
upgrade** uit `data/bom_catalog.json` — met enkel de zekere matches, dus 269
stuklijsten en 345 regels. Regenereer dat bestand met
`tools/parse_bom_export.py` als Tectora een nieuwe export stuurt.

Een **stuklijst op een dienst** is mogelijk: het veld van Odoo biedt alleen
goederen aan (`domain="[('type', '=', 'consu')]"`), maar de verkoopproducten
van Tectora zijn diensten — precies de producten die een stuklijst dragen. Het
domein is daarom verruimd en de knop "Stuklijst" op de productfiche is
zichtbaar gemaakt voor diensten. Niets in `mrp` handhaaft het type verder:
`explode()` kijkt niet naar het type van het bovenliggende product.

Daarnaast is er **Verkoop → Configuratie → Stuklijsten importeren** voor een
nieuw bestand of een lagere drempel:

* de matcher zit in `models/bom_rules.py` — pure Python, dus testbaar zonder
  database;
* drempels per soort: alleen zekere matches (standaard) of ook waarschijnlijke;
* verpakkingseenheden: overslaan (standaard), omrekenen, of letterlijk
  overnemen;
* **Alleen analyseren** staat standaard aan: het verslag is identiek aan dat van
  een echte import, er wordt alleen niets aangemaakt;
* het verslag lijst op wat niet gekoppeld raakte, gesorteerd op het aantal
  regels dat het blokkeert — dat is de wachtrij uit de tabel hierboven;
* de import is idempotent op `tectora_bom_key` (product + regels), dus een
  tweede import werkt bij in plaats van te verdubbelen, en de 36 identieke
  stuklijsten uit de bron worden samengevoegd.

Één ding kwam pas bij het implementeren boven: **`mrp.bom._bom_find` laat
diensten vallen** (`products.filtered(lambda p: p.type != 'service')`), en de
verkoopproducten van Tectora *zijn* diensten. De materiaallijst zou dus leeg
blijven, hoeveel stuklijsten er ook hangen. `sale.order` zoekt de stuklijst
daarom nu zelf op, in dezelfde volgorde als Odoo (`sequence, id`), en slaat
alleen diensten *zonder* stuklijst over — dat is uurloon, geen materiaal.
`explode()` zelf kijkt niet naar het type van het bovenliggende product en
werkt dus gewoon.

## Volgorde van werken

1. **Producten bevestigen** (188 rijen, blad `Producten`). Kleinste stap, en
   alles hangt eraan: zonder product geen stuklijst.
2. **De tien zwaarste componenten mappen** — driekwart van alle regels.
3. **De eenheidsbasis vastleggen** per verpakkingseenheid, of per regel waar het
   wisselt.
4. **Importeren** wat bevestigd is; de rest blijft in het reviewbestand staan.
5. De staart van 448 componenten afwerken naargelang die in echte projecten
   opduikt.
