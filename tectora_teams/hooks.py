# -*- coding: utf-8 -*-
"""The existing ploegen come along on install: their employees become their
contacts (through the employees' work contacts), their ploegbaas likewise."""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    teams = env["tectora.roof.team"].with_context(active_test=False).search([])
    moved = 0
    for team in teams:
        if team.partner_ids or team.leader_partner_id:
            continue
        employees = team.sudo().employee_ids
        partners = employees.work_contact_id
        leader = team.sudo().leader_id.work_contact_id
        values = {}
        if partners or leader:
            values["partner_ids"] = [(6, 0, (partners | leader).ids)]
        if leader:
            values["leader_partner_id"] = leader.id
        if values:
            team.with_context(tectora_team_sync=True).write(values)
            moved += 1
    _logger.info("tectora_teams: %s ploegen took their employees along as contacts", moved)
