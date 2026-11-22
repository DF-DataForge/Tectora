# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time

import pytz

from markupsafe import escape as html_escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero

from .project_task import WORK_KINDS

# Marks material values in pieces of a component with hercalculatie, still to
# be rounded up once the order's lines are added up per product.
ROUND_PIECES = "_schldr_round_pieces"

_logger = logging.getLogger(__name__)

# Fields kept equal between an order and its painting project: (order, job).
# Customer, opportunity, salesperson/project manager, delivery date/deadline
# and pricelist/project type.
SYNC_PAIRS = [
    ("partner_id", "partner_id"),
    ("opportunity_id", "opportunity_id"),
    ("user_id", "project_manager_id"),
    ("commitment_date", "date_deadline"),
    ("pricelist_id", "project_type"),
    # The order's delivery address is the site.
    ("partner_shipping_id", "site_partner_id"),
]
# Commercial data is only pushed onto an order that is still a quotation.
QUOTATION_ONLY = {"partner_id", "pricelist_id"}


def _differs(record, field_name, value):
    """Whether writing ``value`` (an id for relational fields) would change
    the record; an empty value against an empty field is no change."""
    current = record[field_name]
    if isinstance(current, models.BaseModel):
        current = current.id
    if not current and not value:
        return False
    return current != value


class SaleOrder(models.Model):
    _inherit = "sale.order"

    schldr_project_id = fields.Many2one(
        "schldr.project",
        string="Schilderproject",
        copy=False,
        index=True,
        help="Schilderproject (met optionele opmeting) van deze offerte/order. "
        "Elke order heeft er precies één: het wordt mee aangemaakt met de "
        "order, en klant, opportuniteit, verkoper, leverdatum en prijslijst "
        "blijven in beide richtingen gelijk.",
    )
    schldr_project_state = fields.Selection(
        related="schldr_project_id.state", string="Status schilderproject", readonly=True
    )
    schldr_total_area = fields.Float(
        related="schldr_project_id.total_area", string="Muren en plafonds (m²)"
    )
    schldr_estimated_hours = fields.Float(
        string="Geschatte uitvoeringstijd",
        compute="_compute_schldr_estimated_hours",
        store=True,
        digits=(16, 2),
        help="Uren voorbereiding en uren schilderen van de orderlijnen samen "
        "(hoeveelheid × de normen per eenheid van het product).",
    )
    schldr_preparation_hours = fields.Float(
        string="Geschatte tijd voorbereiding",
        compute="_compute_schldr_estimated_hours",
        store=True,
        digits=(16, 2),
        help="Som van de uren voorbereiding van de orderlijnen; wordt bij "
        "bevestiging de toegewezen tijd van de taak Voorbereiding.",
    )
    schldr_execution_hours = fields.Float(
        string="Geschatte tijd uitvoering",
        compute="_compute_schldr_estimated_hours",
        store=True,
        digits=(16, 2),
        help="Som van de uren schilderen van de orderlijnen; wordt bij "
        "bevestiging de toegewezen tijd van de taak Schilderwerken.",
    )
    schldr_estimated_days = fields.Float(
        string="Geschatte werkdagen",
        compute="_compute_schldr_estimated_days",
        digits=(16, 1),
        help="Geschatte uitvoeringstijd gedeeld door de uren per dag van de "
        "werktijden van het bedrijf.",
    )

    @api.depends(
        "order_line.schldr_execution_hours", "order_line.schldr_preparation_hours"
    )
    def _compute_schldr_estimated_hours(self):
        for order in self:
            hours = order._schldr_hours_by_kind()
            order.schldr_preparation_hours = hours["voorbereiding"]
            order.schldr_execution_hours = hours["uitvoering"]
            order.schldr_estimated_hours = hours["voorbereiding"] + hours["uitvoering"]

    def _schldr_hours_by_kind(self):
        """{'voorbereiding': hours, 'uitvoering': hours} of the order's lines."""
        self.ensure_one()
        lines = self.order_line.filtered(lambda line: not line.display_type)
        return {
            "voorbereiding": sum(lines.mapped("schldr_preparation_hours")),
            "uitvoering": sum(lines.mapped("schldr_execution_hours")),
        }

    @api.depends("schldr_estimated_hours", "company_id")
    def _compute_schldr_estimated_days(self):
        for order in self:
            order.schldr_estimated_days = (
                order.schldr_estimated_hours / order._schldr_hours_per_day()
            )

    def _schldr_hours_per_day(self):
        """Working hours of one day, from the company's working schedule."""
        calendar = (self.company_id or self.env.company).resource_calendar_id
        return calendar.hours_per_day if calendar and calendar.hours_per_day else 8.0

    @api.model
    def _schldr_hours_label(self, value):
        """``42 u 30`` for 42.5 hours."""
        total_minutes = int(round((value or 0.0) * 60))
        hours, minutes = divmod(total_minutes, 60)
        return _("%(hours)s u %(minutes)02d", hours=hours, minutes=minutes)

    schldr_tax_id = fields.Many2one(
        "account.tax",
        string="Btw-tarief voor alle regels",
        domain="[('type_tax_use', '=', 'sale'), ('company_id', 'in', [company_id, False])]",
        check_company=True,
        help="Eén btw-tarief voor de hele offerte, bv. 6% bij renovatie van een "
        "woning ouder dan 10 jaar. Kies het tarief en klik op 'Toepassen op "
        "alle regels': elke productregel krijgt dan dit tarief. Regels die "
        "nadien bijkomen, houden de btw van hun product tot u opnieuw toepast.",
    )
    schldr_follow_measurement = fields.Boolean(
        string="Offerte volgt de meting",
        copy=False,
        help="Aangevinkt past de offerte zich automatisch aan bij elke "
        "wijziging van de tekening of het schilderproject: hoeveelheden volgen de "
        "opgemeten oppervlakte en omtrek, meetlijnen worden herbouwd en lijnen "
        "die op het schilderproject wegvallen, verdwijnen van de offerte. "
        "Uitgevinkt (standaard) blijft de offerte zoals je ze opmaakt en "
        "dienen de plannen enkel als plan; 'Offerte bijwerken uit meting' "
        "op het schilderproject brengt ze dan na bevestiging eenmalig in lijn.",
    )
    schldr_locked = fields.Boolean(
        string="Offerte vastgezet",
        copy=False,
        tracking=True,
        help="Vastgezet kan de opmeting de lijnen van deze offerte niet meer "
        "overschrijven: geen automatische aanpassing, geen 'Offerte bijwerken "
        "uit meting'. Wat je op de offerte zelf doet, "
        "blijft mogelijk. 'Offerte vrijgeven' heft dat op.",
    )
    schldr_include_plan = fields.Boolean(
        string="Plan toevoegen",
        default=True,
        help="Neem het plan (tekening, oppervlakken en kleuren per ruimte) "
        "op in de offerte-pdf en toon het bij de offerte op het klantenportaal.",
    )

    @api.depends("partner_id", "company_id")
    def _compute_note(self):
        # Terms added as a PDF are printed on pages of their own after the
        # quotation, not in its note.
        super(SaleOrder, self.filtered(lambda order: order.company_id.terms_type != "pdf"))._compute_note()

    # ------------------------------------------------------------ lifecycle
    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        if self.env.context.get("schldr_sync"):
            return orders
        linked = orders.filtered("schldr_project_id")
        for order in linked:
            order._schldr_adopt_project(order.schldr_project_id)
        if not self.env.context.get("schldr_no_project"):
            (orders - linked)._schldr_create_project()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get("schldr_sync"):
            return result
        touched = set(vals)
        if "schldr_project_id" in touched:
            for order in self.filtered("schldr_project_id"):
                order._schldr_adopt_project(order.schldr_project_id)
        elif touched & {order_field for order_field, _job in SYNC_PAIRS}:
            for order in self.filtered("schldr_project_id"):
                order._schldr_sync_pair(
                    order.schldr_project_id, master="order", changed=touched
                )
        if vals.get("state") == "cancel":
            # The confirmation is undone: the painting project goes back to
            # "quoted"; its project (if any) keeps its history.
            self.schldr_project_id.filtered(
                lambda job: job.state == "confirmed"
            ).with_context(schldr_sync=True).write({"state": "quoted"})
        return result

    def action_confirm(self):
        """Confirming an order creates the plannable project (the basis of
        the post-calculation: revenue, material and other costs, invoices
        and timesheets are logged on it) and builds the material list from
        the bills of materials of the sold products."""
        result = super().action_confirm()
        for order in self.filtered(lambda order: order.state == "sale"):
            try:
                with self.env.cr.savepoint():
                    order._schldr_on_confirm()
            except Exception:
                _logger.exception(
                    "Could not build the project dossier for order %s", order.name
                )
        return result

    def _schldr_on_confirm(self):
        self.ensure_one()
        if not self.schldr_project_id:
            self._schldr_create_project()
        job = self.schldr_project_id
        if not job:
            return
        had_project = bool(job.project_id)
        project = job._ensure_project()
        if job.state != "done":
            job.with_context(schldr_sync=True).write({"state": "confirmed"})
        if project and not had_project:
            project.message_post(
                body=_(
                    "Project aangemaakt bij bevestiging van %(order)s "
                    "(schilderproject %(job)s).",
                    order=self._get_html_link(),
                    job=job._get_html_link(),
                )
            )
        self._schldr_generate_materials()
        self._schldr_sync_execution_task()

    # -------------------------------------------------------- execution task
    def _schldr_execution_project(self):
        self.ensure_one()
        return self.schldr_project_id.project_id or self.project_id

    def _schldr_sync_execution_task(self):
        """Put the order's estimated time on the project's tasks
        "Voorbereiding" and "Schilderwerken", one per work kind, so hours
        are logged apart: created on confirmation, their allocated time
        follows the estimate whenever the order changes afterwards. Only the
        allocated time is touched on an existing task; the rest belongs to
        whoever plans the work.
        """
        for order in self:
            if order.state != "sale":
                continue
            project = order._schldr_execution_project()
            if not project:
                continue
            hours_by_kind = order._schldr_hours_by_kind()
            deadline = order.commitment_date or order.schldr_project_id.planned_date_end
            for kind, _label in WORK_KINDS:
                hours = hours_by_kind[kind]
                task = project._schldr_work_task(kind)
                if task:
                    if float_compare(task.allocated_hours, hours, precision_digits=2):
                        task.write({"allocated_hours": hours})
                    continue
                if not hours:
                    continue  # nothing estimated for this kind: no task to size
                project._schldr_work_task(
                    kind,
                    create=True,
                    allocated_hours=hours,
                    date_deadline=deadline or False,
                    description=order._schldr_execution_task_description(kind),
                )

    def _schldr_execution_task_description(self, kind):
        """The estimate per works item of one work kind, so the task says
        where its time comes from."""
        self.ensure_one()
        rows = []
        lines = self.order_line.filtered(
            lambda line: not line.display_type and line._schldr_hours_of_kind(kind)
        )
        for line in lines.sorted(key=lambda line: -line._schldr_hours_of_kind(kind)):
            rows.append(
                "<tr><td>%s</td><td class='text-end'>%s %s</td>"
                "<td class='text-end'>%s u</td><td class='text-end'>%s u</td></tr>"
                % (
                    html_escape(line.product_id.display_name),
                    ("%.2f" % line.product_uom_qty).rstrip("0").rstrip("."),
                    html_escape(line.product_uom_id.name or ""),
                    ("%.3f" % line._schldr_norm_of_kind(kind)).rstrip("0").rstrip("."),
                    "%.2f" % line._schldr_hours_of_kind(kind),
                )
            )
        total = sum(line._schldr_hours_of_kind(kind) for line in lines)
        return (
            "<p>%s</p><table class='table table-sm'><thead><tr><th>%s</th>"
            "<th class='text-end'>%s</th><th class='text-end'>%s</th>"
            "<th class='text-end'>%s</th></tr></thead><tbody>%s</tbody></table>"
            % (
                _("%(kind)s, geschat uit %(order)s: %(hours)s.",
                  kind=dict(WORK_KINDS)[kind], order=self.name,
                  hours=self._schldr_hours_label(total)),
                _("Werkpost"), _("Hoeveelheid"), _("Per eenheid"), _("Uren"),
                "".join(rows),
            )
        )

    # -------------------------------------------------- painting project pairing
    def _schldr_project_values(self):
        """Values of the painting project that stands against this order."""
        self.ensure_one()
        partner = self.partner_id
        shipping = self.partner_shipping_id
        name = partner.name or self.name
        if shipping and shipping != partner and shipping.name:
            name = shipping.name
        address = shipping or partner
        values = {
            "name": name,
            "company_id": self.company_id.id or self.env.company.id,
            "site_partner_id": address.id if address else False,
            "state": "confirmed" if self.state in ("sale", "done") else "quoted",
        }
        values.update(self._schldr_project_values_from_order())
        return values

    def _schldr_free_project(self):
        """A painting project that is waiting for this order: the opportunity's
        painting project (made with "Schilderproject maken" on the lead) that has no
        open order yet. None when there is no such project."""
        self.ensure_one()
        if not self.opportunity_id:
            return None
        candidates = self.opportunity_id.schldr_project_ids.filtered(
            lambda job: job.company_id == self.company_id
            and job.state != "done"
            and not job.sale_order_ids.filtered(lambda o: o.state != "cancel")
        )
        return candidates.sorted("id")[:1] or None

    def _schldr_create_project(self, raise_if_failed=False):
        """Every order gets its own painting project: the one its opportunity
        prepared, or a new one made from the order.

        Called from create() and confirmation the failure is logged and the
        order goes on without a painting project; called from a button
        (``raise_if_failed``) the real error reaches the user.
        """
        Job = self.env["schldr.project"].with_context(schldr_sync=True)
        for order in self:
            try:
                with self.env.cr.savepoint():
                    job = order._schldr_free_project()
                    if job:
                        order.with_context(schldr_sync=True).write(
                            {"schldr_project_id": job.id}
                        )
                        order._schldr_sync_pair(job, master="project")
                        if job.state in ("draft", "measured"):
                            job.write({"state": "quoted"})
                        job.message_post(
                            body=_(
                                "Offerte %s gekoppeld aan dit schilderproject.",
                                order._get_html_link(),
                            )
                        )
                        order._schldr_mirror_lines(job)
                        continue
                    job = Job.create(order._schldr_project_values())
                    order.with_context(schldr_sync=True).write(
                        {"schldr_project_id": job.id}
                    )
                    job.message_post(
                        body=_(
                            "Schilderproject aangemaakt vanuit %s.",
                            order._get_html_link(),
                        )
                    )
                    order._schldr_mirror_lines(job)
            except Exception:
                if raise_if_failed:
                    raise
                _logger.exception(
                    "Could not create the painting project of order %s", order.name
                )
        return self.schldr_project_id

    def _schldr_adopt_project(self, job):
        """This order was pointed at ``job``: any other open order of that
        painting project is let go (one painting project, one order) and the two
        records are aligned, the order being the side the user just edited."""
        self.ensure_one()
        others = job.sale_order_ids.filtered(
            lambda other: other != self and other.state != "cancel"
        )
        if others:
            others.with_context(schldr_sync=True).write({"schldr_project_id": False})
        self._schldr_sync_pair(job, master="order")
        self._schldr_mirror_lines(job)

    # ------------------------------------------------------- line mirroring
    def _schldr_mirror_lines(self, job=None):
        """Bring the quotation in line with the plan of its painting project
        (when it follows the measurement, or the user asked for it)."""
        self.ensure_one()
        job = job or self.schldr_project_id
        if job and self.state in ("draft", "sent"):
            job._schldr_mirror_to_order(self)

    @api.onchange("sale_order_template_id")
    def _onchange_schldr_template_project_type(self):
        """The template says renovatie or nieuwbouw: the order takes the
        pricelist of that type, which the painting project follows."""
        kind = self.sale_order_template_id.schldr_project_type
        if not kind:
            return
        label = dict(self.env["sale.order.template"]._fields["schldr_project_type"].selection)[kind]
        pricelist = self.env["product.pricelist"].search(
            [("name", "=ilike", label), ("company_id", "in", [False, self.company_id.id])],
            limit=1,
        )
        if pricelist and pricelist != self.pricelist_id:
            self.pricelist_id = pricelist

    def action_schldr_toggle_lock(self):
        """Zet offerte vast / Offerte vrijgeven: while locked, the job
        measurement no longer changes the quotation's lines (and it no longer
        follows the measurement)."""
        for order in self:
            locked = not order.schldr_locked
            values = {"schldr_locked": locked}
            if locked:
                values["schldr_follow_measurement"] = False
            order.with_context(schldr_sync=True).write(values)
            order.message_post(body=_(
                "Offerte vastgezet: de opmeting past de lijnen niet meer aan."
            ) if locked else _(
                "Offerte vrijgegeven: 'Offerte bijwerken uit meting' kan de lijnen weer aanpassen."
            ))
        return True

    # --------------------------------------------------------- field mirror
    @api.model
    def _schldr_project_to_order_fields(self):
        return [job_field for _order, job_field in SYNC_PAIRS]

    def _schldr_sync_pair(self, job, master="order", changed=None):
        """Keep this order and ``job`` equal on the shared fields.

        ``master`` names the side that was edited: its values win, and when
        it explicitly changed a field (``changed`` given) even an emptied value
        is mirrored. Without ``changed`` the pair is being linked: the master
        pushes what it has and the other side fills in what the master left
        empty.
        """
        self.ensure_one()
        job.ensure_one()
        if master == "order":
            job_vals = self._schldr_project_values_from_order(changed, job=job)
            order_vals = (
                {} if changed is not None
                else self._schldr_order_values_from_project(job, only_missing=True)
            )
        else:
            order_vals = self._schldr_order_values_from_project(job, changed)
            job_vals = (
                {} if changed is not None
                else self._schldr_project_values_from_order(only_missing=True, job=job)
            )
        job_vals = {
            key: value for key, value in job_vals.items()
            if _differs(job, key, value)
        }
        order_vals = {
            key: value for key, value in order_vals.items()
            if _differs(self, key, value)
        }
        if job_vals:
            job.with_context(schldr_sync=True).write(job_vals)
        if order_vals:
            self.with_context(schldr_sync=True).write(order_vals)
        return True

    def _schldr_project_values_from_order(self, changed=None, only_missing=False, job=None):
        """Painting project values mirroring this order.

        ``changed``: only the pairs whose order field is in it (None = all);
        ``only_missing``: only for job fields that are empty on ``job``.
        """
        self.ensure_one()
        job = job if job is not None else self.schldr_project_id
        explicit = changed is not None
        values = {}

        def wanted(order_field, job_field):
            if explicit and order_field not in changed:
                return False
            if only_missing and job and job[job_field]:
                return False
            return True

        if wanted("partner_id", "partner_id") and self.partner_id:
            values["partner_id"] = self.partner_id.id
        if wanted("opportunity_id", "opportunity_id") and (
            self.opportunity_id or explicit
        ):
            values["opportunity_id"] = self.opportunity_id.id or False
        if wanted("user_id", "project_manager_id") and (self.user_id or explicit):
            values["project_manager_id"] = self.user_id.id or False
        if wanted("commitment_date", "date_deadline") and (
            self.commitment_date or explicit
        ):
            values["date_deadline"] = (
                fields.Datetime.context_timestamp(self, self.commitment_date).date()
                if self.commitment_date else False
            )
        if wanted("pricelist_id", "project_type") and self.pricelist_id:
            project_type = self._schldr_project_type_from_pricelist()
            if project_type:
                values["project_type"] = project_type
        # Another customer gets its own delivery address (Odoo recomputes it
        # without it being written), so the site follows that too.
        site_changed = explicit and "partner_id" in changed and not only_missing
        if (wanted("partner_shipping_id", "site_partner_id") or site_changed) \
                and self.partner_shipping_id:
            values["site_partner_id"] = self.partner_shipping_id.id
        return values

    def _schldr_order_values_from_project(self, job, changed=None, only_missing=False):
        """Order values mirroring ``job``; see _schldr_project_values_from_order.
        Commercial fields are only produced while the order is a quotation."""
        self.ensure_one()
        explicit = changed is not None
        quotation = self.state in ("draft", "sent")
        values = {}

        def wanted(order_field, job_field):
            if explicit and job_field not in changed:
                return False
            if only_missing and self[order_field]:
                return False
            if order_field in QUOTATION_ONLY and not quotation:
                return False
            return True

        if wanted("partner_id", "partner_id") and job.partner_id:
            values["partner_id"] = job.partner_id.id
        if wanted("opportunity_id", "opportunity_id") and (
            job.opportunity_id or explicit
        ):
            values["opportunity_id"] = job.opportunity_id.id or False
        if wanted("user_id", "project_manager_id") and job.project_manager_id:
            values["user_id"] = job.project_manager_id.id
        if wanted("commitment_date", "date_deadline") and (
            job.date_deadline or explicit
        ):
            values["commitment_date"] = self._schldr_deadline_to_datetime(
                job.date_deadline
            )
        if wanted("pricelist_id", "project_type") and job.project_type:
            pricelist = job._find_pricelist()
            if pricelist:
                values["pricelist_id"] = pricelist.id
        if wanted("partner_shipping_id", "site_partner_id") and job.site_partner_id:
            values["partner_shipping_id"] = job.site_partner_id.id
        return values

    def _schldr_project_type_from_pricelist(self):
        """Project type whose label the pricelist name carries, or None."""
        self.ensure_one()
        name = (self.pricelist_id.name or "").lower()
        selection = self.env["schldr.project"]._fields["project_type"].selection
        for key, label in selection:
            if label.lower() in name:
                return key
        return None

    def _schldr_deadline_to_datetime(self, deadline):
        """A deadline date becomes a delivery date at 08:00 in the user's
        time zone; the existing delivery date is kept when it already falls
        on that day."""
        if not deadline:
            return False
        current = self.commitment_date
        if current and fields.Datetime.context_timestamp(self, current).date() == deadline:
            return current
        tz = pytz.timezone(self.env.user.tz or "UTC")
        local = tz.localize(datetime.combine(deadline, time(hour=8)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    # ------------------------------------------------------------------- btw
    def action_apply_schldr_tax(self):
        """Put the chosen tax on every product line. Deliberately a button,
        not an automatism: the user decides when the whole order switches."""
        for order in self:
            lines = order.order_line.filtered(lambda line: not line.display_type)
            if not lines:
                continue
            if order.schldr_tax_id:
                lines.with_context(schldr_sync=True).write(
                    {"tax_ids": [(6, 0, order.schldr_tax_id.ids)]}
                )
            else:
                # No tax chosen: back to the taxes of the products and the
                # fiscal position.
                lines.with_context(schldr_sync=True)._compute_tax_ids()
        return True

    # ---------------------------------------------------------------- report
    def _schldr_report_sections(self, optional=False):
        """The order lines grouped under their section headers, with a
        subtotal per section, for the dossier PDF. Lines before the first
        header form a nameless first group. Subsections and notes stay in
        the group as lines (their display_type tells them apart).

        Odoo 19 and 20 mark optional products as sections flagged ``is_optional``:
        ``optional=False`` returns the ordinary sections, ``optional=True``
        the optional ones (offered separately, outside the totals).
        """
        self.ensure_one()
        sections = []
        current = {"name": False, "lines": [], "subtotal": 0.0, "measurement": False, "optional": False}
        for line in self.order_line:
            if line.display_type == "line_section":
                if current["lines"] or current["name"]:
                    sections.append(current)
                current = {
                    "name": line.name,
                    "lines": [],
                    "subtotal": 0.0,
                    "measurement": bool(line.schldr_measurement_line),
                    "optional": bool(getattr(line, "is_optional", False)),
                }
                continue
            current["lines"].append(line)
            if not line.display_type:
                current["subtotal"] += line.price_subtotal
        if current["lines"] or current["name"]:
            sections.append(current)
        return [section for section in sections if section["optional"] == optional]

    def _schldr_report_tax_label(self, line):
        """"21%" for a line's taxes, the way a customer reads them."""
        labels = []
        for tax in line.tax_ids:
            amount = ("%g" % tax.amount) if tax.amount_type == "percent" else tax.name
            labels.append("%s%%" % amount if tax.amount_type == "percent" else amount)
        return ", ".join(labels)

    # --------------------------------------------------------------- catalog
    # The "Catalog" button of the order lines can be shown under a selected
    # line (static/src/sale_order_line/add_line_below_selection.js). It then
    # passes that line's position in the context, and the products picked in
    # the catalog are inserted right after it instead of at the bottom.

    def _get_action_add_from_catalog_extra_context(self):
        context = super()._get_action_add_from_catalog_extra_context()
        after_index = self.env.context.get("schldr_catalog_after_index")
        if isinstance(after_index, int) and after_index >= 0:
            # Resolved to the line that follows now (the order was just saved),
            # so it keeps pointing at the same place while lines are added.
            lines = self._schldr_ordered_lines()
            if after_index + 1 < len(lines):
                context["schldr_catalog_before_line_id"] = lines[after_index + 1].id
        return context

    def _update_order_line_info(self, product, quantity, uom, child_field, **kwargs):
        # Sent by the catalog (catalog_insert_position.js). Taken out of
        # kwargs, which are passed on to the price computation.
        before_line_id = kwargs.pop("schldr_before_line_id", False)
        if before_line_id:
            self = self.with_context(schldr_catalog_before_line_id=before_line_id)
        return super()._update_order_line_info(product, quantity, uom, child_field, **kwargs)

    def _catalog_prepare_new_line_vals(self, child_field, product, quantity, uom, **kwargs):
        vals = super()._catalog_prepare_new_line_vals(
            child_field, product, quantity, uom, **kwargs
        )
        before_line_id = self.env.context.get("schldr_catalog_before_line_id")
        if child_field == "order_line" and before_line_id:
            lines = self._schldr_ordered_lines()
            before = lines.filtered(lambda line: line.id == before_line_id)
            if before:
                # Take the place of the line that follows and move it and every
                # line after it one down. A line before it with the same
                # sequence still comes first: the new line has the higher id.
                following = lines[lines.ids.index(before.id):]
                for sequence, group in following.grouped("sequence").items():
                    group.sequence = sequence + 1
                vals["sequence"] = before.sequence - 1
        return vals

    def _schldr_ordered_lines(self):
        """The order lines in the order the quotation shows them."""
        return self.order_line.sorted(lambda line: (line.sequence, line.id))

    # ---------------------------------------------------------- smart buttons
    def action_view_schldr_project(self):
        """The painting project of this order (created on the spot if the order
        was made without one)."""
        self.ensure_one()
        if not self.schldr_project_id:
            self._schldr_create_project(raise_if_failed=True)
        if not self.schldr_project_id:
            raise UserError(
                _(
                    "Het schilderproject kon niet aangemaakt worden; kijk in de "
                    "serverlog voor de oorzaak."
                )
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "schldr.project",
            "res_id": self.schldr_project_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_project_dashboard(self):
        """The project dashboard of this order; a confirmed order without a
        project yet gets one first."""
        self.ensure_one()
        project = self.project_id
        if not project and self.schldr_project_id:
            project = self.schldr_project_id.project_id
        if not project:
            if self.state not in ("sale", "done"):
                raise UserError(
                    _(
                        "Het project wordt aangemaakt bij het bevestigen van de "
                        "order. Bevestig eerst de offerte."
                    )
                )
            if not self.schldr_project_id:
                self._schldr_create_project(raise_if_failed=True)
            project = self.schldr_project_id._ensure_project()
        return project.action_open_dashboard()

    # ---------------------------------------------------------- material list
    def _schldr_material_values(self, line, product, quantity, uom, bom_name):
        return {
            "project_id": self.schldr_project_id.id,
            "product_id": product.id,
            "product_uom_id": (uom or product.uom_id).id,
            "quantity": quantity,
            "source_product_id": line.product_id.id,
            "bom_name": bom_name or False,
            "sale_order_id": self.id,
            "sale_order_line_id": line.id,
        }

    def _schldr_find_boms(self, products):
        """First bill of materials per product, ordered as Odoo orders them.

        Deliberately not ``mrp.bom._bom_find``: that drops service products,
        and the works items Schldr sells are services, so it would
        never return the bill of materials that was imported for them.
        """
        BoM = self.env.get("mrp.bom")  # Manufacturing is an optional dependency
        if BoM is None or not products:
            return {}
        boms = BoM.search(
            # Explicit prefix operators: & active & company | variant (& any
            # variant, template).
            [
                "&", ("active", "=", True),
                "&", ("company_id", "in", [False, self.company_id.id]),
                "|", ("product_id", "in", products.ids),
                "&", ("product_id", "=", False),
                ("product_tmpl_id", "in", products.product_tmpl_id.ids),
            ],
            order="sequence, id",
        )
        by_product = {}
        by_template = {}
        for bom in boms:
            if bom.product_id:
                by_product.setdefault(bom.product_id, bom)
            else:
                by_template.setdefault(bom.product_tmpl_id, bom)
        for product in products:
            if product not in by_product and product.product_tmpl_id in by_template:
                by_product[product] = by_template[product.product_tmpl_id]
        return by_product

    def _schldr_line_material_values(self, line, bom):
        """Material requirement values of one order line, exploded from
        ``bom`` (its product's bill of materials, or None).

        A product without one is itself the material if it is goods; a
        service without one is labour and contributes nothing. Extension
        point: a line can bring its own components (schldr_sale_bom).
        """
        quantity = line.product_uom_qty
        if not bom:
            if line.product_id.type == "service":
                return []  # works item with no bill of materials: labour
            return [
                self._schldr_material_values(
                    line, line.product_id, quantity, line.product_uom_id, None
                )
            ]
        # explode() expects how many times the BoM is needed, in the BoM's
        # own unit of measure.
        bom_quantity = quantity
        if line.product_uom_id and bom.uom_id != line.product_uom_id:
            bom_quantity = line.product_uom_id._compute_quantity(
                quantity, bom.uom_id
            )
        factor = bom_quantity / (bom.product_qty or 1.0)
        _boms_done, lines_done = bom.explode(line.product_id, factor)
        return [
            self._schldr_component_values(
                line,
                bom_line.product_id,
                self._schldr_exploded_quantity(bom, factor, bom_line, line_data),
                bom_line.uom_id,
                bom.display_name,
            )
            for bom_line, line_data in lines_done
        ]

    def _schldr_component_values(self, line, product, quantity, uom, bom_name, margin=None):
        """Material values of a component of a bill of materials. A component
        with hercalculatie is counted in m² or m³ on the bill of materials
        and needed in pieces: ``quantity`` is turned into pieces of the
        product's own unit, with the product's safety margin or ``margin``
        (in %, a bill of materials line's own). Not rounded yet: the pieces
        are rounded up once per product, when the lines of the order are
        added up (_schldr_merge_material_values)."""
        if product.schldr_recalc:
            quantity = product.product_tmpl_id._schldr_recalc_pieces(quantity, margin)
            values = self._schldr_material_values(line, product, quantity, product.uom_id, bom_name)
            # Pieces, to be rounded up on the product's total.
            values[ROUND_PIECES] = True
            return values
        return self._schldr_material_values(line, product, quantity, uom, bom_name)

    def _schldr_exploded_quantity(self, bom, factor, bom_line, line_data):
        """Quantity of one exploded component; ``factor`` is how many times
        ``bom`` is needed. Extension point for components whose quantity does
        not follow the order line (schldr_sale_bom)."""
        return line_data["qty"]

    def _schldr_merge_material_values(self, values):
        """One material line per product: what the order lines need of a
        product (several works items need the same primer or screws, a
        credit line takes some back) is added up, in the unit of its first
        line (another unit of the same kind is converted). A component with
        hercalculatie is rounded up to whole pieces on the total, not per
        order line. What adds up to nothing is left out."""
        Product = self.env["product.product"]
        Uom = self.env["uom.uom"]
        merged = {}
        for vals in values:
            product = Product.browse(vals["product_id"])
            uom = Uom.browse(vals.get("product_uom_id")) or product.uom_id
            key = product.id
            current = merged.get(key)
            if current:
                target = Uom.browse(current["product_uom_id"])
                if uom != target and not uom._has_common_reference(target):
                    # Units that do not convert stay on their own line.
                    key = (product.id, uom.id)
                    current = merged.get(key)
            if not current:
                merged[key] = dict(vals, product_uom_id=uom.id, bom_name=vals.get("bom_name") or False)
                continue
            target = Uom.browse(current["product_uom_id"])
            quantity = vals["quantity"]
            if uom != target:
                quantity = uom._compute_quantity(quantity, target, round=False)
            current["quantity"] += quantity
            if vals.get(ROUND_PIECES):
                current[ROUND_PIECES] = True
            for field in ("source_product_id", "sale_order_line_id"):
                if current.get(field) != vals.get(field):
                    current[field] = False
            names = [name for name in (current["bom_name"] or "").split("; ") if name]
            if vals.get("bom_name") and vals["bom_name"] not in names:
                names.append(vals["bom_name"])
            current["bom_name"] = "; ".join(names) or False
        result = []
        for vals in merged.values():
            product = Product.browse(vals["product_id"])
            if vals.pop(ROUND_PIECES, False):
                vals["quantity"] = product.product_tmpl_id._schldr_round_pieces(vals["quantity"])
            if float_is_zero(vals["quantity"], precision_digits=6):
                continue
            result.append(vals)
        return result

    def _schldr_generate_materials(self):
        """Explode every sold product into material requirements.

        The paint comes from the plan: what the layers of the paint systems
        take, per product and colour. Besides that, a sold product with a
        bill of materials contributes its components and one without is
        itself the material if it is goods; a service is labour. Lines
        generated by an earlier confirmation of this order are replaced.
        """
        self.ensure_one()
        Material = self.env["schldr.material"]
        Material.search([("sale_order_id", "=", self.id)]).unlink()

        # The works of the plan are services: their paint comes from the
        # layers of the paint systems, per colour and rounded to pots. Every
        # other line goes the usual way (goods are material, a product with
        # a bill of materials gives its components).
        lines = self.order_line.filtered(
            lambda line: not line.display_type and line.product_id
            and not (line.schldr_measurement_line and not line.schldr_line_id)
        )
        boms = self._schldr_find_boms(lines.product_id)
        values = []
        for line in lines:
            values += self._schldr_line_material_values(line, boms.get(line.product_id))
        values = self._schldr_merge_material_values(values)
        values += self.schldr_project_id._schldr_plan_material_values(self)
        materials = Material.create(values) if values else Material
        if materials:
            self.schldr_project_id.message_post(
                body=_(
                    "Materiaallijst bijgewerkt uit %(order)s: %(count)s "
                    "materiaallijn(en).",
                    order=self.name,
                    count=len(materials),
                )
            )
        return materials
