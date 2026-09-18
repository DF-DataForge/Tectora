# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Medewerkersportaal",
    "summary": "Portaal voor de dakwerkers: hun werven raadplegen (overzicht, "
    "materialen, plan, uitvoeringsverslag) en uren registreren met start/stop",
    "description": """
Data Forge Dakmeting — Medewerkersportaal
=========================================
A portal site for the employees on the roofs. An employee (``hr.employee``)
gets a portal login (an external user, no backend seat) and finds under
*Mijn werven* every roof project they are planned on, as a team member or as
ploegbaas. Each site opens on four tabs:

* **Overzicht**: customer, site address, project type, planned period, team,
  site instructions and the site sheet (werfblad) with the preparation,
  access, transport and safety information;
* **Materialen**: the material list of the project;
* **Plan**: the roof plan (drawing, sections, roof objects, m² and m) and the
  work blocks with the planned employees;
* **Uitvoeringsverslag**: the daily execution reports of the crew (work done,
  materials used, remarks, photos) with a form to add one, and the hours
  registered on the site.

Hours are registered with a **Start** and a **Stop** button on the site. One
timer runs per site; whoever stops it confirms the crew that was present
(pre-filled from the planner: the employees of the work block(s) of that day)
and one timesheet line per employee is written on the project, so the hours
and the labour cost show up in the project dashboard and in the standard
Timesheets reports.

Portal access is granted on the employee form (button *Portaaltoegang
geven*): a portal user is created on the employee's work contact and the
invitation e-mail is sent. The reports and the hour registrations are also
visible in the back office, under Dakmeting and on the project dashboard's
*Uitvoering* tab.
    """,
    "version": "19.0.1.0.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "portal", "hr_timesheet"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/roof_timer_views.xml",
        "views/roof_execution_report_views.xml",
        "views/hr_employee_views.xml",
        "views/project_project_views.xml",
        "views/portal_templates.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "tectora_portal/static/src/portal/tectora_portal.scss",
            "tectora_portal/static/src/portal/tectora_portal.js",
        ],
    },
    "installable": True,
    "auto_install": False,
}
