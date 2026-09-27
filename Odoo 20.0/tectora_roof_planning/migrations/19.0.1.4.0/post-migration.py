# -*- coding: utf-8 -*-
"""Install the team planner and move the Ploegen menu on upgrade.

A post_init_hook only runs on install, so an upgrade needs to run it too:
it extends Odoo's Planning views, adds the "Per ploeg" menu, makes it the
planner the app opens on and moves Ploegen to Planning -> Configuratie.
"""
import logging

from odoo import SUPERUSER_ID, api

# Migration scripts are loaded standalone, so the hook needs an absolute
# import rather than a relative one.
from odoo.addons.tectora_roof_planning.hooks import post_init_hook

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)
    _logger.info("tectora_roof_planning: team planner installed on upgrade")
