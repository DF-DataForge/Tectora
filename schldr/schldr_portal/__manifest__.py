# -*- coding: utf-8 -*-
{
    "name": "Data Forge Schldr — Medewerkersportaal",
    "summary": "Portaal voor de schilders: hun werven raadplegen (overzicht, "
    "materialen, plan, uitvoeringsverslag) en uren registreren met start/stop",
    "description": """
Data Forge Schldr — Medewerkersportaal
=========================================
A portal site for the painters on site. An employee (``hr.employee``)
gets a portal login (an external user, no backend seat) and finds under
*Mijn werven* every painting project they are planned on, as a team member or as
ploegbaas. Each site opens on four tabs:

* **Overzicht**: customer, site address, project type, planned period, team,
  site instructions and the site sheet (werfblad) with the preparation,
  access, transport and safety information;
* **Materialen**: the material list of the project;
* **Plan**: the plan (drawing, rooms, and per room which paint system and colour) and the
  work blocks with the planned employees;
* **Uitvoeringsverslag**: the daily execution reports of the crew (work done,
  materials used, remarks, photos) with a form to add one, and the hours
  registered on the site.

Hours are registered with a **Start** and a **Stop** button on the site. One
timer runs per site; whoever stops it confirms the crew that was present
(pre-filled from the planner: the employees of the work block(s) of that day)
and one timesheet line per employee is written on the project, so the hours
and the labour cost show up in the project dashboard and in the standard
Timesheets reports. Start comes in two: *Start uitvoering* and *Start
afbraak*, and the hours land on the project's task Uitvoeringswerken or
Afbraakwerken -- the tasks the confirmed order sizes with its estimate -- so
preparation and execution stay apart in the timesheets.

Portal access is granted on the employee form (button *Portaaltoegang
geven*): a portal user is created on the employee's work contact and the
invitation e-mail is sent. The reports and the hour registrations are also
visible in the back office, under Schilderwerk and on the project dashboard's
*Uitvoering* tab.
    """,
    "version": "20.0.1.0.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["schldr_paint", "portal", "hr_timesheet"],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "data/portal_entry_data.xml",
        "views/schldr_timer_views.xml",
        "views/schldr_execution_report_views.xml",
        "views/hr_employee_views.xml",
        "views/project_project_views.xml",
        "views/portal_templates.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "schldr_portal/static/src/portal/schldr_portal.scss",
            "schldr_portal/static/src/portal/schldr_portal.js",
        ],
    },
    "installable": True,
    "auto_install": False,
}
