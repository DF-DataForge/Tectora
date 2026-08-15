# Tectora Productcatalogus

Seeds the Odoo product database from the company price book
(`GOOD_LUCK_<year>.xlsx`).

## What gets created on install

- **Product categories** under a `Dakwerken` root, one per price-book chapter,
  numbered (`01. Algemene werken` … `13. Upsale`) so quotations can follow the
  chapter order.
- **Units of measure**: core `Stuk`/`m`/`m²`/`Dag`/`Uur` where available, plus
  `Forfait` (price-book `SOG`/`VH`) and `Week`.
- **226 service products**, one per unique price-book entry. The full
  multi-line specification is the sales description (printed on quotations);
  the internal warnings from column E are the internal note. Products without
  a price carry the tag *Prijs op aanvraag*; the upsale chapter carries the
  tag *Upsale*.
- **Pricelists** `Renovatie`, `Nieuwbouw` and `Industrie`. The product's list
  price is the (indexed) RENOVATIE price; where a sheet prices the same work
  differently, a fixed-price rule is added to that type's pricelist
  (129 rules).

`tectora_roof` picks the pricelist matching the roof project's *Projecttype*
when generating a quotation (by name, no hard dependency between the
modules).

## Refreshing from a new price book

```bash
python3 tools/parse_price_book.py path/to/GOOD_LUCK_20XX.xlsx \
    tectora_products/data/price_book.json
```

Then, on the server, re-run the import (idempotent — products are matched on
their `DAK-XXXX` internal reference, pricelist rules on pricelist+product):

```python
# odoo shell
env["product.template"]._tectora_import_price_book()
env.cr.commit()
```

Reinstalling the module runs the same import automatically. Prices edited by
hand in Odoo on imported products are overwritten by a re-import; the price
book stays the source of truth.

## Not imported (by design)

- The 10-year liability insurance clause, the guarantee text
  (`GARANTIEPAKKET`) and the `ALGEMENE NOTA'S` chapter body: quotation
  clauses, not products. Add them to a quotation template or the sale terms.
- `OVERSTEKEN` (renovatie): "steeds prijs opvragen bij onze partner" — no
  prices to import.
