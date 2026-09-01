# Data Forge Productcatalogus

Vult de Odoo-productendatabase met de **leverancierscatalogus** van Tectora
(export `producten_Tectora_BV_*.xlsx`, 1497 producten).

## Wat de import doet

- **Categorieën**: bestaande categorieën worden hergebruikt (01. Algemene
  werken, 02. Dakranden, 02. Verplichte veiligheidsvoorzieningen,
  03. Afbraakwerken, 05. Koepels, 06. Dakramen, 08. Terrasvloer). Voor de
  materiaalfamilies die geen bestaande werkcategorie hebben, komen
  **subcategorieën onder 04. Opbouwwerken plat dak**: Afvoer, Isolatie,
  Afdichting, Bevestigingsmaterialen, Hout & plaatmateriaal, Doorvoeren &
  schoorsteen, Gereedschap & klein materiaal.
- **Classificatie** in drie signalen: de kolom `productgroup` (565 producten),
  daarna trefwoorden in de Nederlandse naam (793) en als laatste de
  leverancier, wiens assortiment homogeen is (143). Geen enkel product valt
  nog in een restcategorie.
- **Prijzen**: `aankoopprijs` wordt de kostprijs, `verkoopprijs` de
  verkoopprijs. Ontbreekt de verkoopprijs (926 producten), dan wordt
  `adviesprijs` gebruikt of anders de kostprijs × **1,85** — de mediaan van de
  eigen catalogus (en tegelijk de meest voorkomende verhouding). Die producten
  krijgen de tag *Prijs berekend*; producten zonder enige prijs de tag *Prijs
  op aanvraag*.
- **Leveranciers**: 15 leveranciers worden als relatie aangemaakt (of
  hergebruikt) met een leverancierslijn per product: aankoopprijs en de
  productcode van de leverancier. `DEFRANCQ`/`DEFRANCQ BOUWSPECIALITEITEN`
  worden samengevoegd.
- **Type**: de export nummert zijn twee prijslijsten uit elkaar — `S0001…` zijn
  de **werkposten** die geoffreerd worden, `P0001…` de artikels die aangekocht
  worden. Een `S`-referentie is dus altijd een verkoopproduct, ook al staat er
  een leverancier bij (bij *Leveren en plaatsen van de koepelschaal type:
  Skylux* staat Cintralux als leverancier van het materiaal, niet als teken dat
  de post zelf voorraad is). Voor een rij zonder referentie beslist de
  leverancier: mét leverancier een voorraadartikel, zonder leverancier een
  dienst. Samen 499 diensten en 998 materialen.
- **Eenheden** worden genormaliseerd naar Stuk, m, m², kg, Uur, Dag en
  Forfait; verpakkingsinfo ("12 stuks", "20 BOX", rol, doos) gaat naar de
  omschrijving.
- **EAN-nummers** worden als barcode gezet waar ze uniek en plausibel zijn.
- De oude prijsboekproducten (`DAK-*`) worden **gearchiveerd**, niet verwijderd:
  bestaande offertes en orders blijven intact.

## Catalogus importeren (in Odoo)

**Verkoop → Configuratie → Catalogus importeren** opent een venster waarin je de
export (.xlsx) oplaadt. Geen shell, geen upgrade nodig — te gebruiken bij elke
nieuwe prijslijst van een leverancier.

Kolommen worden op naam herkend, met synonymen: **interne referentie**
(`interne referentie`, `productcode`, `referentie`, `code`), naam (`naam NL`,
`naam`), **productcategorie** (`productcategorie`, `categorie`, `categ_id`),
aankoopprijs, verkoopprijs, adviesprijs, eenheid, leverancier, leverancierscode,
EAN, gewicht, merk en een type-kolom.

Twee keuzes bepalen het resultaat:

| Optie | Betekenis |
|---|---|
| **Productcategorie: automatisch** | De productgroep, de naam en de leverancier bepalen de bestaande categorie (de ingebouwde indeling). |
| **Productcategorie: uit de kolom** | De categorie uit het bestand wordt letterlijk gebruikt en indien nodig aangemaakt; een pad met `/` maakt subcategorieën (`Dakwerken/Afdichting`). |
| **Soort: automatisch** | Rij met leverancier = **grondstof**, zonder leverancier = **verkoopproduct**. |
| **Soort: uit een type-kolom** | Woorden als *dienst/werkuren* → verkoopproduct, *grondstof/materiaal/voorraad* → grondstof. |
| **Soort: alles als dienst / alles als grondstof** | Handmatig, voor een bestand met één soort. |

Het verschil tussen beide soorten in Odoo:

- **Verkoopproducten (diensten)**: `type = service`, verkoopbaar, niet
  aankoopbaar, geen voorraad. Dit zijn de posten die je offreert.
- **Grondstoffen (voorraadproducten)**: `type = consu` met voorraadbeheer,
  aankoopbaar, met een leverancierslijn (aankoopprijs + leverancierscode).
  Standaard **niet** verkoopbaar, zodat enkel de verkoopproducten in offertes
  en in de productkiezer van de tekening verschijnen — aan te vinken met
  *Grondstoffen ook verkoopbaar* als je ze toch wil kunnen offreren.

Verder: producten worden gematcht op interne referentie (zonder referentie op
naam binnen de categorie, dus geen dubbels), ontbrekende verkoopprijzen worden
berekend met de instelbare marge-coëfficiënt (standaard 1,85), en na de import
toont het venster een samenvatting: aantal nieuw/bijgewerkt, diensten versus
grondstoffen, leverancierslijnen, berekende prijzen en overgeslagen rijen.

## Verversen na een nieuwe export

Gebruik gewoon de wizard hierboven. Wil je de catalogus die met de module
meegeleverd wordt (voor een verse installatie) verversen, dan genereert dit
script hetzelfde bestand met exact dezelfde regels:

```bash
python3 tools/parse_product_export.py producten_Tectora_BV_<datum>.xlsx \
    tectora_products/data/product_catalog.json
```

Bij installatie wordt dat bestand geïmporteerd; bij een upgrade doet de
migratie van 19.0.2.0.0 hetzelfde.

## Offertesjablonen

Twintig startpunten voor een offerte, opgebouwd uit dezelfde catalogus:
**tien renovatie** (mét afbraakwerken) en **tien nieuwbouw** (zonder). Ze staan
onder **Verkoop → Configuratie → Offertesjablonen** en worden geladen via
**Verkoop → Configuratie → Offertesjablonen laden**.

Elk sjabloon heeft dezelfde ruggengraat, in secties:

| Sectie | Inhoud |
|---|---|
| Algemene werken | Vaste kosten, verticaal transport (manueel bij renovatie, camionkraan bij nieuwbouw), afvalverwerking. |
| Verplichte veiligheidsvoorzieningen | Twee permanente ankerpunten en tijdelijke balustrades over de volledige omtrek. |
| Afbraakwerken | **Enkel bij renovatie**: de bestaande bedekking, de dakranden, de tapbuizen en wat daarbij hoort. |
| Dakopbouw | Eén dampscherm, één isolatie, één dakbedekking, plus de kimfixatie — en bij een geballast systeem het grind met grindvangers. |
| Dakranden en hoeken | Eén dakrandtype met **de binnen- en buitenhoek die bij dat profiel horen**. |
| Regenwaterafvoer | Tapbuizen met bolrooster. |
| Opties | Koepel of dakraam, parkeervergunning, stelling en keuring, hoogwerker, noodspuwer, afvoerbuis. Optionele lijnen: ze staan op de offerte maar tellen niet mee. |

De twintig variëren in dakbedekking (Elevate EPDM 1,1 of 1,5 mm, verkleefd of
geballast, en 2-laagse bitumineuze roofing), isolatie (PIR 10 tot 20 cm en
Rockwool 16 cm voor een onbrandbaar pakket) en dakrand (2-delig aluminium in
RAL, RAL 9005 of geanodiseerd; enkelvoudig 100/150/175/200 mm; zinken kraal in
naturel, Anthra of Quartz; aluminium kraal Iconik). Verder zijn er varianten
voor een dakterras, een industriedak en een bijgebouw of carport.

De hoeveelheden beschrijven één **referentiedak**: 100 m² dakvlak, 40 lm
dakrand, één binnenhoek, vier buitenhoeken en twee tapbuizen. Ze worden
overschreven door de opmeting — de tekening voedt de offerte — maar een
sjabloon vol enen zou de rand- en hoeklijnen betekenisloos maken.

Het laden is idempotent en **overschrijft nooit de lijnen van een sjabloon dat
het bureau al heeft bijgesteld**; enkel de naam, de geldigheidsduur en de
voorwaarden volgen het bestand. Wil je toch terug naar de meegeleverde versie,
vink dan *Bestaande sjablonen opnieuw opbouwen* aan.

Het bestand `data/quotation_templates.json` wordt gegenereerd door
`tools/build_quotation_templates.py`. Dat script controleert elke
productreferentie tegen de catalogus en controleert dat elke hoek bij het
profiel hoort waar hij onder staat — een hoek uit een andere profielfamilie is
de fout waarvoor die controle bestaat. Bij een fout schrijft het niets weg.

```bash
python3 tools/build_quotation_templates.py
```

## Prijsboek (historiek)

De vorige bron — het werkenprijsboek `GOOD_LUCK_2023.xlsx` — blijft beschikbaar
via `tools/parse_price_book.py`, `data/price_book.json` en
`env["product.template"]._tectora_import_price_book()`, samen met de
prijslijsten Renovatie / Nieuwbouw / Industrie. Die import wordt niet meer
automatisch uitgevoerd.
