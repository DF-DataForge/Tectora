# -*- coding: utf-8 -*-
{
    "name": "Tectora Ploegen",
    "summary": "De ploegen als eigen app: leden als contacten, ploegbaas, "
    "voertuigen uit het wagenpark",
    "description": """
Tectora Ploegen
===============
An app of its own around the ploegen (``tectora.roof.team``).

* The members of a ploeg are **contacts** (``res.partner``), not employees
  (that lives in the roofing core): a ploeg lists its contacts and its
  ploegbaas is one of them. A contact can be in more than one ploeg; the
  contact form shows its ploegen.
* Planning and hour registration run on those contacts. Whoever is also an
  employee (the contact is their work contact) gets timesheet lines on top.
* **Wagenpark**: a vehicle of the Fleet app is given to a ploeg. The ploeg
  lists its vehicles, the vehicle form and list show the ploeg, vehicles can
  be searched and grouped by it, and a work block shows the vehicles of its
  ploeg.
* Menu **Ploegen**: the ploegen (kanban, list), their members (the contacts
  in a ploeg) and their vehicles.

Installing takes the existing ploegen along: the employees of a ploeg become
its contacts through their work contact, and its ploegbaas likewise.
    """,
    "version": "20.0.1.1.0",
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
