# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    roof_planning_id = fields.Many2one(
        "tectora.roof.planning",
        string="Dakwerkblok",
        index=True,
        ondelete="cascade",
        copy=False,
        help="Werkblok van het dakproject waaruit deze planning-item komt.",
    )
    roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        index=True,
        help="Dakproject van deze planning-item. Wordt overgenomen van het "
        "werkblok of van het projectdossier waaraan de shift hangt, en is "
        "zelf te kiezen bij het inplannen van een ploeg.",
    )
    roof_team_id = fields.Many2one(
        "tectora.roof.team",
        string="Ploeg",
        index=True,
        help="Ploeg die dit werk uitvoert. Wie er precies ingepland wordt, "
        "volgt uit de samenstelling van de ploeg.",
    )
    roof_partner_id = fields.Many2one(
        related="roof_project_id.partner_id", string="Klant"
    )
    roof_address = fields.Char(related="roof_project_id.address", string="Werfadres")

    # ------------------------------------------------------- roof project link
    def _tectora_derive_roof_project(self):
        """Fill in the roof project of shifts that do not carry one yet.

        A shift belongs to a roof project either through a work block or --
        for shifts the Planning app itself created -- through the project
        dossier the roof project owns. Existing shifts are picked up that way
        instead of being duplicated. A project chosen by hand is never
        overwritten.
        """
        candidates = self.filtered(lambda slot: not slot.roof_project_id)
        if not candidates:
            return True
        by_block = candidates.filtered("roof_planning_id")
        rest = candidates - by_block
        dossiers = {}
        if rest and "project_id" in self._fields:
            dossier_ids = rest.mapped("project_id").ids
            if dossier_ids:
                dossiers = {
                    project.project_id.id: project.id
                    for project in self.env["tectora.roof.project"].search(
                        [("project_id", "in", dossier_ids)]
                    )
                }
        # One write per roof project instead of one per shift: this also runs
        # over every existing shift on upgrade.
        groups = {}
        for slot in by_block:
            project_id = slot.roof_planning_id.project_id.id
            if project_id:
                groups.setdefault(project_id, self.browse())
                groups[project_id] |= slot
        for slot in rest:
            project_id = dossiers.get(slot.project_id.id)
            if project_id:
                groups.setdefault(project_id, self.browse())
                groups[project_id] |= slot
        for project_id, slots in groups.items():
            slots.write({"roof_project_id": project_id})
        return True

    @api.onchange("roof_project_id")
    def _onchange_roof_project_id(self):
        """Picking the project proposes the team it is assigned to."""
        for slot in self:
            if slot.roof_project_id and not slot.roof_team_id:
                slot.roof_team_id = slot.roof_project_id.team_id

    # ---------------------------------------------------------- team planning
    @api.model_create_multi
    def create(self, vals_list):
        slots = super().create(vals_list)
        slots._tectora_derive_roof_project()
        slots._tectora_plan_team()
        return slots

    def write(self, vals):
        result = super().write(vals)
        touched = set(vals)
        if {"roof_planning_id", "project_id"} & touched:
            self._tectora_derive_roof_project()
        if {"roof_team_id", "roof_project_id"} & touched:
            self._tectora_plan_team()
        return result

    def _tectora_plan_team(self):
        """Plan a whole team from a single shift.

        In the team planner the user creates one shift and picks a dakproject
        and a ploeg on it. That shift becomes the project's work block, and the
        work block is what fans the team out over its members -- so the team
        configuration, not the planner, decides who ends up planned. Shifts the
        work block itself created are skipped.
        """
        if self.env.context.get("tectora_planning_sync"):
            return True
        Block = self.env["tectora.roof.planning"]
        for slot in self:
            try:
                slot._tectora_plan_team_one(Block)
            except Exception:
                _logger.exception(
                    "Could not plan the team of planning shift %s", slot.id
                )
        return True

    def _tectora_plan_team_one(self, Block):
        self.ensure_one()
        team = self.roof_team_id
        block = self.roof_planning_id
        if block:
            # An existing team shift moved to another team: the work block owns
            # the assignment, so retarget it and let it re-sync its shifts.
            if team and block.team_id != team:
                members = team.member_ids.filtered("resource_id")
                # Take a member of the new team first: re-syncing the block
                # drops the shifts of everyone who is no longer on it, and this
                # record is the one the user is looking at.
                if members and self.resource_id not in members.resource_id:
                    self.with_context(tectora_planning_sync=True).write(
                        {"resource_id": members[0].resource_id.id}
                    )
                block.write({
                    "team_id": team.id,
                    "employee_ids": [(6, 0, members.ids)],
                })
            return True
        if not team or not self.roof_project_id:
            return True
        if not (self.start_datetime and self.end_datetime):
            return True
        members = team.member_ids.filtered("resource_id")
        if not members:
            _logger.info(
                "Team %s has no members with a resource; shift %s left as is",
                team.display_name, self.id,
            )
            return True
        block = Block.with_context(tectora_planning_sync=True).create({
            "project_id": self.roof_project_id.id,
            "team_id": team.id,
            "employee_ids": [(6, 0, members.ids)],
            "start_datetime": self.start_datetime,
            "end_datetime": self.end_datetime,
            "state": "published",
        })
        # Hand this shift to one of the team members, so the planner does not
        # end up with a stray unassigned shift next to the team's own.
        resource = self.resource_id
        if resource not in members.resource_id:
            resource = members[0].resource_id
        self.with_context(tectora_planning_sync=True).write({
            "roof_planning_id": block.id,
            "resource_id": resource.id,
        })
        block._sync_slots()
        return True
