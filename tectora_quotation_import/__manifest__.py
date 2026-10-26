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
* the wizard checks the file (a test run shows what the import would do);
  the import itself is a job run in the background by a scheduled action,
  committed after every quotation, so a large export never hits the time
  limit of a web request and an interrupted import goes on where it stopped
  (Offerte-imports).
    """,
    "version": "20.0.1.2.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "tectora_products", "sale_crm", "account"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.access.csv",
        "data/import_status_data.xml",
        "data/ir_cron_data.xml",
        "views/import_status_views.xml",
        "views/sale_order_views.xml",
        "views/product_template_views.xml",
        "views/import_job_views.xml",
        "wizard/quotation_import_views.xml",
    ],
    "installable": True,
}
