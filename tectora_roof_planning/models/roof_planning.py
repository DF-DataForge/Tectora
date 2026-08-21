# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class TectoraRoofPlanning(models.Model):
    _inherit = "tectora.roof.planning"

    slot_ids = fields.One2many(
        "planning.slot",
        "roof_planning_id",
        string="Planning-items",
        copy=False,
    )
    slot_count = fields.Integer(compute="_compute_slot_count")

    @api.depends("slot_ids")
    def _compute_slot_count(self):
        for item in self:
            item.slot_count = len(item.slot_ids)

    def _planning_slot_values(self, employee):
        """Values for one employee's shift.

        Only keys the installed Planning version actually has are kept, so the
        bridge survives differences between Planning releases.
        """
        self.ensure_one()
        Slot = self.env["planning.slot"]
        values = {
            "roof_planning_id": self.id,
            "resource_id": employee.resource_id.id,
            "start_datetime": self.start_datetime,
            "end_datetime": self.end_datetime,
            "company_id": (self.company_id or self.env.company).id,
            "name": self.notes or self.name,
        }
        # Planning ↔ Project bridge (project_forecast): point the shift at the
        # roof project's project dossier.
        dossier = self.project_id.project_id
        if dossier:
            values["project_id"] = dossier.id
        values = {key: value for key, value in values.items() if key in Slot._fields}
        # The published/draft flag is named and valued differently across
        # versions: only set it when the exact value exists.
        state_field = Slot._fields.get("state")
        selection = getattr(state_field, "selection", None) if state_field else None
        if isinstance(selection, (list, tuple)):
            target = "draft" if self.state == "draft" else "published"
            if target in dict(selection):
                values["state"] = target
        return values

    def _sync_employee_items(self):
        """Create, update and remove the employees' planning shifts so they
        mirror the work block."""
        super()._sync_employee_items()
        for item in self:
            if not (item.start_datetime and item.end_datetime):
                continue
            try:
                item._sync_slots()
            except Exception:
                _logger.exception(
                    "Could not synchronise planning shifts for work block %s",
                    item.display_name,
                )
        return True

    def _sync_slots(self):
        self.ensure_one()
        Slot = self.env["planning.slot"]
        wanted_resources = self.employee_ids.resource_id
        slots = self.slot_ids
        stale = slots.filtered(lambda slot: slot.resource_id not in wanted_resources)
        if stale:
            stale.unlink()
        by_resource = {slot.resource_id: slot for slot in self.slot_ids}
        to_create = []
        for employee in self.employee_ids:
            values = self._planning_slot_values(employee)
            slot = by_resource.get(employee.resource_id)
            if slot:
                slot.write(values)
            else:
                to_create.append(values)
        if to_create:
            Slot.create(to_create)
        return True

    def action_open_in_planner(self):
        """Open the standard resource planner on this project's shifts."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "tectora_roof_planning.action_planning_slot_by_resource"
        )
        action["domain"] = [("roof_project_id", "=", self.project_id.id)]
        action["context"] = {"search_default_group_resource": 1}
        return action

    def action_view_slots(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planning-items"),
            "res_model": "planning.slot",
            "view_mode": "list,form",
            "domain": [("roof_planning_id", "=", self.id)],
            "context": {"default_roof_planning_id": self.id},
        }
