# -*- coding: utf-8 -*-
"""Load the shipped bills of materials on install.

Only the confident matches are created; ``docs/stuklijst_koppeling.md`` has
the analysis and the queue of decisions the rest needs. Upgrades run the same
thing through migrations/, since Odoo only calls a post_init_hook on install.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    env["mrp.bom"]._tectora_import_shipped_boms()
