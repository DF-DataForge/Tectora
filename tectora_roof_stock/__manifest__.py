# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Voorraad",
    "summary": "Zet de materiaallijst van een dakproject klaar als uitgaande "
    "levering",
    "description": """
Data Forge Dakmeting — Voorraad
===============================
Bridge between the roof projects and Inventory.

The material list of a roof project (built from the bills of materials of
the sold works items when the order is confirmed) is what the crew loads on
the van. *Levering klaarzetten* turns it into an outgoing transfer of the
company's warehouse: one move per material, quantities added up over the
list, addressed to the site (the order's delivery address), scheduled on the
planned start of the works and linked to the order, so it shows among the
order's deliveries and on the project dashboard's Leveringen card.

Running it again ships only what is not yet on a transfer: the quantities
already on the project's material transfers (waiting, ready or done) are
deducted, so a material list that grew after a change order gives a second
transfer with the difference, and nothing is shipped twice. Services on the
list (labour) are skipped; only goods move.

Installs itself with Inventory.
    """,
    "version": "19.0.1.0.0",
    "category": "Inventory",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "sale_stock"],
    "data": [
        "views/stock_picking_views.xml",
        "views/roof_project_views.xml",
        "views/project_project_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
