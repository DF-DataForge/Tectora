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
ROUND_PIECES = "_tectora_round_pieces"

_logger = logging.getLogger(__name__)

# Fields kept equal between an order and its roof project: (order, roof).
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

    roof_project_id = fields.Many2one(
        "tectora.roof.project",
        string="Dakproject",
        copy=False,
        index=True,
        help="Dakproject (met optionele dakmeting) van deze offerte/order. "
        "Elke order heeft er precies één: het wordt mee aangemaakt met de "
        "order, en klant, opportuniteit, verkoper, leverdatum en prijslijst "
        "blijven in beide richtingen gelijk.",
    )
    tectora_roof_ids = fields.One2many(
        related="roof_project_id.roof_ids", string="Daken", readonly=True,
    )
    roof_project_state = fields.Selection(
        related="roof_project_id.state", string="Status dakproject", readonly=True
    )
    roof_total_area = fields.Float(
        related="roof_project_id.total_area", string="Dakoppervlakte (m²)"
    )
    tectora_estimated_hours = fields.Float(
        string="Geschatte uitvoeringstijd",
        compute="_compute_tectora_estimated_hours",
        store=True,
        digits=(16, 2),
        help="Uren afbraak en uren opbouw van de orderlijnen samen "
        "(hoeveelheid × de normen per eenheid van het product).",
    )
    tectora_demolition_hours = fields.Float(
        string="Geschatte tijd afbraak",
        compute="_compute_tectora_estimated_hours",
        store=True,
        digits=(16, 2),
        help="Som van de uren afbraak van de orderlijnen; wordt bij "
        "bevestiging de toegewezen tijd van de taak Afbraakwerken.",
    )
    tectora_execution_hours = fields.Float(
        string="Geschatte tijd uitvoering",
        compute="_compute_tectora_estimated_hours",
        store=True,
        digits=(16, 2),
        help="Som van de uren opbouw van de orderlijnen; wordt bij "
        "bevestiging de toegewezen tijd van de taak Uitvoeringswerken.",
    )
    tectora_estimated_days = fields.Float(
        string="Geschatte werkdagen",
        compute="_compute_tectora_estimated_days",
        digits=(16, 1),
        help="Geschatte uitvoeringstijd gedeeld door de uren per dag van de "
        "werktijden van het bedrijf.",
    )

    @api.depends(
        "order_line.tectora_execution_hours", "order_line.tectora_demolition_hours"
    )
    def _compute_tectora_estimated_hours(self):
        for order in self:
            hours = order._tectora_hours_by_kind()
            order.tectora_demolition_hours = hours["afbraak"]
            order.tectora_execution_hours = hours["uitvoering"]
            order.tectora_estimated_hours = hours["afbraak"] + hours["uitvoering"]

    def _tectora_hours_by_kind(self):
        """{'afbraak': hours, 'uitvoering': hours} of the order's lines."""
        self.ensure_one()
        lines = self.order_line.filtered(lambda line: not line.display_type)
        return {
            "afbraak": sum(lines.mapped("tectora_demolition_hours")),
            "uitvoering": sum(lines.mapped("tectora_execution_hours")),
        }

    @api.depends("tectora_estimated_hours", "company_id")
    def _compute_tectora_estimated_days(self):
        for order in self:
            order.tectora_estimated_days = (
                order.tectora_estimated_hours / order._tectora_hours_per_day()
            )

    def _tectora_hours_per_day(self):
        """Working hours of one day, from the company's working schedule."""
        calendar = (self.company_id or self.env.company).resource_calendar_id
        return calendar.hours_per_day if calendar and calendar.hours_per_day else 8.0

    @api.model
    def _tectora_hours_label(self, value):
        """``42 u 30`` for 42.5 hours."""
        total_minutes = int(round((value or 0.0) * 60))
        hours, minutes = divmod(total_minutes, 60)
        return _("%(hours)s u %(minutes)02d", hours=hours, minutes=minutes)

    tectora_tax_id = fields.Many2one(
        "account.tax",
        string="Btw-tarief voor alle regels",
        domain="[('type_tax_use', '=', 'sale'), ('company_id', 'in', [company_id, False])]",
        check_company=True,
        help="Eén btw-tarief voor de hele offerte, bv. 6% bij renovatie van een "
        "woning ouder dan 10 jaar. Kies het tarief en klik op 'Toepassen op "
        "alle regels': elke productregel krijgt dan dit tarief. Regels die "
        "nadien bijkomen, houden de btw van hun product tot u opnieuw toepast.",
    )
    tectora_follow_measurement = fields.Boolean(
        string="Offerte volgt de meting",
        copy=False,
        help="Aangevinkt past de offerte zich automatisch aan bij elke "
        "wijziging van de tekening of het dakproject: hoeveelheden volgen de "
        "opgemeten oppervlakte en omtrek, meetlijnen worden herbouwd en lijnen "
        "die op het dakproject wegvallen, verdwijnen van de offerte. "
        "Uitgevinkt (standaard) blijft de offerte zoals je ze opmaakt en "
        "dienen de dakplannen enkel als plan; 'Offerte bijwerken uit meting' "
        "op het dakproject brengt ze dan na bevestiging eenmalig in lijn.",
    )
    tectora_include_roof_plan = fields.Boolean(
        string="Dakplan toevoegen",
        default=True,
        help="Neem het dakplan (tekening, maten en producten per daksectie) "
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
        if self.env.context.get("tectora_sync"):
            return orders
        linked = orders.filtered("roof_project_id")
        for order in linked:
            order._tectora_adopt_roof_project(order.roof_project_id)
        if not self.env.context.get("tectora_no_roof_project"):
            (orders - linked)._tectora_create_roof_project()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get("tectora_sync"):
            return result
        touched = set(vals)
        if "roof_project_id" in touched:
            for order in self.filtered("roof_project_id"):
                order._tectora_adopt_roof_project(order.roof_project_id)
        elif touched & {order_field for order_field, _roof in SYNC_PAIRS}:
            for order in self.filtered("roof_project_id"):
                order._tectora_sync_pair(
                    order.roof_project_id, master="order", changed=touched
                )
        if vals.get("state") == "cancel":
            # The confirmation is undone: the roof project goes back to
            # "quoted"; its project (if any) keeps its history.
            self.roof_project_id.filtered(
                lambda roof: roof.state == "confirmed"
            ).with_context(tectora_sync=True).write({"state": "quoted"})
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
                    order._tectora_on_confirm()
            except Exception:
                _logger.exception(
                    "Could not build the project dossier for order %s", order.name
                )
        return result

    def _tectora_on_confirm(self):
        self.ensure_one()
        if not self.roof_project_id:
            self._tectora_create_roof_project()
        roof = self.roof_project_id
        if not roof:
            return
        had_project = bool(roof.project_id)
        project = roof._ensure_project()
        if roof.state != "done":
            roof.with_context(tectora_sync=True).write({"state": "confirmed"})
        if project and not had_project:
            project.message_post(
                body=_(
                    "Project aangemaakt bij bevestiging van %(order)s "
                    "(dakproject %(roof)s).",
                    order=self._get_html_link(),
                    roof=roof._get_html_link(),
                )
            )
        self._tectora_generate_materials()
        self._tectora_sync_execution_task()

    # -------------------------------------------------------- execution task
    def _tectora_execution_project(self):
        self.ensure_one()
        return self.roof_project_id.project_id or self.project_id

    def _tectora_sync_execution_task(self):
        """Put the order's estimated time on the project's tasks
        "Afbraakwerken" and "Uitvoeringswerken", one per work kind, so hours
        are logged apart: created on confirmation, their allocated time
        follows the estimate whenever the order changes afterwards. Only the
        allocated time is touched on an existing task; the rest belongs to
        whoever plans the work.
        """
        for order in self:
            if order.state != "sale":
                continue
            project = order._tectora_execution_project()
            if not project:
                continue
            hours_by_kind = order._tectora_hours_by_kind()
            deadline = order.commitment_date or order.roof_project_id.planned_date_end
            for kind, _label in WORK_KINDS:
                hours = hours_by_kind[kind]
                task = project._tectora_work_task(kind)
                if task:
                    if float_compare(task.allocated_hours, hours, precision_digits=2):
                        task.write({"allocated_hours": hours})
                    continue
                if not hours:
                    continue  # nothing estimated for this kind: no task to size
                project._tectora_work_task(
                    kind,
                    create=True,
                    allocated_hours=hours,
                    date_deadline=deadline or False,
                    description=order._tectora_execution_task_description(kind),
                )

    def _tectora_execution_task_description(self, kind):
        """The estimate per works item of one work kind, so the task says
        where its time comes from."""
        self.ensure_one()
        rows = []
        lines = self.order_line.filtered(
            lambda line: not line.display_type and line._tectora_hours_of_kind(kind)
        )
        for line in lines.sorted(key=lambda line: -line._tectora_hours_of_kind(kind)):
            rows.append(
                "<tr><td>%s</td><td class='text-end'>%s %s</td>"
                "<td class='text-end'>%s u</td><td class='text-end'>%s u</td></tr>"
                % (
                    html_escape(line.product_id.display_name),
                    ("%.2f" % line.product_uom_qty).rstrip("0").rstrip("."),
                    html_escape(line.product_uom_id.name or ""),
                    ("%.3f" % line._tectora_norm_of_kind(kind)).rstrip("0").rstrip("."),
                    "%.2f" % line._tectora_hours_of_kind(kind),
                )
            )
        total = sum(line._tectora_hours_of_kind(kind) for line in lines)
        return (
            "<p>%s</p><table class='table table-sm'><thead><tr><th>%s</th>"
            "<th class='text-end'>%s</th><th class='text-end'>%s</th>"
            "<th class='text-end'>%s</th></tr></thead><tbody>%s</tbody></table>"
            % (
                _("%(kind)s, geschat uit %(order)s: %(hours)s.",
                  kind=dict(WORK_KINDS)[kind], order=self.name,
                  hours=self._tectora_hours_label(total)),
                _("Werkpost"), _("Hoeveelheid"), _("Per eenheid"), _("Uren"),
                "".join(rows),
            )
        )

    # -------------------------------------------------- roof project pairing
    def _tectora_roof_project_values(self):
        """Values of the roof project that stands against this order."""
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
        values.update(self._tectora_roof_values_from_order())
        return values

    def _tectora_free_roof_project(self):
        """A roof project that is waiting for this order: the opportunity's
        roof project (made with "Dakproject maken" on the lead) that has no
        open order yet. None when there is no such project."""
        self.ensure_one()
        if not self.opportunity_id:
            return None
        candidates = self.opportunity_id.roof_project_ids.filtered(
            lambda roof: roof.company_id == self.company_id
            and roof.state != "done"
            and not roof.sale_order_ids.filtered(lambda o: o.state != "cancel")
        )
        return candidates.sorted("id")[:1] or None

    def _tectora_create_roof_project(self, raise_if_failed=False):
        """Every order gets its own roof project: the one its opportunity
        prepared, or a new one made from the order.

        Called from create() and confirmation the failure is logged and the
        order goes on without a roof project; called from a button
        (``raise_if_failed``) the real error reaches the user.
        """
        Roof = self.env["tectora.roof.project"].with_context(tectora_sync=True)
        for order in self:
            try:
                with self.env.cr.savepoint():
                    roof = order._tectora_free_roof_project()
                    if roof:
                        order.with_context(tectora_sync=True).write(
                            {"roof_project_id": roof.id}
                        )
                        order._tectora_sync_pair(roof, master="roof")
                        if roof.state in ("draft", "measured"):
                            roof.write({"state": "quoted"})
                        roof.message_post(
                            body=_(
                                "Offerte %s gekoppeld aan dit dakproject.",
                                order._get_html_link(),
                            )
                        )
                        order._tectora_mirror_lines(roof)
                        continue
                    roof = Roof.create(order._tectora_roof_project_values())
                    order.with_context(tectora_sync=True).write(
                        {"roof_project_id": roof.id}
                    )
                    roof.message_post(
                        body=_(
                            "Dakproject aangemaakt vanuit %s.",
                            order._get_html_link(),
                        )
                    )
                    order._tectora_mirror_lines(roof)
            except Exception:
                if raise_if_failed:
                    raise
                _logger.exception(
                    "Could not create the roof project of order %s", order.name
                )
        return self.roof_project_id

    def _tectora_adopt_roof_project(self, roof):
        """This order was pointed at ``roof``: any other open order of that
        roof project is let go (one roof project, one order) and the two
        records are aligned, the order being the side the user just edited."""
        self.ensure_one()
        others = roof.sale_order_ids.filtered(
            lambda other: other != self and other.state != "cancel"
        )
        if others:
            others.with_context(tectora_sync=True).write({"roof_project_id": False})
        self._tectora_sync_pair(roof, master="order")
        self._tectora_mirror_lines(roof)

    # ------------------------------------------------------- line mirroring
    def _tectora_mirror_lines(self, roof=None):
        """Align the lines of this quotation and its roof project: the order's
        own lines become chapter lines of the roof project, then the roof
        project (quantities from the drawing, measurement lines) is written
        back onto the quotation."""
        self.ensure_one()
        roof = roof or self.roof_project_id
        if not roof or self.state not in ("draft", "sent"):
            return
        self._tectora_mirror_to_roof()
        roof._tectora_mirror_to_order(self)

    def _tectora_mirror_to_roof(self, lines=None):
        """Order lines -> roof project.

        A product line without a roof counterpart becomes a project-level
        (chapter) line of the roof project, measured by its unit (m² ->
        surface, m -> edges, else counted) and starting with the quantity of
        the order; the drawing takes over the measured ones as soon as it
        changes.

        ``lines`` given means the user just edited those order lines: their
        quantity is pushed onto the roof line whatever its coverage, the way a
        quantity typed on the roof project is pushed onto the order. Without
        ``lines`` (aligning a whole order) counted lines follow the order and
        measured lines follow the roof project, so the order quantity is put
        back.
        """
        self.ensure_one()
        roof = self.roof_project_id
        if not roof or self.state not in ("draft", "sent"):
            return
        order_is_master = lines is not None
        RoofLine = self.env["tectora.roof.section.product"].with_context(
            tectora_sync=True
        )
        candidates = (lines if lines is not None else self.order_line)
        candidates = candidates._tectora_mirrorable().filtered(
            lambda line: line.order_id == self
        )
        # Keyed on (product, roof): every roof has its own chapter lines.
        direct_by_product = {}
        for roof_line in roof.direct_line_ids:
            direct_by_product.setdefault((roof_line.product_id, roof_line.roof_id), roof_line)
        for line in candidates:
            roof_line = line.roof_line_id
            if roof_line and roof_line.project_id != roof:
                roof_line = self.env["tectora.roof.section.product"]
            line_roof = line.tectora_roof_id.filtered(lambda r: r.project_id == roof)
            if not roof_line:
                if line.product_id in roof._tectora_measured_products(line_roof):
                    # The drawing already prices this product; a manually
                    # added line is left to the user.
                    continue
                roof_line = direct_by_product.get((line.product_id, line_roof))
                if roof_line and roof_line.sale_line_ids.filtered(
                    lambda sol: sol.order_id == self and sol != line
                ):
                    roof_line = self.env["tectora.roof.section.product"]
                if not roof_line:
                    coverage = RoofLine._coverage_from_product(line.product_id)
                    # The order's quantity is kept, also on a measured line:
                    # without it a roof project without drawing would zero
                    # the line. The drawing overrides it when it changes.
                    roof_line = RoofLine.create({
                        "project_direct_id": roof.id,
                        "roof_id": line_roof.id or False,
                        "product_id": line.product_id.id,
                        "coverage": coverage,
                        "quantity": line.product_uom_qty,
                    })
                    direct_by_product[(line.product_id, line_roof)] = roof_line
                line.with_context(tectora_sync=True).write(
                    {"roof_line_id": roof_line.id}
                )
            elif roof_line.product_id != line.product_id:
                roof_line.with_context(tectora_sync=True).write(
                    {
                        "product_id": line.product_id.id,
                        "coverage": RoofLine._coverage_from_product(line.product_id),
                    }
                )
            # Quantities: an edited order line wins; otherwise counted chapter
            # lines follow the order and measured lines the roof project.
            if order_is_master or (
                roof_line.project_direct_id and roof_line.coverage == "general"
            ):
                if roof_line._quantity_differs(line.product_uom_qty):
                    roof_line.with_context(tectora_sync=True).write(
                        {"quantity": line.product_uom_qty}
                    )
            elif roof_line._quantity_differs(line.product_uom_qty):
                line.with_context(tectora_sync=True).write(
                    {"product_uom_qty": roof_line.quantity}
                )
        return True

    # ----------------------------------------------------------------- roofs
    # The fixed sections of a quotation in which every roof gets a subsection.
    ROOF_CHAPTERS = (("afbouw", ("afbouw", "afbraak")), ("opbouw", ("opbouw",)))

    @api.onchange("sale_order_template_id")
    def _onchange_tectora_template_project_type(self):
        """The template says renovatie or nieuwbouw: the order takes the
        pricelist of that type, which the roof project follows."""
        kind = self.sale_order_template_id.tectora_project_type
        if not kind:
            return
        label = dict(self.env["sale.order.template"]._fields["tectora_project_type"].selection)[kind]
        pricelist = self.env["product.pricelist"].search(
            [("name", "=ilike", label), ("company_id", "in", [False, self.company_id.id])],
            limit=1,
        )
        if pricelist and pricelist != self.pricelist_id:
            self.pricelist_id = pricelist

    def _tectora_check_roofs_allowed(self):
        self.ensure_one()
        if not self.sale_order_template_id:
            raise UserError(_("Kies eerst een offertesjabloon; daarna kunnen de daken toegevoegd worden."))
        if self.state not in ("draft", "sent"):
            raise UserError(_("Daken worden toegevoegd op een offerte, niet op een bevestigde order."))

    def action_tectora_add_roofs(self):
        self.ensure_one()
        self._tectora_check_roofs_allowed()
        return {
            "type": "ir.actions.act_window",
            "name": _("Daken toevoegen"),
            "res_model": "tectora.add.roofs.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id, "default_roof_count": 1},
        }

    def _tectora_roof_chapter_header(self, lines, keywords):
        return lines.filtered(
            lambda line: line.display_type == "line_section"
            and not line.roof_measurement_line
            and any(word in (line.name or "").lower() for word in keywords)
        )[:1]

    def _tectora_add_roof_subsections(self, roofs):
        """Every roof gets the works of the afbouw- and opbouwwerken: the
        template's lines go to the first roofs, every next roof gets the same
        lines as the first. The roof project gets them as lines of that roof,
        whose quantities follow the roof's plan once it is drawn; the
        quotation is laid out per roof (Afbouwwerken and Opbouwwerken thv
        each roof)."""
        self.ensure_one()
        Line = self.env["sale.order.line"]
        ordered = list(self.order_line.sorted(lambda l: (l.sequence, l.id)))
        for _kind, keywords in self.ROOF_CHAPTERS:
            lines = Line.union(*ordered) if ordered else Line
            header = self._tectora_roof_chapter_header(lines, keywords)
            if not header:
                continue
            start = ordered.index(header)
            end = start + 1
            while end < len(ordered) and ordered[end].display_type != "line_section":
                end += 1
            block = ordered[start + 1:end]
            pattern = [
                line for line in block
                if not line.display_type and line.product_id
                and not line.tectora_roof_id and not line.roof_measurement_line
            ]
            if not pattern:
                # Laid out per roof before: a new roof gets the lines of the
                # first roof.
                first_roof = next((l.tectora_roof_id for l in block if l.tectora_roof_id), None)
                if first_roof:
                    pattern = [
                        line for line in block
                        if not line.display_type and not line.roof_measurement_line
                        and line.tectora_roof_id == first_roof
                    ]
            values = []
            for roof in roofs:
                for line in pattern:
                    values.append({
                        "order_id": self.id,
                        "product_id": line.product_id.id,
                        "name": line.name,
                        "product_uom_qty": line.product_uom_qty,
                        "product_uom_id": line.product_uom_id.id,
                        "price_unit": line.price_unit,
                        "discount": line.discount,
                        "tectora_roof_id": roof.id,
                        "sequence": header.sequence,
                    })
            Line.create(values)
            loose = [line for line in pattern if not line.tectora_roof_id]
            if loose:
                ordered = [line for line in ordered if line not in loose]
                Line.union(*loose).unlink()
            ordered = list(self.order_line.sorted(lambda l: (l.sequence, l.id)))
        self._tectora_restructure()
        if self.roof_project_id:
            self.roof_project_id._tectora_mirror_to_order(self)
        return True

    # ------------------------------------------------------------ segments
    def _tectora_header_context(self, line, chapter_kind):
        """(kind, roof) a header opens, or (None, roof) for a header of the
        user's own (kept as it is, with its lines)."""
        project = self.roof_project_id
        Roof = self.env["tectora.roof.project.roof"]
        if getattr(line, "is_optional", False):
            return None, Roof
        if line.tectora_segment:
            return line.tectora_segment.split(":")[0], line.tectora_roof_id
        kind = project._tectora_segment_kind(line.name)
        if line.tectora_roof_id:
            # A roof's subsection under a chapter header.
            return kind or chapter_kind, line.tectora_roof_id
        if kind == "other":
            return None, Roof  # a header of the user's own: kept
        return kind, Roof

    def _tectora_restructure(self):
        """Lay the quotation out in its standard segments: Algemene werken,
        Veiligheid, per roof Afbouwwerken and Opbouwwerken thv that roof, the
        other chapters, the headers of the user's own (with their lines),
        Algemene nota's.

        A line goes to the segment of its product's chapter (and its roof);
        a line whose product has no chapter stays in the segment of the
        header it was under. Notes stay with the line they follow. Lines keep
        their order within a segment. The segment headers are made (or
        renamed) by this; the chapter headers and roof subsections of the
        old layout are dropped.
        """
        for order in self:
            project = order.roof_project_id
            if not project or order.state not in ("draft", "sent"):
                continue
            Line = self.env["sale.order.line"].with_context(tectora_sync=True)
            Roof = self.env["tectora.roof.project.roof"]
            Category = self.env["product.category"]
            roofs = project.roof_ids
            segments = {}
            dropped = []

            def segment(key, kind, roof=Roof, chapter=Category, position=0):
                if key not in segments:
                    segments[key] = {
                        "kind": kind, "roof": roof, "chapter": chapter,
                        "header": None, "items": [], "position": position,
                    }
                return segments[key]

            context_kind, context_roof, context_key = None, Roof, None
            last_item = None
            for position, line in enumerate(order.order_line.sorted(lambda l: (l.sequence, l.id))):
                if line.display_type in ("line_section", "line_subsection"):
                    last_item = None
                    if line.roof_measurement_line:
                        dropped.append(line)  # a header of the old measurement blocks
                        continue
                    kind, roof = order._tectora_header_context(line, context_kind)
                    if not kind:
                        context_kind, context_roof = None, Roof
                        context_key = "custom:%s" % line.id
                        segment(context_key, "custom", position=position)["header"] = line
                        continue
                    context_kind, context_roof, context_key = kind, roof, None
                    if kind in ("demolition", "buildup") and not roof and len(roofs) == 1:
                        roof = roofs
                    key = project._tectora_segment_key(kind, roof)
                    target = segment(key, kind, roof)
                    if target["header"] is None and line.display_type == "line_section":
                        target["header"] = line
                    else:
                        dropped.append(line)
                    continue
                if line.display_type == "line_note" and line.tectora_segment == "notes":
                    segment("notes", "notes")["items"].append([line])
                    continue
                if line.display_type:
                    if last_item is not None:
                        last_item.append(line)
                        continue
                    item = [line]
                    if context_key:
                        segments[context_key]["items"].append(item)
                    else:
                        key = project._tectora_segment_key(context_kind or "other", context_roof)
                        segment(key, context_kind or "other", context_roof)["items"].append(item)
                    last_item = item
                    continue
                # A product line.
                item = [line]
                last_item = item
                if context_key and not line.roof_line_id and not line.roof_measurement_line:
                    segments[context_key]["items"].append(item)
                    continue
                kind, chapter = project._tectora_product_segment(line.product_id)
                kind = kind or context_kind or "other"
                roof = line.tectora_roof_id or line.roof_line_id.roof_id
                if kind in ("demolition", "buildup"):
                    roof = roof or context_roof
                    if not roof and len(roofs) == 1:
                        roof = roofs
                else:
                    roof = Roof
                key = project._tectora_segment_key(kind, roof, chapter)
                segment(key, kind, roof, chapter)["items"].append(item)

            ranked = sorted(segments.items(), key=lambda kv: project._tectora_segment_rank(
                kv[1]["kind"], kv[1]["roof"], kv[1]["chapter"], kv[1]["position"]
            ))
            final = []
            for key, data in ranked:
                header = data["header"]
                if data["kind"] == "custom":
                    final.append(header)
                elif data["items"]:
                    title = project._tectora_segment_title(data["kind"], data["roof"], data["chapter"])
                    values = {
                        "display_type": "line_section",
                        "name": title,
                        "tectora_segment": key,
                        "tectora_roof_id": data["roof"].id or False,
                    }
                    if header:
                        changed = {
                            field: value for field, value in values.items()
                            if (header[field].id if field == "tectora_roof_id" else header[field]) != value
                        }
                        if changed:
                            header.with_context(tectora_sync=True).write(changed)
                    else:
                        header = Line.create(dict(values, order_id=order.id))
                    final.append(header)
                elif header:
                    dropped.append(header)
                    continue
                for item in data["items"]:
                    final.extend(item)
            leftovers = [line for line in dropped if line not in final]
            if leftovers:
                Line.union(*leftovers).unlink()
            for index, line in enumerate(final, start=1):
                if line.sequence != index * 10:
                    line.with_context(tectora_sync=True).write({"sequence": index * 10})
        return True

    # --------------------------------------------------------- field mirror
    @api.model
    def _tectora_roof_to_order_fields(self):
        return [roof_field for _order, roof_field in SYNC_PAIRS]

    def _tectora_sync_pair(self, roof, master="order", changed=None):
        """Keep this order and ``roof`` equal on the shared fields.

        ``master`` names the side that was edited: its values win, and when
        it explicitly changed a field (``changed`` given) even an emptied value
        is mirrored. Without ``changed`` the pair is being linked: the master
        pushes what it has and the other side fills in what the master left
        empty.
        """
        self.ensure_one()
        roof.ensure_one()
        if master == "order":
            roof_vals = self._tectora_roof_values_from_order(changed, roof=roof)
            order_vals = (
                {} if changed is not None
                else self._tectora_order_values_from_roof(roof, only_missing=True)
            )
        else:
            order_vals = self._tectora_order_values_from_roof(roof, changed)
            roof_vals = (
                {} if changed is not None
                else self._tectora_roof_values_from_order(only_missing=True, roof=roof)
            )
        roof_vals = {
            key: value for key, value in roof_vals.items()
            if _differs(roof, key, value)
        }
        order_vals = {
            key: value for key, value in order_vals.items()
            if _differs(self, key, value)
        }
        if roof_vals:
            roof.with_context(tectora_sync=True).write(roof_vals)
        if order_vals:
            self.with_context(tectora_sync=True).write(order_vals)
        return True

    def _tectora_roof_values_from_order(self, changed=None, only_missing=False, roof=None):
        """Roof project values mirroring this order.

        ``changed``: only the pairs whose order field is in it (None = all);
        ``only_missing``: only for roof fields that are empty on ``roof``.
        """
        self.ensure_one()
        roof = roof if roof is not None else self.roof_project_id
        explicit = changed is not None
        values = {}

        def wanted(order_field, roof_field):
            if explicit and order_field not in changed:
                return False
            if only_missing and roof and roof[roof_field]:
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
            project_type = self._tectora_project_type_from_pricelist()
            if project_type:
                values["project_type"] = project_type
        # Another customer gets its own delivery address (Odoo recomputes it
        # without it being written), so the site follows that too.
        site_changed = explicit and "partner_id" in changed and not only_missing
        if (wanted("partner_shipping_id", "site_partner_id") or site_changed) \
                and self.partner_shipping_id:
            values["site_partner_id"] = self.partner_shipping_id.id
        return values

    def _tectora_order_values_from_roof(self, roof, changed=None, only_missing=False):
        """Order values mirroring ``roof``; see _tectora_roof_values_from_order.
        Commercial fields are only produced while the order is a quotation."""
        self.ensure_one()
        explicit = changed is not None
        quotation = self.state in ("draft", "sent")
        values = {}

        def wanted(order_field, roof_field):
            if explicit and roof_field not in changed:
                return False
            if only_missing and self[order_field]:
                return False
            if order_field in QUOTATION_ONLY and not quotation:
                return False
            return True

        if wanted("partner_id", "partner_id") and roof.partner_id:
            values["partner_id"] = roof.partner_id.id
        if wanted("opportunity_id", "opportunity_id") and (
            roof.opportunity_id or explicit
        ):
            values["opportunity_id"] = roof.opportunity_id.id or False
        if wanted("user_id", "project_manager_id") and roof.project_manager_id:
            values["user_id"] = roof.project_manager_id.id
        if wanted("commitment_date", "date_deadline") and (
            roof.date_deadline or explicit
        ):
            values["commitment_date"] = self._tectora_deadline_to_datetime(
                roof.date_deadline
            )
        if wanted("pricelist_id", "project_type") and roof.project_type:
            pricelist = roof._find_pricelist()
            if pricelist:
                values["pricelist_id"] = pricelist.id
        if wanted("partner_shipping_id", "site_partner_id") and roof.site_partner_id:
            values["partner_shipping_id"] = roof.site_partner_id.id
        return values

    def _tectora_project_type_from_pricelist(self):
        """Project type whose label the pricelist name carries, or None."""
        self.ensure_one()
        name = (self.pricelist_id.name or "").lower()
        selection = self.env["tectora.roof.project"]._fields["project_type"].selection
        for key, label in selection:
            if label.lower() in name:
                return key
        return None

    def _tectora_deadline_to_datetime(self, deadline):
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
    def action_apply_tectora_tax(self):
        """Put the chosen tax on every product line. Deliberately a button,
        not an automatism: the user decides when the whole order switches."""
        for order in self:
            lines = order.order_line.filtered(lambda line: not line.display_type)
            if not lines:
                continue
            if order.tectora_tax_id:
                lines.with_context(tectora_sync=True).write(
                    {"tax_ids": [(6, 0, order.tectora_tax_id.ids)]}
                )
            else:
                # No tax chosen: back to the taxes of the products and the
                # fiscal position.
                lines.with_context(tectora_sync=True)._compute_tax_ids()
        return True

    # ---------------------------------------------------------------- report
    def _tectora_report_sections(self, optional=False):
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
                    "measurement": bool(line.roof_measurement_line),
                    "optional": bool(getattr(line, "is_optional", False)),
                }
                continue
            current["lines"].append(line)
            if not line.display_type:
                current["subtotal"] += line.price_subtotal
        if current["lines"] or current["name"]:
            sections.append(current)
        return [section for section in sections if section["optional"] == optional]

    def _tectora_report_tax_label(self, line):
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
        after_index = self.env.context.get("tectora_catalog_after_index")
        if isinstance(after_index, int) and after_index >= 0:
            # Resolved to the line that follows now (the order was just saved),
            # so it keeps pointing at the same place while lines are added.
            lines = self._tectora_ordered_lines()
            if after_index + 1 < len(lines):
                context["tectora_catalog_before_line_id"] = lines[after_index + 1].id
        return context

    def _update_order_line_info(self, product, quantity, uom, child_field, **kwargs):
        # Sent by the catalog (catalog_insert_position.js). Taken out of
        # kwargs, which are passed on to the price computation.
        before_line_id = kwargs.pop("tectora_before_line_id", False)
        if before_line_id:
            self = self.with_context(tectora_catalog_before_line_id=before_line_id)
        return super()._update_order_line_info(product, quantity, uom, child_field, **kwargs)

    def _catalog_prepare_new_line_vals(self, child_field, product, quantity, uom, **kwargs):
        vals = super()._catalog_prepare_new_line_vals(
            child_field, product, quantity, uom, **kwargs
        )
        before_line_id = self.env.context.get("tectora_catalog_before_line_id")
        if child_field == "order_line" and before_line_id:
            lines = self._tectora_ordered_lines()
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

    def _tectora_ordered_lines(self):
        """The order lines in the order the quotation shows them."""
        return self.order_line.sorted(lambda line: (line.sequence, line.id))

    # ---------------------------------------------------------- smart buttons
    def action_view_roof_project(self):
        """The roof project of this order (created on the spot if the order
        was made without one)."""
        self.ensure_one()
        if not self.roof_project_id:
            self._tectora_create_roof_project(raise_if_failed=True)
        if not self.roof_project_id:
            raise UserError(
                _(
                    "Het dakproject kon niet aangemaakt worden; kijk in de "
                    "serverlog voor de oorzaak."
                )
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "tectora.roof.project",
            "res_id": self.roof_project_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_project_dashboard(self):
        """The project dashboard of this order; a confirmed order without a
        project yet gets one first."""
        self.ensure_one()
        project = self.project_id
        if not project and self.roof_project_id:
            project = self.roof_project_id.project_id
        if not project:
            if self.state not in ("sale", "done"):
                raise UserError(
                    _(
                        "Het project wordt aangemaakt bij het bevestigen van de "
                        "order. Bevestig eerst de offerte."
                    )
                )
            if not self.roof_project_id:
                self._tectora_create_roof_project(raise_if_failed=True)
            project = self.roof_project_id._ensure_project()
        return project.action_open_dashboard()

    # ---------------------------------------------------------- material list
    def _tectora_material_values(self, line, product, quantity, uom, bom_name):
        return {
            "project_id": self.roof_project_id.id,
            "product_id": product.id,
            "product_uom_id": (uom or product.uom_id).id,
            "quantity": quantity,
            "source_product_id": line.product_id.id,
            "bom_name": bom_name or False,
            "sale_order_id": self.id,
            "sale_order_line_id": line.id,
        }

    def _tectora_find_boms(self, products):
        """First bill of materials per product, ordered as Odoo orders them.

        Deliberately not ``mrp.bom._bom_find``: that drops service products,
        and the works items Tectora sells (``DAK-*``) are services, so it would
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

    def _tectora_line_material_values(self, line, bom):
        """Material requirement values of one order line, exploded from
        ``bom`` (its product's bill of materials, or None).

        A product without one is itself the material if it is goods; a
        service without one is labour and contributes nothing. Extension
        point: a line can bring its own components (tectora_sale_bom).
        """
        quantity = line.product_uom_qty
        if not bom:
            if line.product_id.type == "service":
                return []  # works item with no bill of materials: labour
            return [
                self._tectora_material_values(
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
            self._tectora_component_values(
                line,
                bom_line.product_id,
                self._tectora_exploded_quantity(bom, factor, bom_line, line_data),
                bom_line.uom_id,
                bom.display_name,
            )
            for bom_line, line_data in lines_done
        ]

    def _tectora_component_values(self, line, product, quantity, uom, bom_name, margin=None):
        """Material values of a component of a bill of materials. A component
        with hercalculatie is counted in m² or m³ on the bill of materials
        and needed in pieces: ``quantity`` is turned into pieces of the
        product's own unit, with the product's safety margin or ``margin``
        (in %, a bill of materials line's own). Not rounded yet: the pieces
        are rounded up once per product, when the lines of the order are
        added up (_tectora_merge_material_values)."""
        if product.tectora_recalc:
            quantity = product.product_tmpl_id._tectora_recalc_pieces(quantity, margin)
            values = self._tectora_material_values(line, product, quantity, product.uom_id, bom_name)
            # Pieces, to be rounded up on the product's total.
            values[ROUND_PIECES] = True
            return values
        return self._tectora_material_values(line, product, quantity, uom, bom_name)

    def _tectora_exploded_quantity(self, bom, factor, bom_line, line_data):
        """Quantity of one exploded component; ``factor`` is how many times
        ``bom`` is needed. Extension point for components whose quantity does
        not follow the order line (tectora_sale_bom)."""
        return line_data["qty"]

    def _tectora_merge_material_values(self, values):
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
                vals["quantity"] = product.product_tmpl_id._tectora_round_pieces(vals["quantity"])
            if float_is_zero(vals["quantity"], precision_digits=6):
                continue
            result.append(vals)
        return result

    def _tectora_generate_materials(self):
        """Explode every sold product into material requirements.

        Products with a bill of materials contribute their components (nested
        phantom BoMs included, as ``explode`` resolves those). A product
        without one is itself the material if it is goods; a service without
        one is labour and contributes nothing. Lines generated by an earlier
        confirmation of this order are replaced.
        """
        self.ensure_one()
        Material = self.env["tectora.roof.material"]
        Material.search([("sale_order_id", "=", self.id)]).unlink()

        lines = self.order_line.filtered(
            lambda line: not line.display_type and line.product_id
        )
        if not lines:
            return Material

        boms = self._tectora_find_boms(lines.product_id)

        values = []
        for line in lines:
            values += self._tectora_line_material_values(line, boms.get(line.product_id))
        values = self._tectora_merge_material_values(values)
        materials = Material.create(values) if values else Material
        if materials:
            self.roof_project_id.message_post(
                body=_(
                    "Materiaallijst bijgewerkt uit %(order)s: %(count)s "
                    "materiaallijn(en).",
                    order=self.name,
                    count=len(materials),
                )
            )
        return materials
