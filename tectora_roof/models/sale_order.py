# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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
    roof_project_state = fields.Selection(
        related="roof_project_id.state", string="Status dakproject", readonly=True
    )
    roof_total_area = fields.Float(
        related="roof_project_id.total_area", string="Dakoppervlakte (m²)"
    )

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
            "address": address._display_address(without_company=True).replace(
                "\n", ", "
            ) if address else False,
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
            bom = boms.get(line.product_id)
            quantity = line.product_uom_qty
            if not bom:
                if line.product_id.type == "service":
                    continue  # works item with no bill of materials: labour
                values.append(
                    self._tectora_material_values(
                        line, line.product_id, quantity, line.product_uom_id, None
                    )
                )
                continue
            # explode() expects how many times the BoM is needed, in the BoM's
            # own unit of measure.
            bom_quantity = quantity
            if line.product_uom_id and bom.product_uom_id != line.product_uom_id:
                bom_quantity = line.product_uom_id._compute_quantity(
                    quantity, bom.product_uom_id
                )
            factor = bom_quantity / (bom.product_qty or 1.0)
            _boms_done, lines_done = bom.explode(line.product_id, factor)
            for bom_line, line_data in lines_done:
                values.append(
                    self._tectora_material_values(
                        line,
                        bom_line.product_id,
                        line_data["qty"],
                        bom_line.product_uom_id,
                        bom.display_name,
                    )
                )
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
