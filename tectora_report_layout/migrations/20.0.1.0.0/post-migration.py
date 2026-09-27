# -*- coding: utf-8 -*-
"""Odoo 20 made the table design a choice of its own (Settings -> Configure
Document Layout -> Table Design); the Tectora layout used to force striped
tables. Companies on the Tectora layout that are still on the default design
get Striped, as a fresh install does (hooks.py)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    view = env.ref("tectora_report_layout.external_layout_tectora", raise_if_not_found=False)
    if not view:
        return
    env["res.company"].with_context(active_test=False).search([
        ("external_report_layout_id", "=", view.id),
        ("report_tables_id", "=", "light"),
    ]).write({"report_tables_id": "striped"})
