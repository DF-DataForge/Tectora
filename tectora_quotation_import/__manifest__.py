# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Offerte-import",
    "summary": "Offertes uit het oude systeem (Simpla-export) importeren als "
    "verkooporders met hun verkoopkans, in de juiste staat en fase",
    "description": """
Data Forge Dakmeting — Offerte-import
=====================================
Imports the quotation export of the old system (Simpla: one row per
quotation line) as Odoo sale orders, each with its opportunity, through
Sales -> Configuration -> Offertes importeren (oud systeem). Meant to be run
again on every new export, also on the live database:

* the quotation number of the old system is kept on the order (and by
  default becomes the order number); a quotation already in Odoo is never
  created twice, its status can be brought forward (a quotation approved
  since becomes a confirmed order, its opportunity won);
* the status of the old system decides the state of the order and the stage
  of its opportunity, configurable per status (Statussen oud systeem):
  openstaand / ON HOLD / niet goedgekeurd -> sent quotation, opportunity in
  "Lopende offerte"; goedgekeurd / deels gefactureerd / gefactureerd ->
  confirmed order, opportunity in "Gewonnen". Fully invoiced orders count as
  invoiced in Odoo (the invoices live in the old system) and get no roof
  project or project; the others get them as any order confirmed in Odoo;
* customers are matched on VAT number, then on name and postcode, else
  created; lines are matched on the name of a sellable catalogue product,
  else put on the generic works item "Werkpost (oud systeem)" with their own
  description, unit and price; prices, discounts and VAT rates are those of
  the old quotation and are never re-priced by Odoo;
* lines whose amount is a whole multiple of quantity x price (multiplied in
  the old system) get that factor on their quantity, so every total matches
  the export; title and text lines (the export sorts lines alphabetically,
  so titles no longer stand above their lines) are skipped or added as
  notes;
* a test run processes the whole file and rolls everything back, and the
  import can run in parts (maximum number of new quotations per run).
    """,
    "version": "20.0.1.0.1",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "tectora_products", "sale_crm"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.access.csv",
        "data/import_status_data.xml",
        "views/import_status_views.xml",
        "views/sale_order_views.xml",
        "wizard/quotation_import_views.xml",
    ],
    "installable": True,
}
