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

## Verversen na een nieuwe export

```bash
python3 tools/parse_product_export.py producten_Tectora_BV_<datum>.xlsx \
    tectora_products/data/product_catalog.json
```

Daarna op de server (idempotent):

```python
# odoo shell
env["product.template"]._tectora_import_product_catalog()
env.cr.commit()
```

Herinstalleren van de module doet hetzelfde automatisch.

## Prijsboek (historiek)

De vorige bron — het werkenprijsboek `GOOD_LUCK_2023.xlsx` — blijft beschikbaar
via `tools/parse_price_book.py`, `data/price_book.json` en
`env["product.template"]._tectora_import_price_book()`, samen met de
prijslijsten Renovatie / Nieuwbouw / Industrie. Die import wordt niet meer
automatisch uitgevoerd.
