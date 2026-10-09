# -*- coding: utf-8 -*-
"""The Tectora table look (heads in the primary colour, the total in a light
tint, the information band between two lines, roomier lines) used to come
with the Tectora layouts whatever table design was picked, so the design
choice had no visible effect there. It is now a table design of its own,
"Tectora". Companies on a Tectora layout get it, so their documents look as
before; any other design can now be picked and is honoured."""
from odoo import SUPERUSER_ID, api

LAYOUTS = (
    "tectora_report_layout.external_layout_tectora",
    "tectora_report_layout.external_layout_tectora_letterhead",
    "tectora_report_layout.external_layout_tectora_letterhead_light",
    "tectora_report_layout.external_layout_tectora_roof_letterhead",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    views = env["ir.ui.view"]
    for xmlid in LAYOUTS:
        views |= env.ref(xmlid, raise_if_not_found=False) or env["ir.ui.view"]
    if not views:
        return
    env["res.company"].with_context(active_test=False).search([
        ("external_report_layout_id", "in", views.ids),
    ]).write({"report_tables_id": "tectora"})
