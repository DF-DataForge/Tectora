# -*- coding: utf-8 -*-
"""Fill "Geschatte tijd per eenheid" of the works items from the labour lines
of the Stuklijst export (data/labour_norms.json). Only products without a
value get one; see tools/build_labour_norms.py for the mapping."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    report = env["product.template"]._tectora_import_labour_norms()
    _logger.info("tectora_boms: labour norms migration result: %s", report)
