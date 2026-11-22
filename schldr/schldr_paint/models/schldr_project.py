# -*- coding: utf-8 -*-
import logging
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TASK_STAGE_XMLIDS = (
    "schldr_paint.project_task_type_nieuw",
    "schldr_paint.project_task_type_bezig",
    "schldr_paint.project_task_type_klaar",
    "schldr_paint.project_task_type_geannuleerd",
)

# 50 px per meter — same default as the legacy standalone canvas when no
# satellite background (and thus no geographic scale) is available.


class SchldrProject(models.Model):
    _name = "schldr.project"
    _description = "Schilderproject"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    _rec_names_search = ["name", "code", "partner_id.name"]

    name = fields.Char(string="Projectnaam", required=True, tracking=True)
    code = fields.Char(
        string="Referentie", readonly=True, copy=False, default=lambda self: _("New")
    )
    partner_id = fields.Many2one(
        "res.partner", string="Klant", tracking=True, check_company=True
    )
    opportunity_id = fields.Many2one("crm.lead", string="Opportuniteit")
    site_partner_id = fields.Many2one(
        "res.partner",
        string="Werfadres",
        tracking=True,
        index=True,
        help="Het adres van de werf als contact, standaard een afleveradres "
        "van de klant. Het is het afleveradres van de offerte en de order, in "
        "beide richtingen.",
    )
    address = fields.Char(
        string="Werfadres (tekst)", compute="_compute_address", store=True, readonly=False,
        help="Het werfadres op één lijn, voor het satellietbeeld, de planning "
        "en het weer: dat van het werfadres-contact, anders het adres van de "
        "klant of wat hier getypt is.",
    )
    description = fields.Text(string="Notities")
    state = fields.Selection(
        [
            ("draft", "Concept"),
            ("measured", "Opgemeten"),
            ("quoted", "Offerte gemaakt"),
            ("confirmed", "Order bevestigd"),
            ("done", "Afgerond"),
        ],
        default="draft",
        tracking=True,
    )
    project_type = fields.Selection(
        [
            ("renovatie", "Renovatie"),
            ("nieuwbouw", "Nieuwbouw"),
            ("industrie", "Industrie"),
        ],
        string="Projecttype",
        default="renovatie",
        tracking=True,
        help="Bepaalt de prijslijst op de gegenereerde offerte: er wordt "
        "gezocht naar een prijslijst met dezelfde naam als het projecttype.",
    )
    company_id = fields.Many2one(
        "res.company", string="Bedrijf", default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    color = fields.Integer(
        string="Kleur",
        help="Kleur van dit project in de planner: elk blok van het project "
        "krijgt ze. Wordt automatisch gekozen en kan hier aangepast worden.",
    )

    sale_order_ids = fields.One2many(
        "sale.order", "schldr_project_id", string="Offertes / Orders",
        help="Alle offertes en orders die ooit aan dit schilderproject hingen; "
        "de actieve staat in Offerte / Order.",
    )
    sale_order_count = fields.Integer(compute="_compute_sale_order_count")
    sale_order_id = fields.Many2one(
        "sale.order",
        string="Offerte / Order",
        compute="_compute_sale_order_id",
        inverse="_inverse_sale_order_id",
        store=True,
        readonly=False,
        copy=False,
        index=True,
        help="De verkooporder van dit schilderproject: één schilderproject staat "
        "tegenover één offerte/order. Klant, opportuniteit, verkoper, "
        "leverdatum en prijslijst/projecttype worden in beide richtingen "
        "gelijk gehouden. Een geannuleerde order blijft in de historiek "
        "(Offertes / Orders) en maakt plaats voor een nieuwe.",
    )
    sale_order_state = fields.Selection(
        related="sale_order_id.state", string="Orderstatus", readonly=True
    )
    sale_order_follow_measurement = fields.Boolean(
        related="sale_order_id.schldr_follow_measurement",
        readonly=False,
    )
    sale_order_locked = fields.Boolean(
        related="sale_order_id.schldr_locked", string="Offerte vastgezet",
    )

    # --- Project dossier: analytic accounting, costs, deliveries, invoices ---
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        copy=False,
        ondelete="set null",
        index=True,
        help="Planbaar Odoo-project achter dit schilderproject, aangemaakt bij het "
        "bevestigen van de order. Het draagt de analytische rekening waarop "
        "omzet en kosten (order, facturen, inkoop, leveringen, urenstaten) "
        "samenkomen en toont het projectdashboard.",
    )
    analytic_account_id = fields.Many2one(
        related="project_id.account_id", string="Analytische rekening", readonly=True
    )
    material_line_ids = fields.One2many(
        "schldr.material", "project_id", string="Materiaallijst"
    )
    material_count = fields.Integer(compute="_compute_material_totals")
    material_cost = fields.Monetary(
        string="Materiaalkost",
        compute="_compute_material_totals",
        currency_field="currency_id",
    )
    revenue = fields.Monetary(
        string="Omzet (excl. btw)",
        compute="_compute_revenue",
        currency_field="currency_id",
        help="Bevestigde verkooporders van dit schilderproject.",
    )
    margin = fields.Monetary(
        string="Marge",
        compute="_compute_revenue",
        currency_field="currency_id",
        help="Omzet minus de kostprijs van de materiaallijst.",
    )
    picking_count = fields.Integer(compute="_compute_logistics_counts")
    purchase_count = fields.Integer(compute="_compute_logistics_counts")
    invoice_count = fields.Integer(compute="_compute_logistics_counts")

    # --- Planning on teams ---------------------------------------------------
    team_id = fields.Many2one(
        "schldr.team",
        string="Ploeg",
        tracking=True,
        help="Ploeg die de werf uitvoert. Samen met de geplande data wordt "
        "automatisch een werkblok aangemaakt met planning-items voor elke "
        "medewerker van de ploeg.",
    )
    planned_date_begin = fields.Datetime(string="Geplande start", tracking=True)
    planned_date_end = fields.Datetime(string="Gepland einde", tracking=True)
    planning_ids = fields.One2many(
        "schldr.planning", "project_id", string="Werkblokken"
    )
    planning_count = fields.Integer(compute="_compute_planning_count")

    # ------------------------------------------------------------------ compute
    @api.depends(
        "partner_id", "site_partner_id", "site_partner_id.street", "site_partner_id.street2",
        "site_partner_id.zip", "site_partner_id.city", "site_partner_id.country_id",
    )
    def _compute_address(self):
        for project in self:
            site = project.site_partner_id
            if site:
                project.address = site._schldr_one_line_address()
            elif not project.address and project.partner_id:
                project.address = project.partner_id._schldr_one_line_address()


    def _compute_sale_order_count(self):
        for project in self:
            project.sale_order_count = len(project.sale_order_ids)

    @api.depends("code", "name")
    def _compute_display_name(self):
        for project in self:
            code = project.code if project.code and project.code != _("New") else ""
            project.display_name = " — ".join(filter(None, [code, project.name]))

    @api.depends("sale_order_ids", "sale_order_ids.state")
    def _compute_sale_order_id(self):
        """The one order that stands against this painting project: the most
        recent one that is not cancelled, or -- when every order was
        cancelled -- the most recent one, so the history stays reachable."""
        for project in self:
            orders = project.sale_order_ids.sorted("id", reverse=True)
            current = project.sale_order_id
            if current and current in orders and current.state != "cancel":
                continue
            active = orders.filtered(lambda order: order.state != "cancel")
            project.sale_order_id = (active or orders)[:1]

    def _inverse_sale_order_id(self):
        """Linking an order from the painting project side: the order points back
        at this painting project and any other open order of the project is let
        go, so the pair stays one-to-one. Cancelled orders stay as history."""
        for project in self:
            order = project.sale_order_id
            others = project.sale_order_ids.filtered(
                lambda o: o != order and o.state != "cancel"
            )
            if others:
                others.with_context(schldr_sync=True).write(
                    {"schldr_project_id": False}
                )
            if order and order.schldr_project_id != project:
                order.with_context(schldr_sync=True).write(
                    {"schldr_project_id": project.id}
                )
                order._schldr_sync_pair(project, master="project")

    @api.depends("planning_ids")
    def _compute_planning_count(self):
        for project in self:
            project.planning_count = len(project.planning_ids)

    @api.depends("material_line_ids.cost_subtotal")
    def _compute_material_totals(self):
        for project in self:
            project.material_count = len(project.material_line_ids)
            project.material_cost = sum(
                project.material_line_ids.mapped("cost_subtotal")
            )

    @api.depends(
        "sale_order_ids.state",
        "sale_order_ids.amount_untaxed",
        "material_line_ids.cost_subtotal",
    )
    def _compute_revenue(self):
        for project in self:
            confirmed = project.sale_order_ids.filtered(
                lambda order: order.state == "sale"
            )
            project.revenue = sum(confirmed.mapped("amount_untaxed"))
            project.margin = project.revenue - sum(
                project.material_line_ids.mapped("cost_subtotal")
            )

    def _compute_logistics_counts(self):
        for project in self:
            orders = project.sale_order_ids
            pickings = project._get_pickings()
            project.picking_count = len(pickings) if pickings is not None else 0
            project.invoice_count = len(orders.mapped("invoice_ids"))
            purchases = project._get_purchase_orders()
            project.purchase_count = len(purchases) if purchases is not None else 0

    # --------------------------------------------------------- project dossier
    def _get_pickings(self):
        """Deliveries of the project's sale orders (sale_stock). Returns None
        when Inventory is not installed (an optional dependency)."""
        self.ensure_one()
        Picking = self.env.get("stock.picking")
        orders = self.sale_order_ids
        if Picking is None or "picking_ids" not in orders._fields:
            return None
        return orders.mapped("picking_ids")

    def _get_purchase_orders(self):
        """Purchase orders whose lines carry the project's analytic account.

        Returns None when Purchase is not installed (an optional dependency).
        """
        self.ensure_one()
        PurchaseLine = self.env.get("purchase.order.line")
        if PurchaseLine is None:
            return None
        account = self.analytic_account_id
        if not account:
            return self.env["purchase.order"]
        # analytic.mixin's search accepts account ids for the JSON field.
        lines = PurchaseLine.search([("analytic_distribution", "in", [account.id])])
        return lines.order_id

    def _prepare_project_values(self):
        self.ensure_one()
        values = {
            "name": self._project_name(),
            "partner_id": self.partner_id.id or False,
            "company_id": self.company_id.id or self.env.company.id,
            "allow_billable": True,
        }
        if self.project_manager_id:
            values["user_id"] = self.project_manager_id.id
        values.update(
            self._schldr_project_sync_values(
                {"planned_date_begin", "planned_date_end"}
            )
        )
        Project = self.env["project.project"]
        if "allow_timesheets" in Project._fields:
            values["allow_timesheets"] = True
        stages = self._schldr_task_stages()
        if stages:
            # Shared stages: otherwise every project gets four of its own.
            values["type_ids"] = [Command.set(stages.ids)]
        return values

    @api.model
    def _schldr_task_stages(self):
        """The task stages the projects share: Nieuw, Bezig, Klaar,
        Geannuleerd (those still there and active)."""
        stages = self.env["project.task.type"]
        for xmlid in TASK_STAGE_XMLIDS:
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage and stage.active:
                stages |= stage
        return stages

    def _ensure_project(self):
        """Create (or complete) the plannable project and its analytic
        account, so revenue, costs, POs, deliveries, invoices and timesheets
        aggregate on it. Links the project to the order as well."""
        Project = self.env["project.project"].with_context(schldr_sync=True)
        for job in self:
            project = job.project_id
            if not project:
                # An order confirmed with project-generating services may
                # already have had its project created by Odoo: adopt it.
                order = job.sale_order_id
                candidates = order.project_id if order else Project
                if order and not candidates and "project_ids" in order._fields:
                    candidates = order.sudo().project_ids.filtered(
                        lambda p: p.active and not p.schldr_project_id
                    )
                project = candidates[:1]
                if project:
                    project.write(
                        {
                            key: value
                            for key, value in job._prepare_project_values().items()
                            if key in ("allow_billable", "date_start", "date")
                            or not project[key]
                        }
                    )
                else:
                    project = Project.create(job._prepare_project_values())
                job.with_context(schldr_sync=True).project_id = project
            elif not project.partner_id and job.partner_id:
                project.partner_id = job.partner_id
            # sale.order.project_id only accepts billable projects.
            if not project.allow_billable:
                project.allow_billable = True
            if not project.account_id:
                project._create_analytic_account()
            job._schldr_link_order_to_project(project)
        return self.mapped("project_id")

    def _schldr_link_order_to_project(self, project):
        """Point the order and the project at each other, the way Odoo's own
        sale/project bridge expects it (so its smart buttons and its
        profitability report pick the order up too)."""
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return
        order_values = {}
        if order.project_id != project:
            order_values["project_id"] = project.id
        if order_values:
            order.with_context(schldr_sync=True).write(order_values)
            # Re-trigger the analytic distribution now the project is known.
            order.order_line._compute_analytic_distribution()
        project_values = {}
        if (
            "reinvoiced_sale_order_id" in project._fields
            and not project.sudo().reinvoiced_sale_order_id
        ):
            project_values["reinvoiced_sale_order_id"] = order.id
        if "sale_line_id" in project._fields and not project.sale_line_id:
            # Not a line invoiced on timesheets: hours logged on the project
            # must not become invoiceable quantities by accident.
            service_line = order.order_line.filtered(
                lambda line: not line.display_type
                and line.product_id
                and line.product_id.type == "service"
                and not line.is_downpayment
                and getattr(line.product_id, "service_policy", None)
                != "delivered_timesheet"
            )[:1]
            if service_line and order.state == "sale":
                project_values["sale_line_id"] = service_line.id
        if project_values:
            project.sudo().with_context(schldr_sync=True).write(project_values)

    def action_open_project(self):
        """Open the project dashboard; a painting project without a project yet
        gets one (the button is the manual counterpart of the confirmation)."""
        self.ensure_one()
        self._ensure_project()
        return self.project_id.action_open_dashboard()

    def action_view_materials(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Materiaallijst"),
            "res_model": "schldr.material",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_view_pickings(self):
        self.ensure_one()
        pickings = self._get_pickings()
        if pickings is None:
            raise UserError(_("De module Voorraad is niet geïnstalleerd."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Leveringen"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("id", "in", pickings.ids)],
        }

    def action_view_purchase_orders(self):
        self.ensure_one()
        orders = self._get_purchase_orders()
        if orders is None:
            raise UserError(_("De module Inkoop is niet geïnstalleerd."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Inkooporders"),
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", orders.ids)],
        }

    def action_view_invoices(self):
        self.ensure_one()
        invoices = self.sale_order_ids.mapped("invoice_ids")
        return {
            "type": "ir.actions.act_window",
            "name": _("Facturen"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", invoices.ids)],
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Without a site of its own, the site is the customer's address.
            if vals.get("partner_id") and not vals.get("site_partner_id") and not vals.get("address"):
                vals["site_partner_id"] = vals["partner_id"]
            if not vals.get("code") or vals["code"] == _("New"):
                vals["code"] = (
                    self.env["ir.sequence"].next_by_code("schldr.project")
                    or _("New")
                )
        projects = super().create(vals_list)
        # Every project its own planner colour, spread over the palette.
        for project in projects.filtered(lambda p: not p.color):
            project.color = (project.id % 11) + 1
        projects._autogenerate_planning()
        return projects

    def write(self, vals):
        if vals.get("partner_id") and "site_partner_id" not in vals:
            # The site of another customer is not this one's: it becomes the
            # new customer (or one of its addresses, chosen afterwards).
            customer = self.env["res.partner"].browse(vals["partner_id"]).commercial_partner_id
            if any(
                project.site_partner_id
                and project.site_partner_id.commercial_partner_id != customer
                for project in self
            ):
                vals = dict(vals, site_partner_id=vals["partner_id"])
        result = super().write(vals)
        if {"team_id", "planned_date_begin", "planned_date_end"} & set(vals):
            self._autogenerate_planning()
        if "quote_notes" in vals and not self.env.context.get("schldr_sync"):
            self._schldr_mirror_to_order()
        if not self.env.context.get("schldr_sync"):
            self._schldr_push_sync(vals)
        return result

    # ------------------------------------------------ sale order / project sync
    def _schldr_push_sync(self, vals):
        """Mirror the fields shared with the order and the project onto them.

        The painting project is the master here: whatever was just written on it
        goes to its order (customer, opportunity, salesperson/project manager,
        deadline, project type as pricelist) and to its project (customer,
        planned dates, project manager). The context flag stops the write from
        coming straight back.
        """
        SaleOrder = self.env["sale.order"]
        order_fields = set(SaleOrder._schldr_project_to_order_fields())
        project_fields = {
            "partner_id", "planned_date_begin", "planned_date_end",
            "project_manager_id", "name", "code", "address",
        }
        touched = set(vals)
        for project in self:
            order = project.sale_order_id
            if order and touched & order_fields:
                order._schldr_sync_pair(project, master="project", changed=touched)
            dossier = project.project_id
            if dossier and touched & project_fields:
                dossier.with_context(schldr_sync=True).write(
                    project._schldr_project_sync_values(touched)
                )

    def _schldr_project_sync_values(self, fields_changed=None):
        """Values of the project (project.project) that follow this job
        project; restricted to the job fields in ``fields_changed``."""
        self.ensure_one()
        values = {}
        changed = fields_changed or {
            "partner_id", "planned_date_begin", "planned_date_end",
            "project_manager_id", "name", "code", "address",
        }
        if "partner_id" in changed and self.partner_id:
            values["partner_id"] = self.partner_id.id
        if {"planned_date_begin", "planned_date_end"} & changed:
            begin = self.planned_date_begin
            end = self.planned_date_end
            if begin:
                values["date_start"] = fields.Datetime.context_timestamp(
                    self, begin
                ).date()
            if end:
                values["date"] = fields.Datetime.context_timestamp(self, end).date()
        if "project_manager_id" in changed and self.project_manager_id:
            values["user_id"] = self.project_manager_id.id
        if {"name", "code", "partner_id", "address"} & changed:
            values["name"] = self._project_name()
        return values

    def _schldr_vendor_reference(self):
        """The reference of this site on a purchase order (its vendor
        reference): "SCH/2026/0107 · Dhr. Peeters — Heule"."""
        self.ensure_one()
        code = self.code if self.code and self.code != _("New") else ""
        return " · ".join(filter(None, [code, self.name]))

    def _site_city(self):
        """Municipality of the site: the order's delivery address, else the
        customer's, else the last part of the free-text site address
        ("Straat 1, 9790 Wortegem" -> "Wortegem")."""
        self.ensure_one()
        order = self.sale_order_id
        for partner in (order.partner_shipping_id if order else None, self.partner_id):
            if partner and partner.city:
                return partner.city.strip()
        match = re.search(r"\b\d{4,5}\s+([^,]+?)\s*$", self.address or "")
        if match:
            return match.group(1).strip()
        return ""

    def _project_name(self):
        """Name of the project: the customer and the municipality of the site
        ("Data Forge — Wortegem"); the painting project's own name as fallback."""
        self.ensure_one()
        customer = self.partner_id.name or ""
        name = " — ".join(filter(None, [customer, self._site_city()]))
        return name or self.name

    # ---------------------------------------------------------- team planning
    def _autogenerate_planning(self):
        """A project with a team and a planned window gets its work block (and
        through it the individual employee planning items) automatically.
        Existing blocks are never overwritten: use the button to add one."""
        for project in self:
            if not (
                project.team_id
                and project.planned_date_begin
                and project.planned_date_end
                and not project.planning_ids
            ):
                continue
            project._create_planning_item()
        return True

    def _create_planning_item(self):
        self.ensure_one()
        return self.env["schldr.planning"].create(
            {
                "project_id": self.id,
                "team_id": self.team_id.id or False,
                "employee_ids": [(6, 0, self.team_id.member_ids.ids)],
                "start_datetime": self.planned_date_begin,
                "end_datetime": self.planned_date_end,
            }
        )

    def action_generate_planning(self):
        self.ensure_one()
        if not (self.planned_date_begin and self.planned_date_end):
            raise UserError(
                _("Vul eerst de geplande start- en einddatum van de werf in.")
            )
        if not self.team_id:
            raise UserError(_("Kies eerst de ploeg die de werf uitvoert."))
        self._create_planning_item()
        return self.action_view_planning()

    def action_view_planning(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planning"),
            "res_model": "schldr.planning",
            "view_mode": "calendar,list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {
                "default_project_id": self.id,
                "default_team_id": self.team_id.id,
                "default_start_datetime": self.planned_date_begin,
                "default_end_datetime": self.planned_date_end,
            },
        }

    def _project_type_label(self):
        self.ensure_one()
        return dict(self._fields["project_type"].selection).get(self.project_type, "")


    def action_schldr_toggle_quote_lock(self):
        """Zet offerte vast / Offerte vrijgeven, from the painting project."""
        self.ensure_one()
        if self.sale_order_id:
            self.sale_order_id.action_schldr_toggle_lock()
        return True

    def _find_pricelist(self):
        """Pricelist named after the project type, if the company has one."""
        self.ensure_one()
        if not self.project_type:
            return self.env["product.pricelist"]
        type_label = dict(self._fields["project_type"].selection)[self.project_type]
        return self.env["product.pricelist"].search(
            [
                ("name", "=ilike", type_label),
                ("company_id", "in", [False, self.company_id.id]),
            ],
            limit=1,
        )

    def _prepare_sale_order_values(self):
        self.ensure_one()
        values = {
            "partner_id": self.partner_id.id,
            "opportunity_id": self.opportunity_id.id or False,
            "origin": self.code,
            "schldr_project_id": self.id,
            "company_id": self.company_id.id or self.env.company.id,
        }
        if self.project_manager_id:
            values["user_id"] = self.project_manager_id.id
        if self.project_id:
            values["project_id"] = self.project_id.id
        pricelist = self._find_pricelist()
        if pricelist:
            values["pricelist_id"] = pricelist.id
        return values

    def action_create_sale_order(self):
        """Create the quotation of the painting project, or bring it in line with
        the measurement.

        One painting project stands against one order: an open quotation is
        aligned (chapter lines and measurement lines follow the painting project,
        manual lines stay), a confirmed order is left alone, and only when
        there is no open order a new quotation is created.
        """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Kies eerst de klant van het project."))
        order = self.sale_order_id
        if order and order.state == "cancel":
            order = self.env["sale.order"]
        if order and order.state in ("draft", "sent") and order.schldr_locked:
            raise UserError(_(
                "Offerte %(order)s is vastgezet: de meting past ze niet meer aan. "
                "Geef ze eerst vrij ('Offerte vrijgeven').",
                order=order.name,
            ))
        if order and order.state not in ("draft", "sent"):
            raise UserError(
                _(
                    "Order %(order)s van dit schilderproject is al bevestigd. Pas de "
                    "order zelf aan, of annuleer ze en maak een nieuwe offerte.",
                    order=order.name,
                )
            )
        if not order:
            if not (self.line_ids or self.assignment_ids):
                raise UserError(_(
                    "Er staat nog geen verfsysteem op het plan en er zijn geen "
                    "algemene werken. Teken eerst de ruimtes of voeg werken toe."
                ))
            order = self.env["sale.order"].with_context(schldr_sync=True).create(
                self._prepare_sale_order_values()
            )
            self.message_post(
                body=_(
                    "Offerte %s gemaakt uit de meting.",
                    order._get_html_link(),
                )
            )
        else:
            self.message_post(
                body=_(
                    "Offerte %s bijgewerkt uit de meting.",
                    order._get_html_link(),
                )
            )
        # Asked for by the user (the update asks for confirmation first).
        self.with_context(schldr_update_from_measurement=True)._schldr_mirror_to_order(order)
        # The meetblad is rendered as an extra page inside the quotation PDF
        # itself (see report_saleorder_inherit_schldr), so no separate
        # attachment is created here.
        if self.state in ("draft", "measured"):
            self.with_context(schldr_sync=True).state = "quoted"
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_sale_order(self):
        """The order of this painting project; a new quotation when there is
        none yet (the smart button is always there)."""
        self.ensure_one()
        order = self.sale_order_id
        if order:
            return {
                "type": "ir.actions.act_window",
                "res_model": "sale.order",
                "res_id": order.id,
                "view_mode": "form",
                "target": "current",
            }
        context = {
            "default_%s" % key: value
            for key, value in self._prepare_sale_order_values().items()
        }
        return {
            "type": "ir.actions.act_window",
            "name": _("Offerte"),
            "res_model": "sale.order",
            "view_mode": "form",
            "target": "current",
            "context": context,
        }

    def action_view_sale_orders(self):
        """History of every quotation/order of this painting project."""
        self.ensure_one()
        if len(self.sale_order_ids) <= 1:
            return self.action_view_sale_order()
        return {
            "type": "ir.actions.act_window",
            "name": _("Offertes / Orders"),
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("schldr_project_id", "=", self.id)],
            "context": {
                "default_schldr_project_id": self.id,
                "default_partner_id": self.partner_id.id,
            },
        }
