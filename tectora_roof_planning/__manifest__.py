# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Planning",
    "summary": "Plan dakprojecten per ploeg in de Planning-app; elk ploeglid "
    "krijgt een eigen planning-item",
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

The Planning app also gets a "Per ploeg" planner, which becomes the planner
the app opens on: one row per ploeg and one project block per work block,
carrying the project and the site address. Drag or resize the block and the
shifts of every employee on it move along; its summary lists those employees
(take one off to drop their shift) and opens the project overview and the
roof project. Ploegen themselves move from Dakmeting to
Planning -> Configuratie, since that is where they are used. Uninstalling puts
the app's own default planner and the Ploegen menu back.

The project dashboard of Dakmeting lists the employees' shifts on its
Planning tab and its planning card opens the resource planner on them.

Installs itself automatically as soon as both Dakmeting and Planning are
installed.
    """,
    "version": "19.0.1.10.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "planning"],
    "data": [
        "views/planning_slot_views.xml",
        "views/roof_planning_views.xml",
        "views/project_project_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tectora_roof_planning/static/src/team_gantt/team_gantt.scss",
            "tectora_roof_planning/static/src/team_gantt/team_gantt.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "auto_install": True,
    "installable": True,
}
