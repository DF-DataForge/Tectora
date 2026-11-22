# -*- coding: utf-8 -*-
{
    "name": "Data Forge Schldr",
    "summary": "Teken de ruimtes van een woning, zet er verfsystemen op en maak "
    "de offerte, het project en de materiaallijst uit het plan",
    "description": """
Schldr
======
Planning interior painting, fully inside Odoo:

* Draw the rooms of a house in 2D on a plan, per level, by typing sizes or
  tracing an uploaded floor plan. A ceiling height turns every room into a
  space: each wall, the ceiling, the floor, sloped ceilings, skirting,
  mouldings, door leaves, frames and radiators are measured. Doors and windows
  are cut out of their wall; their reveals are added.
* Paint systems are what is done to a surface and sold as one works item: a
  preparation and layers (primer, intermediate coat, finish), each with its
  product, its number of coats, its spreading rate and its time. A project
  sets a system and a colour per kind of surface once; a room follows that
  unless it says otherwise.
* The quotation follows the plan: a section per room (or a line per system),
  quantities from the measurement. A line that is on the quotation already
  keeps its price and discount when the plan changes.
* One painting project stands against one order, in both directions:
  customer, opportunity, salesperson, deadline, pricelist/project type and
  site address are kept equal.
* Confirming the order creates the plannable project (Odoo Project) with its
  analytic account, the tasks Voorbereiding and Schilderwerken sized from
  the time norms, and the material list: per product and colour what the
  layers take, rounded up to the pots the product comes in.
* Measurement sheet and site sheet as PDF, with the colour schedule per room.

Schldr is a fork of the Tectora roofing addons: the order, project, crew and
planning flow is theirs, drawing and calculating are new.
    """,
    "version": "20.0.1.0.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["sale_management", "crm", "project", "sale_project", "hr"],
    "external_dependencies": {"python": ["PIL"]},
    "data": [
        "security/ir.access.csv",
        "data/ir_sequence_data.xml",
        "data/utm_source_data.xml",
        "data/project_task_type_data.xml",
        "data/partner_title_data.xml",
        "data/element_type_data.xml",
        "views/schldr_system_views.xml",
        "views/schldr_project_views.xml",
        "views/schldr_material_views.xml",
        "views/schldr_team_views.xml",
        "views/hr_employee_views.xml",
        "views/schldr_work_block_views.xml",
        "views/sale_order_views.xml",
        "views/project_project_views.xml",
        "views/res_config_settings_views.xml",
        "views/product_template_views.xml",
        "views/crm_lead_views.xml",
        "views/res_partner_views.xml",
        "views/sale_portal_templates.xml",
        "report/schldr_project_report.xml",
        "report/sale_order_report.xml",
        "report/schldr_project_info_report.xml",
        "report/terms_report.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "schldr_paint/static/src/schldr_form/chatter_bottom.js",
            "schldr_paint/static/src/sale_order_line/add_line_below_selection.xml",
            "schldr_paint/static/src/sale_order_line/add_line_below_selection.js",
            "schldr_paint/static/src/sale_order_line/catalog_insert_position.js",
            "schldr_paint/static/src/sale_order_line/enter_adds_line.js",
            "schldr_paint/static/src/plan_editor/lib/*.js",
            "schldr_paint/static/src/plan_editor/plan_editor.scss",
            "schldr_paint/static/src/plan_editor/plan_view.js",
            "schldr_paint/static/src/plan_editor/plan_3d.xml",
            "schldr_paint/static/src/plan_editor/plan_3d.js",
            "schldr_paint/static/src/plan_editor/plan_editor.xml",
            "schldr_paint/static/src/plan_editor/plan_editor.js",
            "schldr_paint/static/src/project_dashboard/project_dashboard.scss",
            "schldr_paint/static/src/project_overview/project_overview.scss",
            "schldr_paint/static/src/project_overview/project_overview.xml",
            "schldr_paint/static/src/project_overview/project_overview.js",
        ],
    },
    "application": True,
    "installable": True,
}
