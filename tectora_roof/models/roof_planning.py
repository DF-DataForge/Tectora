# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class TectoraRoofPlanning(models.Model):
    _name = "tectora.roof.planning"
    _description = "Dakplanning (werkblok)"
    _order = "start_datetime, id"

    name = fields.Char(string="Werkblok", compute="_compute_name", store=True)
    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        required=True,
        ondelete="cascade",
        index=True,
    )
    team_id = fields.Many2one("tectora.roof.team", string="Ploeg", index=True)
    employee_ids = fields.Many2many(
        "hr.employee",
        "tectora_roof_planning_employee_rel",
        "planning_id",
        "employee_id",
        string="Toegewezen medewerkers",
    )
    employee_count = fields.Integer(compute="_compute_employee_count")
    start_datetime = fields.Datetime(string="Start", required=True, index=True)
    end_datetime = fields.Datetime(string="Einde", required=True)
    duration_hours = fields.Float(
        string="Duur (uren)", compute="_compute_duration_hours", store=True
    )
    state = fields.Selection(
        [
            ("draft", "Concept"),
            ("published", "Ingepland"),
            ("done", "Uitgevoerd"),
        ],
        string="Status",
        default="draft",
        required=True,
    )
    color = fields.Integer(related="team_id.color", store=True)
    notes = fields.Text(string="Werfinstructies")

    # --- basic project information shown on the planning item -------------
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    partner_id = fields.Many2one(related="project_id.partner_id", store=True)
    address = fields.Char(related="project_id.address")
    project_code = fields.Char(related="project_id.code", string="Referentie")
    project_type = fields.Selection(related="project_id.project_type")
    total_area = fields.Float(related="project_id.total_area")
    total_perimeter = fields.Float(related="project_id.total_perimeter")

    @api.depends("project_id.code", "project_id.name")
    def _compute_name(self):
        for item in self:
            project = item.project_id
            item.name = " — ".join(filter(None, [project.code, project.name]))

    def _compute_employee_count(self):
        for item in self:
            item.employee_count = len(item.employee_ids)

    @api.depends("start_datetime", "end_datetime")
    def _compute_duration_hours(self):
        for item in self:
            if item.start_datetime and item.end_datetime:
                delta = item.end_datetime - item.start_datetime
                item.duration_hours = delta.total_seconds() / 3600.0
            else:
                item.duration_hours = 0.0

    @api.onchange("team_id")
    def _onchange_team_id(self):
        for item in self:
            if item.team_id:
                item.employee_ids = item.team_id.member_ids

    # ------------------------------------------------------ employee items
    def _sync_employee_items(self):
        """Create/update the individual planning items of the assigned
        employees. Implemented by the Planning bridge module
        (tectora_roof_planning); a no-op when the Planning app is absent."""
        return True

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items._sync_employee_items()
        return items

    def write(self, vals):
        result = super().write(vals)
        if {"employee_ids", "start_datetime", "end_datetime", "state", "project_id"} & set(vals):
            self._sync_employee_items()
        return result

    # --------------------------------------------------------------- states
    def action_publish(self):
        self.write({"state": "published"})
        return True

    def action_set_done(self):
        self.write({"state": "done"})
        return True

    def action_reset_draft(self):
        self.write({"state": "draft"})
        return True

    # ---------------------------------------------------------------- split
    def _split_ranges(self):
        """Day-by-day ranges of this block, in the user's timezone (same
        semantics as splitting a planning shift into daily shifts)."""
        self.ensure_one()
        if not (self.start_datetime and self.end_datetime):
            return []
        tz = pytz.timezone(self.env.user.tz or "UTC")
        start_local = pytz.utc.localize(self.start_datetime).astimezone(tz)
        end_local = pytz.utc.localize(self.end_datetime).astimezone(tz)
        ranges = []
        cursor = start_local
        while cursor < end_local and len(ranges) < 366:
            next_midnight = tz.localize(
                datetime.combine(cursor.date() + timedelta(days=1), time.min)
            )
            segment_end = min(next_midnight, end_local)
            if segment_end <= cursor:
                break
            ranges.append(
                (
                    cursor.astimezone(pytz.utc).replace(tzinfo=None),
                    segment_end.astimezone(pytz.utc).replace(tzinfo=None),
                )
            )
            cursor = segment_end
        return ranges

    def action_split(self):
        """Split every selected block into one block per calendar day.

        Each resulting block keeps a copy of the employee assignment and can
        be re-assigned independently afterwards.
        """
        created = self.browse()
        for item in self:
            ranges = item._split_ranges()
            if len(ranges) < 2:
                continue
            first_start, first_end = ranges[0]
            item.write({"start_datetime": first_start, "end_datetime": first_end})
            for start, end in ranges[1:]:
                created |= item.copy(
                    {"start_datetime": start, "end_datetime": end}
                )
        (self | created)._sync_employee_items()
        return True
