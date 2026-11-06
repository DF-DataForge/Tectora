# -*- coding: utf-8 -*-
"""The planner per resource groups its employees team by team: the search
views get the "Ploeg van de medewerker" group-by and the planners per
resource group by it first (a post_init_hook only runs on install)."""
import logging

from odoo import SUPERUSER_ID, api

# Migration scripts are loaded standalone, so the hooks need an absolute
# import rather than a relative one.
from odoo.addons.tectora_roof_planning.hooks import (
    _extend_planning_views,
    _group_resource_planner_by_team,
)

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _extend_planning_views(env)
    _group_resource_planner_by_team(env)
    _logger.info("tectora_roof_planning: planners per resource grouped by team")
