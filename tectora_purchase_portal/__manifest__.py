# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Inkoop op het medewerkersportaal",
    "summary": "De logistieke lijsten van een werf (afhalen magazijn, "
    "ontvangsten magazijn, dropship op de werf) op het portaal van de ploeg",
    "description": """
Data Forge Dakmeting — Inkoop op het medewerkersportaal
=======================================================
Puts the three logistic lists of a roof project on the site page of the
employee portal, tab Materialen: what the crew picks up from the own
warehouse, what the vendors deliver to the warehouse for this project and
what is dropshipped straight to the site -- each with vendor, purchase order
and delivery status -- plus the PDF of the lists.

Installs itself as soon as Dakmeting — Inkoop and the Medewerkersportaal are
installed.
    """,
    "version": "19.0.1.0.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_purchase", "tectora_portal"],
    "data": [
        "views/portal_templates.xml",
    ],
    "auto_install": True,
    "installable": True,
}
