# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Planning",
    "summary": "Zet de werkblokken van een dakproject om in planning-items "
    "per medewerker in de Planning-app",
    "description": """
Data Forge Dakmeting — Planning
===============================
Bridge between the roof measurement projects and Odoo Planning.

A work block (``tectora.roof.planning``) on a roof project keeps the project
information and the team assignment; this bridge turns every assigned employee
into a real planning shift (``planning.slot``), so the shifts show up in the
Planning app, in the employees' own planning and in every standard Planning
report.

* the shifts follow the block: changing its dates, its employees or its state
  updates (or removes) the corresponding shifts;
* splitting a work block per day splits the employees' shifts along with it,
  and each resulting block can be re-assigned independently;
* deleting a block removes its shifts.

Installs itself automatically as soon as both Dakmeting and Planning are
installed.
    """,
    "version": "19.0.1.1.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "planning"],
    "data": [
        "views/planning_slot_views.xml",
        "views/roof_planning_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
