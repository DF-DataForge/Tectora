# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from .order_list_template import ORDER_ACTIONS


class TectoraProjectOrderLine(models.Model):
    """One part of a project's order list: tick it off, choose the supplier,
    follow the order and delivery dates, and order it in one click."""

    _name = "tectora.project.order.line"
    _description = "Bestellijst: regel per project"
    _order = "project_id, sequence, id"

    sequence = fields.Integer(default=10)
    project_id = fields.Many2one(
        "project.project", string="Project", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="project_id.company_id", store=True)
    template_id = fields.Many2one(
        "tectora.order.list.template", string="Standaardonderdeel", ondelete="set null"
    )
    name = fields.Char(string="Onderdeel", required=True)
    order_action = fields.Selection(ORDER_ACTIONS, string="Actie", required=True, default="order")
    checked = fields.Boolean(string="Afgevinkt")
    supplier_note = fields.Text(string="Leveranciers (bestellijst)")
    allowed_partner_ids = fields.Many2many(
        related="template_id.partner_ids", string="Voorgestelde leveranciers"
    )
    partner_id = fields.Many2one(
        "res.partner", string="Leverancier", domain=[("parent_id", "=", False)]
    )
    order_date = fields.Date(string="Besteldatum")
    expected_date = fields.Date(string="Verwachte leverdatum")
    note = fields.Char(string="Opmerking")
    product_line_ids = fields.One2many(
        "tectora.project.order.product", "order_line_id", string="Producten"
    )
    purchase_order_ids = fields.One2many(
        "purchase.order", "tectora_order_line_id", string="Inkooporders"
    )
    purchase_count = fields.Integer(compute="_compute_status", string="# Inkooporders")
    status = fields.Selection(
        [
            ("todo", "Te bestellen"),
            ("stock", "Uit stock"),
            ("rfq", "Prijsaanvraag"),
            ("ordered", "Besteld"),
            ("received", "Ontvangen"),
            ("done", "Afgevinkt"),
        ],
        string="Status",
        compute="_compute_status",
    )
    is_late = fields.Boolean(compute="_compute_status", string="Te laat")

    @api.depends(
        "checked", "order_action", "expected_date", "purchase_order_ids.state",
        "purchase_order_ids.receipt_status", "product_line_ids.shortage_qty",
    )
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for line in self:
            orders = line.purchase_order_ids.filtered(lambda po: po.state != "cancel")
            line.purchase_count = len(orders)
            confirmed = orders.filtered(lambda po: po.state == "purchase")
            if line.checked:
                status = "done"
            elif confirmed and all(po.receipt_status == "full" for po in confirmed):
                status = "received"
            elif confirmed:
                status = "ordered"
            elif orders:
                status = "rfq"
            elif (
                line.order_action == "stock_first" and line.product_line_ids
                and not any(line.product_line_ids.mapped("shortage_qty"))
            ):
                status = "stock"
            else:
                status = "todo"
            line.status = status
            line.is_late = bool(
                line.expected_date and line.expected_date < today
                and status in ("todo", "rfq", "ordered")
            )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.project_id._tectora_sync_order_list_task()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if "checked" in vals:
            self.project_id._tectora_sync_order_list_task()
        return res

    def unlink(self):
        projects = self.project_id
        res = super().unlink()
        projects.exists()._tectora_sync_order_list_task()
        return res

    def _tectora_purchase_line_values(self, product_lines=None):
        """Purchase lines for the given product lines (all of them by
        default): everything for "Bestellen", only the shortage for
        "Stock eerst"."""
        self.ensure_one()
        if product_lines is None:
            product_lines = self.product_line_ids
        values = []
        for product_line in product_lines:
            qty = (
                product_line.shortage_qty if self.order_action == "stock_first"
                else product_line.quantity
            )
            if qty <= 0:
                continue
            values.append(fields.Command.create({
                "product_id": product_line.product_id.id,
                "product_qty": qty,
                "uom_id": product_line.uom_id.id,
            }))
        return values

    def _tectora_supplier_infos(self):
        """The supplier prices (Purchase tab of the products) of the part's
        supplier; without a chosen supplier, those of the suggested ones."""
        self.ensure_one()
        partners = self.partner_id or self.allowed_partner_ids
        if not partners:
            return self.env["product.supplierinfo"]
        return self.env["product.supplierinfo"].search([
            ("partner_id", "child_of", partners.commercial_partner_id.ids),
            ("company_id", "in", [False, self.company_id.id or self.env.company.id]),
        ])

    def tectora_get_supplier_products(self):
        """The product list of the order list page: the products the
        supplier delivers and those already on the part; the latter come
        first, selected, with their quantity."""
        self.ensure_one()
        existing = {pl.product_id: pl for pl in self.product_line_ids}
        codes = {}
        products = self.env["product.product"]
        for info in self._tectora_supplier_infos():
            variants = info.product_id or info.product_tmpl_id.product_variant_ids
            for product in variants.filtered("purchase_ok"):
                products |= product
                if info.product_code:
                    codes.setdefault(product.id, info.product_code)
        products |= self.product_line_ids.product_id
        company = self.company_id or self.env.company
        result = []
        for product in products.sorted(lambda p: (p not in existing, p.display_name or "")):
            product_line = existing.get(product)
            result.append({
                "id": product.id,
                "name": product.display_name,
                "code": codes.get(product.id, ""),
                "uom": (product_line.uom_id if product_line else product.uom_id).name or "",
                "quantity": product_line.quantity if product_line else 1.0,
                "selected": bool(product_line),
                "free_qty": (
                    product.with_company(company).free_qty if product.is_storable else False
                ),
            })
        return result

    def _tectora_set_products(self, products):
        """Puts the selected products on the part, with their quantity, and
        returns their product lines. Other products on the part stay."""
        self.ensure_one()
        ProductLine = self.env["tectora.project.order.product"]
        selected = ProductLine
        for item in products:
            product = self.env["product.product"].browse(int(item["product_id"])).exists()
            if not product:
                continue
            quantity = float(item.get("quantity") or 0.0)
            if quantity <= 0:
                raise UserError(self.env._(
                    "Geef een hoeveelheid groter dan nul voor '%s'.", product.display_name
                ))
            product_line = self.product_line_ids.filtered(lambda pl: pl.product_id == product)[:1]
            if product_line:
                if product_line.quantity != quantity:
                    product_line.quantity = quantity
            else:
                product_line = ProductLine.create({
                    "order_line_id": self.id,
                    "product_id": product.id,
                    "quantity": quantity,
                })
            selected |= product_line
        return selected

    def action_tectora_create_purchase(self, products=None):
        """A request for quotation for this part, charged to the project.

        ``products`` (from the order list page): the selected products, as
        ``[{"product_id": id, "quantity": qty}]``; they are put on the part
        and the request for quotation holds only them. Without it, all the
        part's products are ordered.
        """
        self.ensure_one()
        if not self.partner_id:
            raise UserError(self.env._("Kies eerst een leverancier voor '%s'.", self.name))
        if products is not None:
            if not products:
                raise UserError(self.env._(
                    "Selecteer eerst de producten om te bestellen voor '%s'.", self.name
                ))
            product_lines = self._tectora_set_products(products)
        else:
            product_lines = self.product_line_ids
        line_values = self._tectora_purchase_line_values(product_lines)
        if product_lines and not line_values:
            raise UserError(self.env._(
                "Alles voor '%s' is op voorraad: er moet niets besteld worden.", self.name
            ))
        order = self.env["purchase.order"].create({
            "partner_id": self.partner_id.id,
            "origin": f"{self.project_id.name} · {self.name}",
            "project_id": self.project_id.id,
            "tectora_order_line_id": self.id,
            "order_line": line_values,
        })
        self.write({
            "order_date": self.order_date or fields.Date.context_today(self),
            "expected_date": self.expected_date or (
                order.date_planned and order.date_planned.date()
            ),
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "res_id": order.id,
            "views": [(False, "form")],
            "target": "current",
        }

    def action_tectora_view_purchases(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Inkooporders · %s", self.name),
            "res_model": "purchase.order",
            "views": [(False, "list"), (False, "form")],
            "domain": [("tectora_order_line_id", "=", self.id)],
            "context": {
                "default_tectora_order_line_id": self.id,
                "default_project_id": self.project_id.id,
                "default_partner_id": self.partner_id.id,
            },
        }

    def action_tectora_toggle_checked(self):
        for line in self:
            line.checked = not line.checked
        return True

    def action_tectora_open_form(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self._name,
            "res_id": self.id,
            "views": [(False, "form")],
            "target": "current",
        }


class TectoraProjectOrderProduct(models.Model):
    """A product needed for an order list line; "Stock eerst" orders only
    what the free stock does not cover."""

    _name = "tectora.project.order.product"
    _description = "Bestellijst: benodigd product"

    order_line_id = fields.Many2one(
        "tectora.project.order.line", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="order_line_id.company_id")
    product_id = fields.Many2one(
        "product.product", string="Product", required=True, domain=[("purchase_ok", "=", True)]
    )
    quantity = fields.Float(string="Nodig", digits="Product Unit", default=1.0)
    uom_id = fields.Many2one(
        "uom.uom", string="Eenheid", compute="_compute_uom_id", store=True, readonly=False
    )
    free_qty = fields.Float(string="Vrije voorraad", digits="Product Unit", compute="_compute_stock")
    shortage_qty = fields.Float(string="Tekort", digits="Product Unit", compute="_compute_stock")

    @api.depends("product_id")
    def _compute_uom_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_id

    @api.depends("product_id", "quantity", "uom_id")
    def _compute_stock(self):
        for line in self:
            free = 0.0
            if line.product_id.is_storable:
                free = line.product_id.with_company(line.company_id or self.env.company).free_qty
                if line.uom_id and line.uom_id != line.product_id.uom_id:
                    free = line.product_id.uom_id._compute_quantity(free, line.uom_id)
            line.free_qty = free
            line.shortage_qty = max(line.quantity - max(free, 0.0), 0.0)
