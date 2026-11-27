# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Projectplanning",
    "summary": "Plan projecten per ploeg in de Project-app: planner per "
    "ploeg, per medewerker en per project, zonder de Planning-app",
    "description": """
Data Forge Dakmeting — Projectplanning
======================================
The planner of the projects, inside the Project app (Project -> Planning).
It does not use Odoo's Planning app: the work blocks
(``tectora.roof.planning``) are the planning itself. A block is planned on a
project (of the Project app; through it on its roof project), for a ploeg
and the employees on it.

* **Per ploeg**: one row per ploeg and one block per work block, carrying the
  customer, the municipality of the site, the roof area, the project type and
  the crew size. Drag or resize a block and it moves for everyone on it; drop
  it on another ploeg and it takes that team's members. Its summary lists the
  employees (take one off, add one) and opens the project overview and the
  roof project. Teams set to "Altijd weergeven op planner" always have a row.
* **Per medewerker**: the same blocks, one row per employee -- everyone's own
  planning.
* **Per project**: one row per project.
* The block's colour is its project's; a concept is hatched, a block carried
  out greyed, and a block with an employee who is planned twice in that
  period is outlined in red ("Dubbel ingepland", also a filter and a warning
  on the block).
* The scissors cut a block in two at a day boundary; each part can be
  re-assigned on its own.
* Opened from a project (the Planning button or card of its dashboard), a
  click on free cells plans that project there at once, as a concept block
  on that row's team.
* "Beschikbare momenten": per team the free working days in the coming
  weeks, for a project the days it needs on each team, and "Inplannen" makes
  a concept block there.
* Planned hours per block: 8 hours per working day and per employee; the
  project dashboard totals them.

Weather forecasts from Open-Meteo (no API key) on the work blocks: a
scheduled action fetches every morning the daily forecast of the next 16
days for every site with a work block in that period and keeps it; each block
gets the worst day's weather (icon, temperatures, rain, wind gusts) in its
label in the planner and in its summary, day by day, with a warning when
the weather is no good for roofing work (rain, snow, thunder, gusts from
50 km/h, below 5 °C). "Weer vernieuwen" on the planner, and on the blocks'
list and form, fetches it at once. The site is located by the roof project's
satellite image, else its municipality (Open-Meteo geocoding, kept).

The employee portal (tectora_portal) reads the same work blocks: an employee
sees the sites they are planned on, and the hours they register are booked
for the crew of that day's block. Nothing else is needed for it.

Ploegen move from Dakmeting to Project -> Configuratie, since that is where
they are planned. Uninstalling puts the menu back.

Upgrading from the bridge to the Planning app (up to 20.0.1.x) takes
everything that bridge left in the Planning app out again: its views on the
shifts, its "Per ploeg" menu and default planner, and the shifts the work
blocks made (see migrations/20.0.2.0.0). The work blocks stay as they are.

Needs the gantt view (``web_gantt``, Odoo Enterprise).
    """,
    "version": "20.0.2.1.0",
    "category": "Project",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "web_gantt"],
    "data": [
        "security/ir.access.csv",
        "data/weather_data.xml",
        "views/roof_planning_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tectora_roof_planning/static/src/team_gantt/team_gantt.scss",
            "tectora_roof_planning/static/src/team_gantt/availability_dialog.xml",
            "tectora_roof_planning/static/src/team_gantt/availability_dialog.js",
            "tectora_roof_planning/static/src/team_gantt/team_gantt.xml",
            "tectora_roof_planning/static/src/team_gantt/team_gantt.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    # Installed by hand (no auto_install): the gantt view is Enterprise
    # (web_gantt) and could not be tested with the Odoo 20 port, so a problem
    # there only fails this module's own install, never that of the other
    # Tectora modules. See UPGRADE_NOTES.md.
    "auto_install": False,
    "installable": True,
}
