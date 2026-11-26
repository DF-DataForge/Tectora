# -*- coding: utf-8 -*-
"""The planner lives in the Project app: Ploegen moves from the Planning
app's configuration to Project -> Configuratie (a post_init_hook only runs
on install)."""
from odoo import SUPERUSER_ID, api

# Migration scripts are loaded standalone, so the hook needs an absolute
# import rather than a relative one.
from odoo.addons.tectora_roof_planning.hooks import _move_teams_menu


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _move_teams_menu(env)
