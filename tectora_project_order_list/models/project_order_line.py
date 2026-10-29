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

    def _tectora_material_needs(self):
        """{product: quantity in the product's unit} the project needs
        according to its material list (the materials of its roof projects,
        from the confirmed order)."""
        self.ensure_one()
        needs = {}
        for material in self.project_id.roof_project_ids.material_line_ids:
            product = material.product_id
            quantity = material.quantity
            if material.product_uom_id and material.product_uom_id != product.uom_id:
                quantity = material.product_uom_id._compute_quantity(
                    quantity, product.uom_id, round=False
                )
            needs[product] = needs.get(product, 0.0) + quantity
        return needs

    def tectora_get_supplier_products(self):
        """The product list of the order list page, in three parts:

        * ``items``, still to order (or to deliver from stock): the
          supplier's products on the project's material list, with the
          quantity it needs, and the products on the part that are neither
          ordered nor delivered yet (those first, selected), whatever the
          supplier, so they can go to another one;
        * ``ordered``: per purchase order, the products already in order
          ("Reeds in bestelling bij ..."), with its status;
        * ``stock``: per delivery, the products going from the warehouse to
          the site, with their reservation.
        """
        self.ensure_one()
        to_order = self.product_line_ids.filtered(lambda pl: pl.source == "to_order")
        done_products = (self.product_line_ids - to_order).product_id
        existing = {pl.product_id: pl for pl in to_order}
        needs = self._tectora_material_needs()
        codes = {}
        products = self.env["product.product"]
        for info in self._tectora_supplier_infos():
            variants = info.product_id or info.product_tmpl_id.product_variant_ids
            for product in variants.filtered(
                lambda p: p.purchase_ok and p in needs and p not in done_products
            ):
                products |= product
                if info.product_code:
                    codes.setdefault(product.id, info.product_code)
        products |= to_order.product_id
        items = []
        for product in products.sorted(lambda p: (p not in existing, p.display_name or "")):
            product_line = existing.get(product)
            items.append(dict(
                self._tectora_product_item(product, product_line.uom_id if product_line else False),
                code=codes.get(product.id, ""),
                quantity=(
                    product_line.quantity if product_line
                    else round(needs.get(product, 0.0), 2) or 1.0
                ),
                needed=round(needs[product], 2) if product in needs else False,
                selected=bool(product_line),
            ))
        return {
            "items": items,
            "ordered": self._tectora_ordered_groups(),
            "stock": self._tectora_stock_groups(),
        }

    def _tectora_product_item(self, product, uom=False):
        company = self.company_id or self.env.company
        return {
            "id": product.id,
            "name": product.display_name,
            "code": "",
            "uom": (uom or product.uom_id).name or "",
            "free_qty": (
                round(product.with_company(company).free_qty, 2) if product.is_storable else False
            ),
        }

    def _tectora_ordered_groups(self):
        """The products in order, per purchase order."""
        lines = self.product_line_ids.filtered(lambda pl: pl.source == "ordered")
        states = dict(
            self.env["purchase.order"]._fields["state"]._description_selection(self.env)
        )
        groups = []
        for order in lines.purchase_line_id.order_id.sorted("id"):
            order_lines = lines.filtered(lambda pl: pl.purchase_line_id.order_id == order)
            groups.append({
                "id": order.id,
                "model": "purchase.order",
                "title": self.env._("Reeds in bestelling bij %s", order.partner_id.display_name),
                "reference": order.name,
                "state": states.get(order.state, order.state),
                "tone": "success" if order.state == "purchase" else "warning",
                "lines": [{
                    "id": pl.id,
                    "name": pl.product_id.display_name,
                    "quantity": round(pl.purchase_line_id.product_qty, 2),
                    "uom": pl.purchase_line_id.uom_id.name or pl.uom_id.name or "",
                } for pl in order_lines],
            })
        return groups

    def _tectora_stock_groups(self):
        """The products delivered from the warehouse, per delivery."""
        lines = self.product_line_ids.filtered(lambda pl: pl.source == "stock")
        move_states = {
            "draft": self.env._("Concept"),
            "waiting": self.env._("Wacht op voorraad"),
            "confirmed": self.env._("Wacht op voorraad"),
            "partially_available": self.env._("Deels gereserveerd"),
            "assigned": self.env._("Gereserveerd"),
            "done": self.env._("Geleverd"),
        }
        states = dict(
            self.env["stock.picking"]._fields["state"]._description_selection(self.env)
        )
        groups = []
        for picking in lines.move_id.picking_id.sorted("id"):
            picking_lines = lines.filtered(lambda pl: pl.move_id.picking_id == picking)
            groups.append({
                "id": picking.id,
                "model": "stock.picking",
                "title": self.env._("Leveren vanuit magazijn"),
                "reference": picking.name,
                "state": states.get(picking.state, picking.state),
                "tone": "success" if picking.state in ("assigned", "done") else "warning",
                "lines": [{
                    "id": pl.id,
                    "name": pl.product_id.display_name,
                    "quantity": round(pl.move_id.product_uom_qty, 2),
                    "uom": pl.move_id.uom_id.name or "",
                    "state": move_states.get(pl.move_id.state, pl.move_id.state),
                } for pl in picking_lines],
            })
        return groups

    def tectora_search_extra_products(self, term="", limit=20):
        """Any purchasable product, to add to the part beyond what the
        material list needs (the "+ Ander product" search of the order list
        page); the supplier's own products first."""
        self.ensure_one()
        supplier_products = self.env["product.product"]
        for info in self._tectora_supplier_infos():
            supplier_products |= info.product_id or info.product_tmpl_id.product_variant_ids
        domain = [("purchase_ok", "=", True)]
        if term:
            domain += ["|", "|", ("name", "ilike", term), ("default_code", "ilike", term),
                       ("barcode", "ilike", term)]
        Product = self.env["product.product"]
        found = Product.search(domain + [("id", "in", supplier_products.ids)], limit=limit)
        if len(found) < limit:
            found |= Product.search(
                domain + [("id", "not in", found.ids)], limit=limit - len(found)
            )
        company = self.company_id or self.env.company
        return [{
            "id": product.id,
            "name": product.display_name,
            "code": "",
            "uom": product.uom_id.name or "",
            "quantity": 1.0,
            "selected": True,
            "needed": False,
            "extra": True,
            "from_supplier": product in supplier_products,
            "free_qty": (
                product.with_company(company).free_qty if product.is_storable else False
            ),
        } for product in found]

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
            # Only a line still to order: what is ordered or on a delivery
            # stays as it is, a new need gets a line of its own.
            product_line = self.product_line_ids.filtered(
                lambda pl: pl.product_id == product and pl.source == "to_order"
            )[:1]
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
            product_lines = self.product_line_ids.filtered(lambda pl: pl.source == "to_order")
        line_values = self._tectora_purchase_line_values(product_lines)
        if product_lines and not line_values:
            raise UserError(self.env._(
                "Alles voor '%s' is op voorraad: er moet niets besteld worden.", self.name
            ))
        roof = self.project_id.roof_project_id
        order = self.env["purchase.order"].create({
            "partner_id": self.partner_id.id,
            # The site's reference, for the vendor's confirmation and delivery.
            "partner_ref": roof._tectora_vendor_reference() if roof else self.project_id.name,
            "origin": f"{self.project_id.name} · {self.name}",
            "project_id": self.project_id.id,
            "tectora_order_line_id": self.id,
            "order_line": line_values,
        })
        # The products are in order now: the order list page sets them apart.
        for product_line in product_lines:
            purchase_line = order.order_line.filtered(
                lambda pl: pl.product_id == product_line.product_id
            )[:1]
            if purchase_line:
                product_line.purchase_line_id = purchase_line
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

    def action_tectora_deliver_from_stock(self, products):
        """The selected products go from the warehouse to the site: they are
        put on the project's open outgoing delivery of the order list (a new
        one when there is none), which is confirmed and reserves the stock.

        ``products``: ``[{"product_id": id, "quantity": qty}]``, as for a
        request for quotation.
        """
        self.ensure_one()
        if not products:
            raise UserError(self.env._(
                "Selecteer eerst de producten om uit stock te leveren voor '%s'.", self.name
            ))
        product_lines = self._tectora_set_products(products)
        not_stocked = product_lines.product_id.filtered(lambda p: not p.is_storable)
        if not_stocked:
            raise UserError(self.env._(
                "Enkel producten met voorraad kunnen uit het magazijn komen: %s.",
                ", ".join(not_stocked.mapped("display_name")),
            ))
        picking = self._tectora_stock_picking()
        Move = self.env["stock.move"]
        moves = Move
        for product_line in product_lines:
            move = Move.create({
                "picking_id": picking.id,
                "product_id": product_line.product_id.id,
                "product_uom_qty": product_line.quantity,
                "uom_id": (product_line.uom_id or product_line.product_id.uom_id).id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "company_id": picking.company_id.id,
            })
            product_line.move_id = move
            moves |= move
        # Confirmed, so the warehouse sees it, and reserved from the stock.
        moves._action_confirm()
        moves._action_assign()
        self.project_id.message_post(body=self.env._(
            "%(count)s product(en) van '%(part)s' uit het magazijn op %(picking)s.",
            count=len(moves), part=self.name, picking=picking._get_html_link(),
        ))
        return True

    def _tectora_stock_picking(self):
        """The project's open outgoing delivery of the order list, or a new
        one: from the company's warehouse to the site."""
        self.ensure_one()
        project = self.project_id
        company = self.company_id or self.env.company
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        picking_type = warehouse.out_type_id
        if not picking_type:
            raise UserError(self.env._(
                "Er is geen magazijn met een leveringsbewerking voor %s.", company.name
            ))
        origin = self.env._("%s · Bestellijst", project.name)
        Picking = self.env["stock.picking"]
        picking = Picking.search([
            ("picking_type_id", "=", picking_type.id),
            ("origin", "=", origin),
            ("state", "not in", ("done", "cancel")),
        ], limit=1, order="id desc")
        if picking:
            return picking
        roof = project.roof_project_id
        order = roof.sale_order_id if roof else False
        partner = (order.partner_shipping_id if order else False) or project.partner_id
        destination = (
            picking_type.default_location_dest_id
            or (partner and partner.property_stock_customer)
            or self.env.ref("stock.stock_location_customers")
        )
        values = {
            "picking_type_id": picking_type.id,
            "partner_id": partner.id if partner else False,
            "origin": origin,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": destination.id,
            "company_id": company.id,
        }
        if roof and roof.planned_date_begin:
            values["scheduled_date"] = roof.planned_date_begin
        # With the roof project's transfers (tectora_roof_stock): on the roof
        # project, so its material transfers do not ship these again.
        if roof and "tectora_roof_project_id" in Picking._fields:
            values["tectora_roof_project_id"] = roof.id
        return Picking.create(values)

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
    purchase_line_id = fields.Many2one(
        "purchase.order.line", string="Inkooplijn", ondelete="set null", copy=False,
        help="De lijn van de prijsaanvraag of inkooporder waarop dit product besteld is.",
    )
    move_id = fields.Many2one(
        "stock.move", string="Levering uit stock", ondelete="set null", copy=False,
        help="De beweging op de uitgaande levering waarmee dit product uit het "
        "magazijn naar de werf gaat.",
    )
    source = fields.Selection(
        [
            ("to_order", "Te bestellen"),
            ("ordered", "In bestelling"),
            ("stock", "Uit magazijn"),
        ],
        string="Herkomst",
        compute="_compute_source",
        help="Te bestellen tot het op een prijsaanvraag of een levering uit "
        "stock staat; een geannuleerde bestelling of levering zet het terug.",
    )

    @api.depends("purchase_line_id.order_id.state", "move_id.state")
    def _compute_source(self):
        for line in self:
            if line.purchase_line_id and line.purchase_line_id.order_id.state != "cancel":
                line.source = "ordered"
            elif line.move_id and line.move_id.state != "cancel":
                line.source = "stock"
            else:
                line.source = "to_order"

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
