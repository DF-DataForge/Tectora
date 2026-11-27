# -*- coding: utf-8 -*-
{
    "name": "Tectora Ploegen",
    "summary": "De ploegen als eigen app: leden als contacten, ploegbaas, "
    "voertuigen uit het wagenpark",
    "description": """
Tectora Ploegen
===============
An app of its own around the ploegen (``tectora.roof.team``).

* The members of a ploeg are **contacts** (``res.partner``), not employees:
  a ploeg lists its contacts and its ploegbaas is one of them. A contact can
  be in more than one ploeg; the contact form shows its ploegen.
* Whoever is also an employee still takes part in everything that works per
  employee -- the work blocks of the planner, the employee portal, the hours
  booked as timesheets: the employees of a ploeg are those whose work
  contact is one of its contacts. A ploeg without contacts keeps its
  employees as before (the ploeg on the employee form, or its department).
* **Wagenpark**: a vehicle of the Fleet app is given to a ploeg. The ploeg
  lists its vehicles, the vehicle form and list show the ploeg, vehicles can
  be searched and grouped by it, and a work block shows the vehicles of its
  ploeg.
* Menu **Ploegen**: the ploegen (kanban, list), their members (the contacts
  in a ploeg) and their vehicles.

Installing takes the existing ploegen along: the employees of a ploeg become
its contacts through their work contact, and its ploegbaas likewise.
    """,
    "version": "20.0.1.0.0",
    "category": "Human Resources",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "fleet", "contacts"],
    "data": [
        "views/roof_team_views.xml",
        "views/res_partner_views.xml",
        "views/fleet_vehicle_views.xml",
        "views/roof_planning_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
    "auto_install": False,
}
