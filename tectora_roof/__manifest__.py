# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting",
    "summary": "Teken en meet platte daken, wijs producten toe en maak offertes vanuit de meting",
    "description": """
Tectora Dakmeting
=================
Flat-roof measurement for roofing contractors, fully integrated in Odoo:

* Draw roof sections on an interactive canvas, on top of a satellite photo
  fetched from Google Maps or Mapbox.
* Sections are measured in real-world units (m, m²) using the geographic
  scale of the satellite image.
* Convert sections into roof objects (chimneys, skylights) with height and
  volume.
* Assign products to sections per coverage type (surface, edges, corners,
  drainage); quantities default to the measured area/perimeter.
* Generate a native sale.order (quotation) from the measurement in one click.
  Invoicing, Belgian VAT (21/12/6/0%), payments and reporting are handled by
  the standard Sales/Invoicing apps — install l10n_be for the Belgian chart
  of accounts and use a fiscal position for the 6% renovation rate.
    """,
    "version": "19.0.2.7.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["sale_management", "crm", "project", "sale_project", "hr"],
    "external_dependencies": {"python": ["requests", "PIL"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/roof_usage_data.xml",
        "views/roof_project_views.xml",
        "views/roof_object_views.xml",
        "views/roof_material_views.xml",
        "views/roof_team_views.xml",
        "views/roof_planning_views.xml",
        "views/sale_order_views.xml",
        "views/res_config_settings_views.xml",
        "views/product_category_views.xml",
        "views/crm_lead_views.xml",
        "views/sale_portal_templates.xml",
        "report/roof_project_report.xml",
        "report/roof_project_info_report.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tectora_roof/static/src/roof_canvas/roof_canvas.scss",
            "tectora_roof/static/src/roof_canvas/roof_canvas.xml",
            "tectora_roof/static/src/roof_canvas/roof_canvas.js",
            "tectora_roof/static/src/roof_canvas/product_picker_dialog.xml",
            "tectora_roof/static/src/roof_canvas/product_picker_dialog.js",
            "tectora_roof/static/src/roof_canvas/edge_length_dialog.xml",
            "tectora_roof/static/src/roof_canvas/edge_length_dialog.js",
            "tectora_roof/static/src/roof_checklist/roof_checklist.xml",
            "tectora_roof/static/src/roof_checklist/roof_checklist.js",
        ],
    },
    "application": True,
    "installable": True,
}
