# -*- coding: utf-8 -*-
"""Apply the Planning view extensions and backfill the roof project on
existing shifts (a post_init_hook only runs on install)."""
import logging

from odoo import SUPERUSER_ID, api

# Migration scripts are loaded standalone, so the hook needs an absolute
# import rather than a relative one.
from odoo.addons.tectora_roof_planning.hooks import post_init_hook

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)
    _logger.info("tectora_roof_planning: planning views extended on upgrade")
