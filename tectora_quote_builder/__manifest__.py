# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Kop- en voetteksten offerte",
    "summary": "De kop- en voetteksten van de offerte (Quote Builder) automatisch op "
    "elke offerte, in de documentlay-out en met de naam van de klant op de voorpagina",
    "description": """
Data Forge Dakmeting — Kop- en voetteksten offerte
==================================================
The headers and footers of the quotation (Sales › Configuration › Headers &
Footers, Odoo's Quote Builder) as the structure of every quotation:

* **Automatic**: every new quotation gets the headers and footers marked "Add
  by default", also the ones of its quotation template when the quotation is
  made in code (from a roof project, or with the company's default template);
  Odoo itself only adds those when the template is chosen in the form.
* **In the document layout**: every page of a header or footer is printed
  with the header and footer of the document layout (Settings › Document
  Layout), like the quotation itself, laid over the page at full size. The
  PDF's own band (heights per document, by default 28 mm at the top and 24 mm
  at the bottom, optionally only on some pages) is left out underneath. Pages
  whose content runs up to the edge can be scaled down to fit between the
  layout's header and footer instead. Per document this can be switched off.
* **Customer name**: the first header can print the customer's name, with
  the salutation of the contact in front (Dhr., Mevr., ...), and the site
  address (the delivery address of the quotation) under it, on its
  first page (e.g. under "Voorstel op maat" on the cover), centred, in the
  company's primary colour, at a height set on the document.
    """,
    "version": "20.0.1.4.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "sale_pdf_quote_builder"],
    "data": [
        "report/report_layout_frame.xml",
        "views/quotation_document_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
