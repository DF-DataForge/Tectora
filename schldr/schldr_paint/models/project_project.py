# -*- coding: utf-8 -*-
"""The plannable project behind an order and its painting project.

A confirmed order gets a ``project.project``. It carries the analytic account
on which the post-calculation is built -- revenue, material and purchase
costs, invoices, timesheets -- and its dashboard shows, per project: revenue
and costs, the status of the deliveries, the open tasks and the planning of
the team, with the measurement itself as part of the dashboard.
"""
import logging
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .project_task import WORK_KINDS

_logger = logging.getLogger(__name__)


class ProjectProject(models.Model):
    _inherit = "project.project"

    schldr_project_ids = fields.One2many(
        "schldr.project", "project_id", string="Schilderprojecten",
        export_string_translation=False,
    )
    schldr_project_id = fields.Many2one(
        "schldr.project",
        string="Schilderproject",
        compute="_compute_schldr_project_id",
        inverse="_inverse_schldr_project_id",
        store=True,
        readonly=False,
        copy=False,
        index=True,
        help="Schilderproject (meting) van dit project; één schilderproject per project.",
    )
    schldr_sale_order_id = fields.Many2one(
        "sale.order",
        string="Offerte / Order",
        compute="_compute_schldr_sale_order_id",
        help="De order waaruit dit project ontstond: die van het schilderproject, "
        "of de order waaraan het project in Verkoop hangt.",
    )
    schldr_sale_order_state = fields.Selection(
        related="schldr_sale_order_id.state", string="Orderstatus"
    )

    # --- the measurement, mirrored on the dashboard ---------------------
    schldr_state = fields.Selection(related="schldr_project_id.state", string="Status schilderproject")
    schldr_address = fields.Char(related="schldr_project_id.address", string="Werfadres")
    schldr_project_type = fields.Selection(
        related="schldr_project_id.project_type", string="Projecttype"
    )
    schldr_total_area = fields.Float(
        related="schldr_project_id.total_area", string="Muren en plafonds (m²)"
    )
    schldr_total_floor_area = fields.Float(
        related="schldr_project_id.total_floor_area", string="Vloeroppervlakte (m²)"
    )
    schldr_room_count = fields.Integer(
        related="schldr_project_id.room_count", string="Ruimtes"
    )
    schldr_canvas_snapshot = fields.Binary(
        related="schldr_project_id.canvas_snapshot", string="Tekening"
    )
    schldr_room_ids = fields.One2many(
        related="schldr_project_id.room_ids", string="Ruimtes (meting)"
    )
    schldr_material_line_ids = fields.One2many(
        related="schldr_project_id.material_line_ids", string="Materiaallijst"
    )
    schldr_team_id = fields.Many2one(related="schldr_project_id.team_id", string="Ploeg")
    schldr_planned_date_begin = fields.Datetime(
        related="schldr_project_id.planned_date_begin", string="Geplande start"
    )
    schldr_planned_date_end = fields.Datetime(
        related="schldr_project_id.planned_date_end", string="Gepland einde"
    )
    schldr_work_block_ids = fields.One2many(
        related="schldr_project_id.planning_ids", string="Werkblokken"
    )

    # --- post-calculation ----------------------------------------------------
    schldr_revenue = fields.Monetary(
        string="Omzet (order)", compute="_compute_schldr_profitability",
        currency_field="currency_id",
        help="Bedrag excl. btw van de bevestigde order.",
    )
    schldr_invoiced = fields.Monetary(
        string="Gefactureerd", compute="_compute_schldr_profitability",
        currency_field="currency_id",
    )
    schldr_to_invoice = fields.Monetary(
        string="Te factureren", compute="_compute_schldr_profitability",
        currency_field="currency_id",
    )
    schldr_costs = fields.Monetary(
        string="Kosten", compute="_compute_schldr_profitability",
        currency_field="currency_id",
        help="Alle kosten op de analytische rekening van het project: "
        "aankopen, leveranciersfacturen, urenstaten, voorraadbewegingen.",
    )
    schldr_cost_billed = fields.Monetary(
        string="Kosten (geboekt)", compute="_compute_schldr_profitability",
        currency_field="currency_id",
    )
    schldr_cost_to_bill = fields.Monetary(
        string="Kosten (verwacht)", compute="_compute_schldr_profitability",
        currency_field="currency_id",
    )
    schldr_margin = fields.Monetary(
        string="Marge", compute="_compute_schldr_profitability",
        currency_field="currency_id",
        help="Omzet (gefactureerd + te factureren) min de kosten.",
    )
    schldr_margin_percent = fields.Float(
        string="Marge (%)", compute="_compute_schldr_profitability", digits=(16, 1)
    )
    schldr_material_cost = fields.Monetary(
        related="schldr_project_id.material_cost", string="Materiaalkost (stuklijst)",
        currency_field="currency_id",
    )
    schldr_material_count = fields.Integer(
        related="schldr_project_id.material_count", string="Materiaallijnen"
    )
    schldr_timesheet_hours = fields.Float(
        string="Uren", compute="_compute_schldr_timesheets",
        help="Uren op de urenstaten van dit project.",
    )
    schldr_timesheet_cost = fields.Monetary(
        string="Loonkost", compute="_compute_schldr_timesheets",
        currency_field="currency_id",
    )
    schldr_has_timesheets = fields.Boolean(compute="_compute_schldr_timesheets")

    # --- invoices, deliveries, purchases -------------------------------------
    schldr_invoice_count = fields.Integer(
        string="Facturen", compute="_compute_schldr_invoices"
    )
    schldr_invoice_due = fields.Monetary(
        string="Openstaand", compute="_compute_schldr_invoices",
        currency_field="currency_id",
    )
    schldr_picking_count = fields.Integer(
        string="Leveringen", compute="_compute_schldr_pickings"
    )
    schldr_picking_done_count = fields.Integer(
        string="Leveringen gedaan", compute="_compute_schldr_pickings"
    )
    schldr_delivery_status = fields.Selection(
        [
            ("none", "Geen leveringen"),
            ("waiting", "Te leveren"),
            ("partial", "Deels geleverd"),
            ("done", "Geleverd"),
        ],
        string="Leverstatus",
        compute="_compute_schldr_pickings",
    )
    schldr_purchase_count = fields.Integer(
        string="Inkooporders", compute="_compute_schldr_purchases"
    )
    schldr_purchase_amount = fields.Monetary(
        string="Inkoop (excl. btw)", compute="_compute_schldr_purchases",
        currency_field="currency_id",
    )

    # --- planning ------------------------------------------------------------
    schldr_planning_count = fields.Integer(
        string="Werkblokken", compute="_compute_schldr_planning"
    )
    schldr_planning_hours = fields.Float(
        string="Geplande uren", compute="_compute_schldr_planning",
        help="Uren van de werkblokken, maal het aantal ingeplande medewerkers.",
    )
    schldr_next_planning_date = fields.Datetime(
        string="Volgende werkdag", compute="_compute_schldr_planning"
    )
    schldr_planned_employee_ids = fields.Many2many(
        "hr.employee", string="Ingeplande medewerkers",
        compute="_compute_schldr_planning",
    )
    schldr_estimated_hours = fields.Float(
        related="schldr_sale_order_id.schldr_estimated_hours",
        string="Geschatte uitvoeringstijd",
        help="Uit de order: hoeveelheid × geschatte tijd per eenheid van elk "
        "product. Staat als toegewezen tijd op de taken van het project.",
    )

    # ------------------------------------------------------------------ links
    @api.depends("schldr_project_ids")
    def _compute_schldr_project_id(self):
        for project in self:
            jobs = project.schldr_project_ids
            if project.schldr_project_id and project.schldr_project_id in jobs:
                continue
            project.schldr_project_id = jobs[:1]

    def _inverse_schldr_project_id(self):
        for project in self:
            job = project.schldr_project_id
            others = project.schldr_project_ids - job
            if others:
                others.with_context(schldr_sync=True).write({"project_id": False})
            if job and job.project_id != project:
                job.with_context(schldr_sync=True).write({"project_id": project.id})
                job._schldr_link_order_to_project(project)

    @api.depends(
        "schldr_project_id.sale_order_id", "sale_line_id", "reinvoiced_sale_order_id"
    )
    def _compute_schldr_sale_order_id(self):
        SaleOrder = self.env["sale.order"]
        for project in self:
            order = project.schldr_project_id.sale_order_id
            if not order:
                order = project.sudo().reinvoiced_sale_order_id or project.sale_order_id
            if not order and project.id:
                order = SaleOrder.search([("project_id", "=", project.id)], limit=1)
            project.schldr_sale_order_id = order

    # ------------------------------------------------------------ profitability
    def _schldr_profitability_totals(self):
        """Revenues and costs of the project, as the dashboard shows them.
        Costs come back negative. Empty dict when there is no analytic
        account to read them from.

        Up to Odoo 19 these came from project._get_profitability_items(),
        which Odoo 20 removed (with the profitability panel) in favour of a
        single real_cost figure; the same four totals are read here from the
        records themselves:

        * invoiced / to invoice: the order lines' untaxed invoiced and
          to-invoice amounts;
        * billed: every cost booked on the project's analytic account (vendor
          bills, timesheets, stock valuation...), which is Odoo 20's own
          real_cost;
        * to bill: confirmed purchase lines charged to that account and not
          billed yet (only with Purchase installed).
        """
        self.ensure_one()
        return self._schldr_profitability_by_project().get(self.id, {})

    def _schldr_profitability_by_project(self):
        """The totals of _schldr_profitability_totals for many projects at
        once, read with one query per kind of record instead of per project
        (the projects overview): {project id: totals}, projects without an
        analytic account left out."""
        projects = self.filtered(lambda project: project.id and project.account_id)
        if not projects:
            return {}
        accounts = projects.account_id
        costs = dict(self.env["account.analytic.line"].sudo()._read_group(
            [("account_id", "in", accounts.ids), ("amount", "<", 0)],
            ["account_id"],
            ["amount:sum"],
        ))
        to_bill = dict.fromkeys(accounts.ids, 0.0)
        PurchaseLine = self.env.get("purchase.order.line")
        if PurchaseLine is not None:
            # As Odoo 19 counted it: what was ordered for the project, less
            # what posted vendor bills already cover (those are "billed").
            def share(distribution, account):
                # A key can combine accounts of several plans ("12,40").
                return sum(
                    float(percentage)
                    for key, percentage in (distribution or {}).items()
                    if str(account.id) in key.split(",")
                ) / 100.0

            purchase_lines = PurchaseLine.sudo().search(
                [("analytic_distribution", "in", accounts.ids), ("display_type", "=", False)]
            ).filtered(lambda line: line.order_id.state in ("purchase", "done"))
            lines_by_account = {}
            for line in purchase_lines:
                for key in line.analytic_distribution or {}:
                    for account_id in str(key).split(","):
                        if account_id.isdigit():
                            lines_by_account.setdefault(int(account_id), []).append(line)
            for project in projects:
                account = project.account_id

                def in_project_currency(line, amount):
                    return line.currency_id._convert(
                        amount, project.currency_id, project.company_id,
                        fields.Date.context_today(project),
                    )

                for line in dict.fromkeys(lines_by_account.get(account.id, [])):
                    line_share = share(line.analytic_distribution, account)
                    ordered = in_project_currency(line, line.price_subtotal) * line_share
                    billed = sum(
                        in_project_currency(bill_line, bill_line.price_subtotal)
                        * share(bill_line.analytic_distribution, account)
                        for bill_line in line.invoice_lines
                        if bill_line.parent_state == "posted" and not bill_line.is_refund
                    )
                    to_bill[account.id] += ordered - billed
        totals = {}
        for project in projects:
            order = project.schldr_sale_order_id.sudo()
            sale_lines = order.order_line.filtered(lambda line: not line.display_type)
            account = project.account_id
            totals[project.id] = {
                "invoiced": sum(sale_lines.mapped("untaxed_amount_invoiced")),
                "to_invoice": sum(sale_lines.mapped("untaxed_amount_to_invoice")),
                "billed": costs.get(account, 0.0),
                "to_bill": -to_bill[account.id],
            }
        return totals

    @api.depends(
        "account_id", "schldr_sale_order_id.amount_untaxed",
        "schldr_sale_order_id.state", "schldr_project_id.material_cost",
    )
    def _compute_schldr_profitability(self):
        for project in self:
            order = project.schldr_sale_order_id
            project.schldr_revenue = (
                order.amount_untaxed if order and order.state in ("sale", "done") else 0.0
            )
            totals = project._schldr_profitability_totals()
            project.schldr_invoiced = totals.get("invoiced", 0.0)
            project.schldr_to_invoice = totals.get("to_invoice", 0.0)
            project.schldr_cost_billed = -totals.get("billed", 0.0)
            project.schldr_cost_to_bill = -totals.get("to_bill", 0.0)
            project.schldr_costs = (
                project.schldr_cost_billed + project.schldr_cost_to_bill
            )
            revenue_total = project.schldr_invoiced + project.schldr_to_invoice
            if not revenue_total and not totals:
                revenue_total = project.schldr_revenue
            project.schldr_margin = revenue_total - project.schldr_costs
            project.schldr_margin_percent = (
                project.schldr_margin / revenue_total * 100.0 if revenue_total else 0.0
            )

    def _compute_schldr_timesheets(self):
        has_timesheets = "timesheet_ids" in self._fields
        for project in self:
            project.schldr_has_timesheets = has_timesheets
            if not has_timesheets or not project.id:
                project.schldr_timesheet_hours = 0.0
                project.schldr_timesheet_cost = 0.0
                continue
            lines = project.sudo().timesheet_ids
            project.schldr_timesheet_hours = sum(lines.mapped("unit_amount"))
            project.schldr_timesheet_cost = -sum(lines.mapped("amount"))

    # --------------------------------------------- invoices, deliveries, POs
    def _schldr_invoices(self):
        self.ensure_one()
        order = self.schldr_sale_order_id
        invoices = order.sudo().invoice_ids if order else self.env["account.move"]
        return invoices.filtered(lambda move: move.state != "cancel")

    @api.depends("schldr_sale_order_id.invoice_ids.state", "schldr_sale_order_id.invoice_ids.amount_residual")
    def _compute_schldr_invoices(self):
        for project in self:
            invoices = project._schldr_invoices()
            project.schldr_invoice_count = len(invoices)
            project.schldr_invoice_due = sum(
                invoices.filtered(
                    lambda move: move.state == "posted"
                    and move.move_type in ("out_invoice", "out_refund")
                ).mapped("amount_residual_signed")
            )

    def _schldr_pickings(self):
        """Deliveries of the order (sale_stock); empty without Inventory."""
        self.ensure_one()
        order = self.schldr_sale_order_id
        if not order or "picking_ids" not in order._fields:
            return None
        return order.sudo().picking_ids.filtered(lambda p: p.state != "cancel")

    def _compute_schldr_pickings(self):
        for project in self:
            pickings = project._schldr_pickings()
            if not pickings:
                project.schldr_picking_count = 0
                project.schldr_picking_done_count = 0
                project.schldr_delivery_status = "none"
                continue
            done = pickings.filtered(lambda p: p.state == "done")
            project.schldr_picking_count = len(pickings)
            project.schldr_picking_done_count = len(done)
            if len(done) == len(pickings):
                project.schldr_delivery_status = "done"
            elif done:
                project.schldr_delivery_status = "partial"
            else:
                project.schldr_delivery_status = "waiting"

    def _schldr_purchase_orders(self):
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

    def _compute_schldr_purchases(self):
        for project in self:
            orders = project._schldr_purchase_orders()
            project.schldr_purchase_count = len(orders) if orders else 0
            project.schldr_purchase_amount = (
                sum(orders.mapped("amount_untaxed")) if orders else 0.0
            )

    # ---------------------------------------------------------------- planning
    @api.depends(
        "schldr_project_id.planning_ids.start_datetime",
        "schldr_project_id.planning_ids.end_datetime",
        "schldr_project_id.planning_ids.employee_ids",
        "schldr_project_id.planning_ids.state",
    )
    def _compute_schldr_planning(self):
        now = fields.Datetime.now()
        for project in self:
            blocks = project.schldr_project_id.planning_ids
            project.schldr_planning_count = len(blocks)
            project.schldr_planning_hours = sum(
                block.duration_hours * max(len(block.employee_ids), 1)
                for block in blocks
            )
            upcoming = blocks.filtered(
                lambda block: block.end_datetime and block.end_datetime >= now
            ).sorted("start_datetime")
            project.schldr_next_planning_date = (
                upcoming[:1].start_datetime if upcoming else False
            )
            project.schldr_planned_employee_ids = blocks.employee_ids

    # ------------------------------------------------------------------- sync
    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get("schldr_sync"):
            return result
        touched = set(vals) & {"partner_id", "user_id", "date_start", "date"}
        if touched:
            for project in self.filtered("schldr_project_id"):
                values = project._schldr_paint_values(touched)
                if values:
                    project.schldr_project_id.with_context(schldr_sync=True).write(values)
        return result

    def _schldr_paint_values(self, changed):
        """Painting project values that follow this project: customer, project
        manager and the planned window (project dates are days, the job
        project plans in hours: 07:00-17:00 in the user's time zone)."""
        self.ensure_one()
        job = self.schldr_project_id
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
            if local_date(job.planned_date_begin) != self.date_start:
                values["planned_date_begin"] = at_hour(self.date_start, 7)
        if "date" in changed and self.date:
            if local_date(job.planned_date_end) != self.date:
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
                        "schldr_paint.view_project_project_schldr_dashboard"
                    ).id,
                    "form",
                )
            ],
            "target": "current",
            "context": dict(self.env.context, schldr_dashboard=True),
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

    def _schldr_ensure_project(self):
        """A project made outside the painting flow gets its painting project on
        first request, tied to the project's order when there is one."""
        self.ensure_one()
        if self.schldr_project_id:
            return self.schldr_project_id
        order = self.schldr_sale_order_id
        if order:
            job = order.schldr_project_id or order._schldr_create_project(
                raise_if_failed=True
            )
        else:
            job = self.env["schldr.project"].with_context(
                schldr_sync=True
            ).create(
                {
                    "name": self.name,
                    "partner_id": self.partner_id.id or False,
                    "company_id": self.company_id.id or self.env.company.id,
                    "project_manager_id": self.user_id.id or False,
                }
            )
        if job:
            job.with_context(schldr_sync=True).write({"project_id": self.id})
            self.invalidate_recordset(["schldr_project_id", "schldr_project_ids"])
        return job

    def action_view_schldr_project(self):
        self.ensure_one()
        job = self._schldr_ensure_project()
        if not job:
            raise UserError(_("Het schilderproject kon niet aangemaakt worden."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "schldr.project",
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_sale_order(self):
        """The order of the project, or a new quotation for it."""
        self.ensure_one()
        order = self.schldr_sale_order_id
        if order:
            return {
                "type": "ir.actions.act_window",
                "res_model": "sale.order",
                "res_id": order.id,
                "view_mode": "form",
                "target": "current",
            }
        job = self._schldr_ensure_project()
        context = {
            "default_partner_id": self.partner_id.id,
            "default_project_id": self.id if self.allow_billable else False,
            "default_company_id": self.company_id.id,
        }
        if job:
            context.update(
                {
                    "default_%s" % key: value
                    for key, value in job._prepare_sale_order_values().items()
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

    def action_view_schldr_tasks(self):
        self.ensure_one()
        return self.action_view_tasks()

    def _schldr_work_task(self, kind, create=False, **values):
        """The project's task of one work kind, Voorbereiding or
        Schilderwerken: the order sizes it with its estimate, the crew logs
        its hours on it. Created on request, so hours registered before the
        order is confirmed still land on the right task."""
        self.ensure_one()
        Task = self.env["project.task"].sudo()
        task = Task.search(
            [("project_id", "=", self.id), ("schldr_work_kind", "=", kind)],
            limit=1,
        )
        if not task and create:
            task = Task.create({
                "name": dict(WORK_KINDS)[kind],
                "project_id": self.id,
                "partner_id": self.partner_id.id,
                "schldr_work_kind": kind,
                **values,
            })
        return task

    def action_view_schldr_profitability(self):
        """Odoo's own profitability panel of the project, for the detail
        behind the revenue and cost figures."""
        self.ensure_one()
        action = self.with_context(active_id=self.id).project_update_all_action()
        action["context"] = dict(
            self.env.context, active_id=self.id, default_project_id=self.id
        )
        return action

    def action_view_schldr_invoices(self):
        self.ensure_one()
        invoices = self._schldr_invoices()
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

    def action_view_schldr_pickings(self):
        self.ensure_one()
        pickings = self._schldr_pickings()
        if pickings is None:
            raise UserError(_("De module Voorraad is niet geïnstalleerd."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Leveringen"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", pickings.ids)],
        }

    def action_view_schldr_purchases(self):
        self.ensure_one()
        orders = self._schldr_purchase_orders()
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

    def action_view_schldr_materials(self):
        self.ensure_one()
        job = self._schldr_ensure_project()
        return {
            "type": "ir.actions.act_window",
            "name": _("Materiaallijst"),
            "res_model": "schldr.material",
            "view_mode": "list,form",
            "domain": [("project_id", "=", job.id)],
            "context": {"default_project_id": job.id},
        }

    def action_view_schldr_planning(self):
        """The work blocks of the project's painting project (the Planning bridge
        opens the employees' shifts in the planner instead)."""
        self.ensure_one()
        job = self._schldr_ensure_project()
        return job.action_view_planning()

    def action_view_schldr_timesheets(self):
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
