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
- **Type**: producten met een leverancier zijn voorraadartikelen
  (aankoopbaar); producten zonder leverancier zijn de werkposten uit het
  prijsboek en worden diensten (459 diensten, 1038 materialen).
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

## Prijsboek (historiek)

De vorige bron — het werkenprijsboek `GOOD_LUCK_2023.xlsx` — blijft beschikbaar
via `tools/parse_price_book.py`, `data/price_book.json` en
`env["product.template"]._tectora_import_price_book()`, samen met de
prijslijsten Renovatie / Nieuwbouw / Industrie. Die import wordt niet meer
automatisch uitgevoerd.
