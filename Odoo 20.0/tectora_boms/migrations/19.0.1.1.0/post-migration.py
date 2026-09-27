# -*- coding: utf-8 -*-
"""Load the shipped bills of materials on upgrade.

The module used to ship no data at all: the wizard was the only way in, and it
defaults to analysing rather than importing, so upgrading loaded nothing. The
export now ships as data/bom_catalog.json and is loaded here as well, because
a post_init_hook only runs when a module is *installed*.

Idempotent: the import matches on tectora_bom_key (product + lines), so
running it again updates instead of duplicating.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    report = env["mrp.bom"]._tectora_import_shipped_boms()
    _logger.info("tectora_boms: bill of materials migration result: %s", report)
