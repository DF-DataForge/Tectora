# -*- coding: utf-8 -*-
"""The plannable project behind an order and its roof project.

A confirmed order gets a ``project.project``. It carries the analytic account
on which the post-calculation is built -- revenue, material and purchase
costs, invoices, timesheets -- and its dashboard shows, per project: revenue
and costs, the status of the deliveries, the open tasks and the planning of
the team, with the roof measurement itself as part of the dashboard.
"""
import logging
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ProjectProject(models.Model):
    _inherit = "project.project"

    roof_project_ids = fields.One2many(
        "tectora.roof.project", "project_id", string="Dakprojecten",
        export_string_translation=False,
    )
    roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        compute="_compute_roof_project_id",
        inverse="_inverse_roof_project_id",
        store=True,
        readonly=False,
        copy=False,
        index=True,
        help="Dakproject (meting) van dit project; één dakproject per project.",
    )
    tectora_sale_order_id = fields.Many2one(
        "sale.order",
        string="Offerte / Order",
        compute="_compute_tectora_sale_order_id",
        help="De order waaruit dit project ontstond: die van het dakproject, "
        "of de order waaraan het project in Verkoop hangt.",
    )
    tectora_sale_order_state = fields.Selection(
        related="tectora_sale_order_id.state", string="Orderstatus"
    )

    # --- the roof measurement, mirrored on the dashboard ---------------------
    roof_state = fields.Selection(related="roof_project_id.state", string="Status dakproject")
    roof_address = fields.Char(related="roof_project_id.address", string="Werfadres")
    roof_project_type = fields.Selection(
        related="roof_project_id.project_type", string="Projecttype"
    )
    roof_total_area = fields.Float(
        related="roof_project_id.total_area", string="Dakoppervlakte (m²)"
    )
    roof_total_perimeter = fields.Float(
        related="roof_project_id.total_perimeter", string="Omtrek (m)"
    )
    roof_section_count = fields.Integer(
        related="roof_project_id.section_count", string="Daksecties"
    )
    roof_object_count = fields.Integer(
        related="roof_project_id.roof_object_count", string="Dakobjecten"
    )
    roof_canvas_snapshot = fields.Binary(
        related="roof_project_id.canvas_snapshot", string="Tekening"
    )
    roof_section_ids = fields.One2many(
        related="roof_project_id.section_ids", string="Daksecties (meting)"
    )
    roof_material_line_ids = fields.One2many(
        related="roof_project_id.material_line_ids", string="Materiaallijst"
    )
    roof_team_id = fields.Many2one(related="roof_project_id.team_id", string="Ploeg")
    roof_planned_date_begin = fields.Datetime(
        related="roof_project_id.planned_date_begin", string="Geplande start"
    )
    roof_planned_date_end = fields.Datetime(
        related="roof_project_id.planned_date_end", string="Gepland einde"
    )
    roof_planning_ids = fields.One2many(
        related="roof_project_id.planning_ids", string="Werkblokken"
    )

    # --- post-calculation ----------------------------------------------------
    tectora_revenue = fields.Monetary(
        string="Omzet (order)", compute="_compute_tectora_profitability",
        currency_field="currency_id",
        help="Bedrag excl. btw van de bevestigde order.",
    )
    tectora_invoiced = fields.Monetary(
        string="Gefactureerd", compute="_compute_tectora_profitability",
        currency_field="currency_id",
    )
    tectora_to_invoice = fields.Monetary(
        string="Te factureren", compute="_compute_tectora_profitability",
        currency_field="currency_id",
    )
    tectora_costs = fields.Monetary(
        string="Kosten", compute="_compute_tectora_profitability",
        currency_field="currency_id",
        help="Alle kosten op de analytische rekening van het project: "
        "aankopen, leveranciersfacturen, urenstaten, voorraadbewegingen.",
    )
    tectora_cost_billed = fields.Monetary(
        string="Kosten (geboekt)", compute="_compute_tectora_profitability",
        currency_field="currency_id",
    )
    tectora_cost_to_bill = fields.Monetary(
        string="Kosten (verwacht)", compute="_compute_tectora_profitability",
        currency_field="currency_id",
    )
    tectora_margin = fields.Monetary(
        string="Marge", compute="_compute_tectora_profitability",
        currency_field="currency_id",
        help="Omzet (gefactureerd + te factureren) min de kosten.",
    )
    tectora_margin_percent = fields.Float(
        string="Marge (%)", compute="_compute_tectora_profitability", digits=(16, 1)
    )
    tectora_material_cost = fields.Monetary(
        related="roof_project_id.material_cost", string="Materiaalkost (stuklijst)",
        currency_field="currency_id",
    )
    tectora_material_count = fields.Integer(
        related="roof_project_id.material_count", string="Materiaallijnen"
    )
    tectora_timesheet_hours = fields.Float(
        string="Uren", compute="_compute_tectora_timesheets",
        help="Uren op de urenstaten van dit project.",
    )
    tectora_timesheet_cost = fields.Monetary(
        string="Loonkost", compute="_compute_tectora_timesheets",
        currency_field="currency_id",
    )
    tectora_has_timesheets = fields.Boolean(compute="_compute_tectora_timesheets")

    # --- invoices, deliveries, purchases -------------------------------------
    tectora_invoice_count = fields.Integer(
        string="Facturen", compute="_compute_tectora_invoices"
    )
    tectora_invoice_due = fields.Monetary(
        string="Openstaand", compute="_compute_tectora_invoices",
        currency_field="currency_id",
    )
    tectora_picking_count = fields.Integer(
        string="Leveringen", compute="_compute_tectora_pickings"
    )
    tectora_picking_done_count = fields.Integer(
        string="Leveringen gedaan", compute="_compute_tectora_pickings"
    )
    tectora_delivery_status = fields.Selection(
        [
            ("none", "Geen leveringen"),
            ("waiting", "Te leveren"),
            ("partial", "Deels geleverd"),
            ("done", "Geleverd"),
        ],
        string="Leverstatus",
        compute="_compute_tectora_pickings",
    )
    tectora_purchase_count = fields.Integer(
        string="Inkooporders", compute="_compute_tectora_purchases"
    )
    tectora_purchase_amount = fields.Monetary(
        string="Inkoop (excl. btw)", compute="_compute_tectora_purchases",
        currency_field="currency_id",
    )

    # --- planning ------------------------------------------------------------
    tectora_planning_count = fields.Integer(
        string="Werkblokken", compute="_compute_tectora_planning"
    )
    tectora_planning_hours = fields.Float(
        string="Geplande uren", compute="_compute_tectora_planning",
        help="Uren van de werkblokken, maal het aantal ingeplande medewerkers.",
    )
    tectora_next_planning_date = fields.Datetime(
        string="Volgende werkdag", compute="_compute_tectora_planning"
    )
    tectora_planned_employee_ids = fields.Many2many(
        "hr.employee", string="Ingeplande medewerkers",
        compute="_compute_tectora_planning",
    )

    # ------------------------------------------------------------------ links
    @api.depends("roof_project_ids")
    def _compute_roof_project_id(self):
        for project in self:
            roofs = project.roof_project_ids
            if project.roof_project_id and project.roof_project_id in roofs:
                continue
            project.roof_project_id = roofs[:1]

    def _inverse_roof_project_id(self):
        for project in self:
            roof = project.roof_project_id
            others = project.roof_project_ids - roof
            if others:
                others.with_context(tectora_sync=True).write({"project_id": False})
            if roof and roof.project_id != project:
                roof.with_context(tectora_sync=True).write({"project_id": project.id})
                roof._tectora_link_order_to_project(project)

    @api.depends(
        "roof_project_id.sale_order_id", "sale_line_id", "reinvoiced_sale_order_id"
    )
    def _compute_tectora_sale_order_id(self):
        SaleOrder = self.env["sale.order"]
        for project in self:
            order = project.roof_project_id.sale_order_id
            if not order:
                order = project.sudo().reinvoiced_sale_order_id or project.sale_order_id
            if not order and project.id:
                order = SaleOrder.search([("project_id", "=", project.id)], limit=1)
            project.tectora_sale_order_id = order

    # ------------------------------------------------------------ profitability
    def _tectora_profitability_totals(self):
        """Odoo's own profitability figures of the project (sale_project and
        every module that plugs into it: purchase, timesheets, stock...).
        Costs come back negative. Empty dict when it cannot be computed."""
        self.ensure_one()
        if not self.id or not self.account_id:
            return {}
        try:
            items = self.with_context(active_test=False)._get_profitability_items(
                with_action=False
            )
        except Exception:  # never let the dashboard break on a bridge module
            _logger.exception("Could not compute the profitability of %s", self.name)
            return {}
        revenues = items.get("revenues", {}).get("total", {})
        costs = items.get("costs", {}).get("total", {})
        return {
            "invoiced": revenues.get("invoiced", 0.0),
            "to_invoice": revenues.get("to_invoice", 0.0),
            "billed": costs.get("billed", 0.0),
            "to_bill": costs.get("to_bill", 0.0),
        }

    @api.depends(
        "account_id", "tectora_sale_order_id.amount_untaxed",
        "tectora_sale_order_id.state", "roof_project_id.material_cost",
    )
    def _compute_tectora_profitability(self):
        for project in self:
            order = project.tectora_sale_order_id
            project.tectora_revenue = (
                order.amount_untaxed if order and order.state in ("sale", "done") else 0.0
            )
            totals = project._tectora_profitability_totals()
            project.tectora_invoiced = totals.get("invoiced", 0.0)
            project.tectora_to_invoice = totals.get("to_invoice", 0.0)
            project.tectora_cost_billed = -totals.get("billed", 0.0)
            project.tectora_cost_to_bill = -totals.get("to_bill", 0.0)
            project.tectora_costs = (
                project.tectora_cost_billed + project.tectora_cost_to_bill
            )
            revenue_total = project.tectora_invoiced + project.tectora_to_invoice
            if not revenue_total and not totals:
                revenue_total = project.tectora_revenue
            project.tectora_margin = revenue_total - project.tectora_costs
            project.tectora_margin_percent = (
                project.tectora_margin / revenue_total * 100.0 if revenue_total else 0.0
            )

    def _compute_tectora_timesheets(self):
        has_timesheets = "timesheet_ids" in self._fields
        for project in self:
            project.tectora_has_timesheets = has_timesheets
            if not has_timesheets or not project.id:
                project.tectora_timesheet_hours = 0.0
                project.tectora_timesheet_cost = 0.0
                continue
            lines = project.sudo().timesheet_ids
            project.tectora_timesheet_hours = sum(lines.mapped("unit_amount"))
            project.tectora_timesheet_cost = -sum(lines.mapped("amount"))

    # --------------------------------------------- invoices, deliveries, POs
    def _tectora_invoices(self):
        self.ensure_one()
        order = self.tectora_sale_order_id
        invoices = order.sudo().invoice_ids if order else self.env["account.move"]
        return invoices.filtered(lambda move: move.state != "cancel")

    @api.depends("tectora_sale_order_id.invoice_ids.state", "tectora_sale_order_id.invoice_ids.amount_residual")
    def _compute_tectora_invoices(self):
        for project in self:
            invoices = project._tectora_invoices()
            project.tectora_invoice_count = len(invoices)
            project.tectora_invoice_due = sum(
                invoices.filtered(
                    lambda move: move.state == "posted"
                    and move.move_type in ("out_invoice", "out_refund")
                ).mapped("amount_residual_signed")
            )

    def _tectora_pickings(self):
        """Deliveries of the order (sale_stock); empty without Inventory."""
        self.ensure_one()
        order = self.tectora_sale_order_id
        if not order or "picking_ids" not in order._fields:
            return None
        return order.sudo().picking_ids.filtered(lambda p: p.state != "cancel")

    def _compute_tectora_pickings(self):
        for project in self:
            pickings = project._tectora_pickings()
            if not pickings:
                project.tectora_picking_count = 0
                project.tectora_picking_done_count = 0
                project.tectora_delivery_status = "none"
                continue
            done = pickings.filtered(lambda p: p.state == "done")
            project.tectora_picking_count = len(pickings)
            project.tectora_picking_done_count = len(done)
            if len(done) == len(pickings):
                project.tectora_delivery_status = "done"
            elif done:
                project.tectora_delivery_status = "partial"
            else:
                project.tectora_delivery_status = "waiting"

    def _tectora_purchase_orders(self):
        """Purchase orders whose lines carry the project's analytic account;
        None when Purchase is not installed."""
        self.ensure_one()
        PurchaseLine = self.env.get("purchase.order.line")
        if PurchaseLine is None:
            return None
        if not self.account_id:
            return self.env["purchase.order"]
        lines = PurchaseLine.sudo().search(
            [("analytic_distribution", "in", [self.account_id.id])]
        )
        return lines.order_id.filtered(lambda order: order.state != "cancel")

    def _compute_tectora_purchases(self):
        for project in self:
            orders = project._tectora_purchase_orders()
            project.tectora_purchase_count = len(orders) if orders else 0
            project.tectora_purchase_amount = (
                sum(orders.mapped("amount_untaxed")) if orders else 0.0
            )

    # ---------------------------------------------------------------- planning
    @api.depends(
        "roof_project_id.planning_ids.start_datetime",
        "roof_project_id.planning_ids.end_datetime",
        "roof_project_id.planning_ids.employee_ids",
        "roof_project_id.planning_ids.state",
    )
    def _compute_tectora_planning(self):
        now = fields.Datetime.now()
        for project in self:
            blocks = project.roof_project_id.planning_ids
            project.tectora_planning_count = len(blocks)
            project.tectora_planning_hours = sum(
                block.duration_hours * max(len(block.employee_ids), 1)
                for block in blocks
            )
            upcoming = blocks.filtered(
                lambda block: block.end_datetime and block.end_datetime >= now
            ).sorted("start_datetime")
            project.tectora_next_planning_date = (
                upcoming[:1].start_datetime if upcoming else False
            )
            project.tectora_planned_employee_ids = blocks.employee_ids

    # ------------------------------------------------------------------- sync
    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get("tectora_sync"):
            return result
        touched = set(vals) & {"partner_id", "user_id", "date_start", "date"}
        if touched:
            for project in self.filtered("roof_project_id"):
                values = project._tectora_roof_values(touched)
                if values:
                    project.roof_project_id.with_context(tectora_sync=True).write(values)
        return result

    def _tectora_roof_values(self, changed):
        """Roof project values that follow this project: customer, project
        manager and the planned window (project dates are days, the roof
        project plans in hours: 07:00-17:00 in the user's time zone)."""
        self.ensure_one()
        roof = self.roof_project_id
        values = {}
        if "partner_id" in changed and self.partner_id:
            values["partner_id"] = self.partner_id.id
        if "user_id" in changed and self.user_id:
            values["project_manager_id"] = self.user_id.id
        tz = pytz.timezone(self.env.user.tz or "UTC")

        def local_date(value):
            return fields.Datetime.context_timestamp(self, value).date() if value else None

        def at_hour(day, hour):
            local = tz.localize(datetime.combine(day, time(hour=hour)))
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        if "date_start" in changed and self.date_start:
            if local_date(roof.planned_date_begin) != self.date_start:
                values["planned_date_begin"] = at_hour(self.date_start, 7)
        if "date" in changed and self.date:
            if local_date(roof.planned_date_end) != self.date:
                values["planned_date_end"] = at_hour(self.date, 17)
        return values

    # ---------------------------------------------------------------- actions
    def action_open_dashboard(self):
        """The project dashboard: revenue and costs, deliveries, tasks and
        planning, each card opening the records behind it."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": "project.project",
            "res_id": self.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "tectora_roof.view_project_project_tectora_dashboard"
                    ).id,
                    "form",
                )
            ],
            "target": "current",
            "context": dict(self.env.context, tectora_dashboard=True),
        }

    def action_open_project_form(self):
        """The standard project form (settings), from the dashboard."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.project",
            "res_id": self.id,
            "view_mode": "form",
            "views": [(self.env.ref("project.edit_project").id, "form")],
            "target": "current",
        }

    def _tectora_ensure_roof_project(self):
        """A project made outside the roofing flow gets its roof project on
        first request, tied to the project's order when there is one."""
        self.ensure_one()
        if self.roof_project_id:
            return self.roof_project_id
        order = self.tectora_sale_order_id
        if order:
            roof = order.roof_project_id or order._tectora_create_roof_project()
        else:
            roof = self.env["tectora.roof.project"].with_context(
                tectora_sync=True
            ).create(
                {
                    "name": self.name,
                    "partner_id": self.partner_id.id or False,
                    "company_id": self.company_id.id or self.env.company.id,
                    "project_manager_id": self.user_id.id or False,
                }
            )
        if roof:
            roof.with_context(tectora_sync=True).write({"project_id": self.id})
            self.invalidate_recordset(["roof_project_id", "roof_project_ids"])
        return roof

    def action_view_roof_project(self):
        self.ensure_one()
        roof = self._tectora_ensure_roof_project()
        if not roof:
            raise UserError(_("Het dakproject kon niet aangemaakt worden."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "res_id": roof.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_sale_order(self):
        """The order of the project, or a new quotation for it."""
        self.ensure_one()
        order = self.tectora_sale_order_id
        if order:
            return {
                "type": "ir.actions.act_window",
                "res_model": "sale.order",
                "res_id": order.id,
                "view_mode": "form",
                "target": "current",
            }
        roof = self._tectora_ensure_roof_project()
        context = {
            "default_partner_id": self.partner_id.id,
            "default_project_id": self.id if self.allow_billable else False,
            "default_company_id": self.company_id.id,
        }
        if roof:
            context.update(
                {
                    "default_%s" % key: value
                    for key, value in roof._prepare_sale_order_values().items()
                    if key != "partner_id" or value
                }
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Offerte"),
            "res_model": "sale.order",
            "view_mode": "form",
            "target": "current",
            "context": context,
        }

    def action_view_tectora_tasks(self):
        self.ensure_one()
        return self.action_view_tasks()

    def action_view_tectora_profitability(self):
        """Odoo's own profitability panel of the project, for the detail
        behind the revenue and cost figures."""
        self.ensure_one()
        action = self.with_context(active_id=self.id).project_update_all_action()
        action["context"] = dict(
            self.env.context, active_id=self.id, default_project_id=self.id
        )
        return action

    def action_view_tectora_invoices(self):
        self.ensure_one()
        invoices = self._tectora_invoices()
        action = {
            "type": "ir.actions.act_window",
            "name": _("Facturen"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", invoices.ids)],
            "context": {"default_move_type": "out_invoice"},
        }
        if len(invoices) == 1:
            action.update({"view_mode": "form", "res_id": invoices.id})
        return action

    def action_view_tectora_pickings(self):
        self.ensure_one()
        pickings = self._tectora_pickings()
        if pickings is None:
            raise UserError(_("De module Voorraad is niet geïnstalleerd."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Leveringen"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", pickings.ids)],
        }

    def action_view_tectora_purchases(self):
        self.ensure_one()
        orders = self._tectora_purchase_orders()
        if orders is None:
            raise UserError(_("De module Inkoop is niet geïnstalleerd."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Inkooporders"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", orders.ids)],
            "context": {
                "default_partner_id": False,
                "default_project_id": self.id,
            },
        }

    def action_view_tectora_materials(self):
        self.ensure_one()
        roof = self._tectora_ensure_roof_project()
        return {
            "type": "ir.actions.act_window",
            "name": _("Materiaallijst"),
            "res_model": "tectora.roof.material",
            "view_mode": "list,form",
            "domain": [("project_id", "=", roof.id)],
            "context": {"default_project_id": roof.id},
        }

    def action_view_tectora_planning(self):
        """The work blocks of the project's roof project (the Planning bridge
        opens the employees' shifts in the planner instead)."""
        self.ensure_one()
        roof = self._tectora_ensure_roof_project()
        return roof.action_view_planning()

    def action_view_tectora_timesheets(self):
        self.ensure_one()
        if "timesheet_ids" not in self._fields:
            raise UserError(_("De module Urenstaten is niet geïnstalleerd."))
        action = self.with_context(active_id=self.id).action_project_timesheets()
        action["domain"] = [("project_id", "=", self.id)]
        action["context"] = dict(
            self.env.context,
            active_id=self.id,
            default_project_id=self.id,
            search_default_project_id=False,
        )
        return action
