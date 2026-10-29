# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Bestellijst",
    "summary": "Bestellijst per project: onderdelen afvinken, leverancier kiezen, "
    "bestellen en levering opvolgen, vanuit configureerbare onderdelen",
    "description": """
Data Forge Dakmeting — Bestellijst
==================================
The order list (bestellijst) of the Congristruct project dashboard, starting
from an empty list of standard parts.

* **Bestellijst-onderdelen** (Dakmeting -> Projectopvolging): the standard
  parts every new project's order list starts from, in order (longest lead
  time first), with the action "Bestellen" (always order for the project) or
  "Stock eerst" (check the stock, order only the shortage), the suggested
  suppliers and a note on them. The module ships no parts: they are added by
  hand or imported from the standardised Excel list (Projectopvolging ›
  Bestellijst importeren, with the list to download).
* Per project: tick a part off, choose the supplier, the order date and the
  expected delivery date, add the products needed, and create the request for
  quotation in one click. On the order list page, "Producten" under a part
  lists the products its supplier delivers (their supplier prices): tick
  them, set the quantity, and "Bestellen" puts exactly those on the request
  for quotation. "Stock eerst" orders only what the free stock does
  not cover. The purchase order carries the project (and so its analytic
  account) and the order list line; the line's status follows it
  (te bestellen, uit stock, prijsaanvraag, besteld, ontvangen, afgevinkt) and
  shows when the expected delivery is late.
* The **project dashboard** gets a "Bestellijst" block next to "Taken": the
  progress and the next parts to order; "Openen" opens the order list page.
* A task template can follow the order list ("Bestellijst afgevinkt"): the
  task is ticked off as soon as the whole order list is, and links to it on
  the task page.
* Dakmeting -> Bestellijst lists the order lines of all projects, per project
  or per supplier.
    """,
    "version": "20.0.1.6.0",
    "category": "Project",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_project_tasks", "purchase_stock", "project_purchase"],
    "data": [
        "security/ir.access.csv",
        "views/order_list_template_views.xml",
        "views/project_order_line_views.xml",
        "views/purchase_order_views.xml",
        "views/task_template_views.xml",
        "views/project_project_views.xml",
        "wizard/order_list_import_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tectora_project_order_list/static/src/order_list/order_list.scss",
            "tectora_project_order_list/static/src/order_list/order_list.xml",
            "tectora_project_order_list/static/src/order_list/order_list_controller.js",
            "tectora_project_order_list/static/src/order_list/order_list_widget.js",
            "tectora_project_order_list/static/src/order_list/order_board.js",
        ],
    },
    "auto_install": True,
    "installable": True,
}
