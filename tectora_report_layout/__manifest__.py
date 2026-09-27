# -*- coding: utf-8 -*-
{
    "name": "Data Forge — Documentlay-out Tectora",
    "summary": "Documentlay-out met de Tectora dakrand als header, te kiezen in "
    "Instellingen → Documentlay-out en toegepast op alle documenten",
    "description": """
Data Forge — Documentlay-out Tectora
====================================
Adds the **Tectora** layout to *Settings → Configure Document Layout*, next to
Light, Boxed, Bold, Striped, Bubble, Wave and Folder.

The header carries the Tectora roof edge: a soft sky tint with the teal ridge
line of a flat roof running over the full page width, the company logo and
tagline on the left and the company details on the right. The document title,
table heads and totals take the company's primary colour; the footer closes
with the same line. Like every layout it follows the colours, font, logo,
tagline, footer text and paper background chosen in the configurator, so it
applies to every document Odoo prints through the external layout: quotations
and orders, invoices, deliveries, purchase orders, and the Dakmeting sheets.

Installing the module switches every company to this layout (and gives a
company without a primary colour the Tectora teal); another layout can be
picked again at any time.
    """,
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["web"],
    "data": [
        "views/report_templates.xml",
        "data/report_layout_data.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "tectora_report_layout/static/src/scss/layout_tectora.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
