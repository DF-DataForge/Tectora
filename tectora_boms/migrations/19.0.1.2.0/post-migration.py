# -*- coding: utf-8 -*-
"""Load the demo bills of materials on upgrade.

The export loaded in 19.0.1.1.0 matches on names and yields mostly labour
lines, which is not enough to show the material list at work. The demo set
(data/demo_boms.json, built by tools/build_demo_boms.py) puts one complete
bill of materials on every works item that has a counterpart among the raw
materials, keyed on product codes. Idempotent on tectora_bom_key
(``demo:<code>``); the set can be removed again with
``env["mrp.bom"]._tectora_remove_demo_boms()`` or from the menu.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    report = env["mrp.bom"]._tectora_import_demo_boms()
    _logger.info("tectora_boms: demo bills of materials migration result: %s", report)
