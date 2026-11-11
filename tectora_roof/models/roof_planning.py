# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TectoraRoofPlanning(models.Model):
    _name = "tectora.roof.planning"
    _description = "Dakplanning (werkblok)"
    _order = "start_datetime, id"

    name = fields.Char(string="Werkblok", compute="_compute_name", store=True)
    project_name = fields.Char(related="project_id.name", string="Project")
    project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        required=True,
        ondelete="cascade",
        index=True,
    )
    team_id = fields.Many2one(
        "tectora.roof.team", string="Ploeg", index=True,
        group_expand="_read_group_team_id",
    )
    department_id = fields.Many2one(
        "hr.department",
        string="Afdeling",
        compute="_compute_department_id",
        store=True,
        index=True,
        help="De afdeling van de ploeg; heeft de ploeg er geen, die van de "
        "ploegbaas of anders van de toegewezen medewerkers.",
    )
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
    color = fields.Integer(
        related="project_id.color", store=True, string="Kleur",
        help="Kleur van het project: alle blokken van een project delen ze.",
    )
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

    @api.depends(
        "project_id.name", "project_id.address", "project_id.partner_id.name",
        "project_id.partner_id.city", "project_id.total_area",
        "project_id.project_type", "employee_ids",
    )
    def _compute_display_name(self):
        """The block as the planner shows it, shortest first: the customer,
        the municipality of the site, the roof area, the project type and
        how many people are on it ("Dhr. Peeters · Heule · 120 m² ·
        Renovatie · 2 pers."), so the part a planner looks for is still on a
        short bar. The full address is in the block's summary; the block's
        colour is that of its project."""
        types = dict(self.env["tectora.roof.project"]._fields["project_type"].selection)
        for item in self:
            project = item.project_id
            title = project.partner_id.name or project.name or item.name or _("Werkblok")
            details = []
            city = project._site_city() if project else ""
            if city and city.lower() not in title.lower():
                details.append(city)
            if project.total_area:
                details.append(_("%s m²") % ("%.0f" % project.total_area))
            if project.project_type:
                details.append(types.get(project.project_type, project.project_type))
            if item.employee_ids:
                details.append(_("%s pers.") % len(item.employee_ids))
            item.display_name = " · ".join([title] + details)

    @api.depends(
        "team_id.department_id", "team_id.leader_id.department_id",
        "employee_ids.department_id",
    )
    def _compute_department_id(self):
        for item in self:
            item.department_id = (
                item.team_id.department_id
                or item.team_id.leader_id.department_id
                or item.employee_ids.department_id[:1]
            )

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

    @api.model
    def _read_group_team_id(self, teams, domain):
        """The planner's rows: the teams with blocks, and the teams set to
        'Altijd weergeven op planner' -- unless the search leaves them out
        (a filter on the team, or on the department)."""
        if any(isinstance(leaf, (list, tuple)) and leaf and leaf[0] in ("team_id", "team_id.name")
               for leaf in domain or []):
            return teams
        extra_domain = [("show_in_planner", "=", True)]
        for leaf in domain or []:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3 and leaf[0] == "department_id":
                extra_domain.append(("department_id", leaf[1], leaf[2]))
        return (teams | teams.search(extra_domain)).sorted(lambda t: (t.sequence, t.name or ""))

    # A working day on the planner: 8:00 - 17:00.
    WORK_START = time(8, 0)
    WORK_END = time(17, 0)

    @api.model
    def _tectora_working_hours(self, start, end, exclusive_end=False):
        """``start`` / ``end`` (UTC) as picked on a calendar: a day picked
        (midnight) starts at 8:00 and ends at 17:00 -- the end day included,
        or with ``exclusive_end`` (the planner's cells end at the next
        midnight) the day before; an end before the start is the start's
        day. Hours set on purpose are kept."""
        if not start:
            return start, end
        tz = pytz.timezone(self.env.user.tz or "Europe/Brussels")
        local_start = pytz.utc.localize(start).astimezone(tz)
        if local_start.time() == time.min:
            local_start = tz.localize(datetime.combine(local_start.date(), self.WORK_START))
        local_end = pytz.utc.localize(end).astimezone(tz) if end else None
        if local_end is None or local_end <= local_start:
            local_end = tz.localize(datetime.combine(local_start.date(), self.WORK_END))
        elif local_end.time() == time.min:
            day = local_end.date() - timedelta(days=1) if exclusive_end else local_end.date()
            day = max(day, local_start.date())
            local_end = tz.localize(datetime.combine(day, self.WORK_END))
        elif local_end.time() >= time(23, 59):
            local_end = tz.localize(datetime.combine(local_end.date(), self.WORK_END))

        def utc(value):
            return value.astimezone(pytz.utc).replace(tzinfo=None)

        return utc(local_start), utc(local_end)

    @api.onchange("start_datetime", "end_datetime")
    def _onchange_tectora_working_hours(self):
        for item in self:
            start, end = self._tectora_working_hours(item.start_datetime, item.end_datetime)
            if start != item.start_datetime:
                item.start_datetime = start
            if end != item.end_datetime:
                item.end_datetime = end

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        start = values.get("start_datetime")
        if start:
            start, end = self._tectora_working_hours(
                fields.Datetime.to_datetime(start),
                fields.Datetime.to_datetime(values.get("end_datetime")) if values.get("end_datetime") else None,
                exclusive_end=True,
            )
            values["start_datetime"] = start
            if "end_datetime" in fields_list or values.get("end_datetime"):
                values["end_datetime"] = end
        return values

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
        if "team_id" in vals and "employee_ids" not in vals:
            # A block dragged onto another team row in the planner takes that
            # team's members along.
            team = self.env["tectora.roof.team"].browse(vals["team_id"])
            if team:
                vals = dict(vals, employee_ids=[(6, 0, team.member_ids.ids)])
        result = super().write(vals)
        if {"employee_ids", "start_datetime", "end_datetime", "state", "project_id"} & set(vals):
            self._sync_employee_items()
        return result

    # ------------------------------------------------------------- shortcuts
    def action_open_project_dashboard(self):
        """The project dashboard behind this block (created if the order was
        not confirmed yet)."""
        self.ensure_one()
        return self.project_id.action_open_project()

    def action_open_roof_project(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "res_id": self.project_id.id,
            "view_mode": "form",
            "target": "current",
        }

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
    def action_tectora_split_at(self, day):
        """Cut this block in two at the start (local midnight) of ``day``
        ("2026-11-05"), the scissors of the team planner: the first part
        keeps the block, the second is a copy with the same team and
        employees, each with its own shifts."""
        self.ensure_one()
        tz = pytz.timezone(self.env.user.tz or "UTC")
        cut_day = fields.Date.to_date(day)
        cut = tz.localize(datetime.combine(cut_day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        if not (self.start_datetime and self.end_datetime
                and self.start_datetime < cut < self.end_datetime):
            raise UserError(_("Een blok kan enkel binnen zijn eigen periode geknipt worden."))
        end = self.end_datetime
        self.write({"end_datetime": cut})
        second = self.copy({"start_datetime": cut, "end_datetime": end})
        (self | second)._sync_employee_items()
        return True
