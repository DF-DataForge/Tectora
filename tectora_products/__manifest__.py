# -*- coding: utf-8 -*-
{
    "name": "Tectora Productcatalogus",
    "summary": "Dakwerken productcatalogus met prijslijsten per projecttype "
    "(renovatie / nieuwbouw / industrie)",
    "description": """
Tectora Productcatalogus
========================
Seeds the product database from the company price book:

* one service product per unique price-book entry, with the full multi-line
  specification as sales description and the internal warnings as note;
* product categories per price-book chapter (Algemene werken,
  Veiligheidsvoorzieningen, Afbraak, Opbouw, ...), numbered so quotations can
  reproduce the chapter order;
* the units of the price book (Stuk, m², m, Forfait, Dag, Uur, Week);
* pricelists Renovatie / Nieuwbouw / Industrie. The base price is the
  (indexed) RENOVATIE price; deviating prices per project type are loaded as
  fixed-price pricelist rules.

The data lives in ``data/price_book.json``, generated from the source
workbook by ``tools/parse_price_book.py`` (in the repository root). The
import runs on module install and can be re-run from an Odoo shell via
``env["product.template"]._tectora_import_price_book()``.
    """,
    "version": "19.0.1.0.0",
    "category": "Sales",
    "license": "LGPL-3",
    "author": "Tectora",
    "website": "https://www.tectora.be",
    "depends": ["product", "sale_management"],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
