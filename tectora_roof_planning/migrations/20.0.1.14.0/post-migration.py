# -*- coding: utf-8 -*-
"""Colour the Planning app's shifts per roof project on upgrade.

The extensions of Odoo's own Planning views are made by the post_init_hook,
which only runs on install: re-apply them so the gantt views get the
project colour (roof_color).
"""
import logging

from odoo import SUPERUSER_ID, api

# Migration scripts are loaded standalone, so the hook needs an absolute
# import rather than a relative one.
from odoo.addons.tectora_roof_planning.hooks import _extend_planning_views

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _extend_planning_views(env)
    _logger.info("tectora_roof_planning: planning gantt views coloured per roof project")
