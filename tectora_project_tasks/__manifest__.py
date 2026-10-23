# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Taakopvolging per fase",
    "summary": "Taken en subtaken per projectfase (mijlpaal) op het projectdashboard, "
    "vanuit een configureerbaar taaksjabloon",
    "description": """
Data Forge Dakmeting — Taakopvolging per fase
=============================================
Task follow-up per project phase, as on the Congristruct project dashboard,
starting from an empty task template.

* **Projectfases** (Dakmeting -> Projectopvolging): every phase becomes a
  milestone on each new project.
* **Taaksjablonen**: per phase the tasks and their subtasks, optional tasks
  (switched off by default, switched on per project) and deadlines relative to
  the project's start or end date. The module ships no phases and no
  templates: they are filled in per company.
* The **project dashboard** gets a "Taken" block: the phases as a timeline,
  the progress of the current phase and its open tasks, ticked off in place.
  "Openen" (or a click on a phase) opens the **task page**: per phase the
  tasks with their subtasks to tick off, options on/off and "Fase afronden".

Automations: a milestone is reached as soon as all (active) main tasks of its
phase are done; all subtasks done -> main task done; ticking a main task ticks
its subtasks. Deadlines follow the project's start and end date.

New projects get their phases and tasks on creation (once phases exist); an
existing project starts the follow-up with "Taakopvolging starten" on the
dashboard.
    """,
    "version": "20.0.1.0.0",
    "category": "Project",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "project"],
    "data": [
        "security/ir.access.csv",
        "views/project_phase_views.xml",
        "views/task_template_views.xml",
        "views/project_task_views.xml",
        "views/project_project_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tectora_project_tasks/static/src/task_phases/task_phases.scss",
            "tectora_project_tasks/static/src/task_phases/task_phases.xml",
            "tectora_project_tasks/static/src/task_phases/labels.js",
            "tectora_project_tasks/static/src/task_phases/board_bus.js",
            "tectora_project_tasks/static/src/task_phases/task_board_controller.js",
            "tectora_project_tasks/static/src/task_phases/phase_timeline.js",
            "tectora_project_tasks/static/src/task_phases/task_phases_widget.js",
            "tectora_project_tasks/static/src/task_phases/tasks_board.js",
        ],
    },
    "auto_install": True,
    "installable": True,
}
