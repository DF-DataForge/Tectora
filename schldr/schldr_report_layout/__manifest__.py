# -*- coding: utf-8 -*-
{
    "name": "Data Forge — Documentlay-out Schldr",
    "summary": "Documentlay-out met de Schldr accentrand als header, te kiezen in "
    "Instellingen → Documentlay-out en toegepast op alle documenten",
    "description": """
Data Forge — Documentlay-out Schldr
====================================
Adds the **Schldr** layout to *Settings → Configure Document Layout*, next to
Light, Boxed, Bold, Striped, Bubble, Wave and Folder.

The header carries the Schldr accent edge: a soft tint with a slanted line
in the primary colour running over the full page width, the company logo and
tagline on the left and the company details on the right. The document title,
table heads and totals take the company's primary colour; the footer closes
with the same line. Like every layout it follows the colours, font, logo,
tagline, footer text and paper background chosen in the configurator, so it
applies to every document Odoo prints through the external layout: quotations
and orders, invoices, deliveries, purchase orders, and the Schldr measurement and site sheets.

Three more layouts reproduce the Schldr letterhead (briefpapier): **Schldr
Briefpapier**, a band in the primary colour over the full width with the
white Schldr logo, the services and the website, and a light footer band with
the company data, the office address and the bank accounts; **Schldr
Briefpapier licht**, its second colour scheme with the light band at the top
and the coloured band at the bottom; and **Schldr
Briefpapier met accentrand**, the same letterhead with the accent edge as the lower
side of its band.

Installing the module switches every company to the Schldr layout (and gives a
company without a primary colour the Schldr blue); another layout can be
picked again at any time.
    """,
    "version": "20.0.1.0.0",
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
            "schldr_report_layout/static/src/scss/layout_schldr.scss",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
}
