# -*- coding: utf-8 -*-
"""A bill of materials made to measure for one order line.

The works items Tectora sells explode into their materials through the
product's bill of materials (tectora_boms). A roof is rarely standard: one site
needs an extra primer, another a heavier insulation, so the office adapts the
components of a line on the quotation itself. That copy lives here, one per
order line, and replaces the product's bill of materials when the material
list is built. It can be written back onto the product as its new default.

Quantities are kept per unit of the sold product, in the product's own unit
(per m² of roofing), so they follow the order line; a fixed quantity holds for
the whole line (one container per site).
"""
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

# The reference of a bill of materials saved from a quotation.
SAVED_REFERENCE = "Op maat"


class TectoraSaleBom(models.Model):
    _name = "tectora.sale.bom"
    _description = "Stuklijst op maat van een orderlijn"
    _order = "id"

    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Orderlijn",
        required=True,
        ondelete="cascade",
        index=True,
    )
    order_id = fields.Many2one(
        related="sale_line_id.order_id", store=True, index=True, string="Order"
    )
    order_state = fields.Selection(related="order_id.state")
    company_id = fields.Many2one(related="order_id.company_id", store=True)
    currency_id = fields.Many2one(related="order_id.currency_id")
    product_id = fields.Many2one(
        related="sale_line_id.product_id", string="Verkocht product"
    )
    product_unit_id = fields.Many2one(
        related="product_id.uom_id", string="Eenheid van het product"
    )
    product_uom_qty = fields.Float(
        related="sale_line_id.product_uom_qty", string="Hoeveelheid"
    )
    product_uom_id = fields.Many2one(
        related="sale_line_id.product_uom_id", string="Eenheid"
    )
    line_price_unit = fields.Float(
        related="sale_line_id.price_unit",
        string="Huidige prijs",
        digits="Product Price",
    )
    source_bom_id = fields.Many2one(
        "mrp.bom",
        string="Vertrokken van",
        ondelete="set null",
        help="De stuklijst van het product waarvan deze stuklijst op maat "
        "vertrokken is.",
    )
    line_ids = fields.One2many(
        "tectora.sale.bom.line", "bom_id", string="Componenten", copy=True
    )
    quantity_in_product_uom = fields.Float(
        compute="_compute_quantity_in_product_uom",
        digits="Product Unit",
        help="De hoeveelheid van de orderlijn in de eenheid van het product: "
        "de hoeveelheden per eenheid worden daarmee vermenigvuldigd.",
    )
    cost_total = fields.Monetary(
        string="Kost van de lijn",
        compute="_compute_costs",
        currency_field="currency_id",
    )
    cost_per_unit = fields.Float(
        string="Kostprijs per eenheid",
        compute="_compute_costs",
        digits="Product Price",
        help="Kost van de componenten per verkochte eenheid (vaste "
        "hoeveelheden verdeeld over de hoeveelheid van de lijn).",
    )
    margin_percent = fields.Float(
        string="Marge (%)",
        digits=(16, 2),
        help="Opslag op de kostprijs. Bij het openen staat ze zo dat de "
        "berekende prijs gelijk is aan de huidige prijs van de orderlijn.",
    )
    price_computed = fields.Float(
        string="Berekende prijs",
        compute="_compute_price_computed",
        digits="Product Price",
        help="Kostprijs per eenheid plus de marge.",
    )
    price_differs = fields.Boolean(compute="_compute_price_computed")

    _sale_line_uniq = models.Constraint(
        "UNIQUE(sale_line_id)",
        "Een orderlijn heeft hoogstens één stuklijst op maat.",
    )

    @api.depends("product_uom_qty", "product_uom_id", "product_id")
    def _compute_quantity_in_product_uom(self):
        for bom in self:
            line = bom.sale_line_id
            bom.quantity_in_product_uom = (
                line._tectora_quantity_in_product_uom() if line.product_id else 0.0
            )

    @api.depends(
        "line_ids.cost_subtotal",
        "line_ids.unit_cost",
        "line_ids.quantity",
        "line_ids.fixed_quantity",
        "quantity_in_product_uom",
    )
    def _compute_costs(self):
        for bom in self:
            bom.cost_total = sum(bom.line_ids.mapped("cost_subtotal"))
            variable = sum(
                line.quantity * line.unit_cost
                for line in bom.line_ids
                if not line.fixed_quantity
            )
            fixed = sum(
                line.quantity * line.unit_cost
                for line in bom.line_ids
                if line.fixed_quantity
            )
            quantity = bom.quantity_in_product_uom
            # Per unit of the product; fixed costs spread over the line.
            per_product_unit = variable + (fixed / quantity if quantity else 0.0)
            product_unit = bom.product_id.uom_id
            line_unit = bom.product_uom_id
            if product_unit and line_unit and product_unit != line_unit:
                per_product_unit = product_unit._compute_price(per_product_unit, line_unit)
            bom.cost_per_unit = per_product_unit

    @api.depends("cost_per_unit", "margin_percent", "line_price_unit")
    def _compute_price_computed(self):
        for bom in self:
            bom.price_computed = bom.cost_per_unit * (1.0 + bom.margin_percent / 100.0)
            bom.price_differs = bool(
                float_compare(
                    bom.price_computed, bom.line_price_unit, precision_digits=2
                )
            )

    @api.depends("product_id", "order_id")
    def _compute_display_name(self):
        for bom in self:
            bom.display_name = _(
                "%(product)s op maat (%(order)s)",
                product=bom.product_id.display_name or "",
                order=bom.order_id.name or "",
            )

    # ------------------------------------------------------------ lifecycle
    # The component lines are written along with their bill of materials when
    # the dialog saves; the material list is rebuilt once, afterwards.
    @api.model_create_multi
    def create(self, vals_list):
        boms = super(TectoraSaleBom, self.with_context(tectora_sale_bom_batch=True)).create(vals_list)
        boms._check_editable()
        boms.order_id._tectora_sale_bom_changed()
        return boms.with_env(self.env)

    def write(self, vals):
        self._check_editable()
        result = super(TectoraSaleBom, self.with_context(tectora_sale_bom_batch=True)).write(vals)
        self.order_id._tectora_sale_bom_changed()
        return result

    def unlink(self):
        orders = self.order_id
        result = super().unlink()
        orders._tectora_sale_bom_changed()
        return result

    def _check_editable(self):
        for bom in self:
            if bom.order_id.state == "cancel":
                raise UserError(
                    _("%s is geannuleerd; de stuklijst kan niet meer wijzigen.",
                      bom.order_id.name)
                )

    @api.model
    def _margin_for_price(self, cost, price):
        """The margin that turns ``cost`` into ``price``."""
        if float_is_zero(cost, precision_digits=4) or not price:
            return 0.0
        return (price / cost - 1.0) * 100.0

    # --------------------------------------------------------------- actions
    def action_save(self):
        """Keep the components; the price of the order line stays."""
        self.ensure_one()
        return {"type": "ir.actions.act_window_close"}

    def action_save_apply_price(self):
        """Keep the components and put the computed price on the order line."""
        self.ensure_one()
        self._apply_price()
        return {"type": "ir.actions.act_window_close"}

    def _apply_price(self):
        self.ensure_one()
        line = self.sale_line_id
        if line.qty_invoiced:
            raise UserError(
                _("De lijn %s is al gefactureerd; haar prijs kan niet meer "
                  "wijzigen.", line.name)
            )
        line.price_unit = self.price_computed

    def action_reset(self):
        """Drop the customisation: the line uses the product's bill of
        materials again."""
        self.ensure_one()
        self.unlink()
        return {"type": "ir.actions.act_window_close"}

    def action_update_product_price(self):
        """The computed price becomes the product's sales price."""
        self.ensure_one()
        if self.price_computed <= 0.0:
            raise UserError(_("De berekende prijs moet groter zijn dan nul."))
        price = self.price_computed
        product = self.product_id
        if self.product_uom_id and self.product_uom_id != product.uom_id:
            price = self.product_uom_id._compute_price(price, product.uom_id)
        product.lst_price = price
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Verkoopprijs"),
                "message": _(
                    "De verkoopprijs van %(product)s is nu %(price)s.",
                    product=product.display_name,
                    price="%.2f" % price,
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def action_save_as_default(self):
        """Write the components onto the product as its default bill of
        materials, the one every next quotation starts from.

        The shipped sets (tectora_boms: the imported export and the demo set)
        are refreshed on every upgrade by their import key, so they are never
        overwritten: a new bill of materials "Op maat" is put ahead of them.
        One without a key -- made by hand, or saved here earlier -- is updated
        in place.
        """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Voeg eerst componenten toe."))
        product = self.product_id
        default = self.order_id._tectora_find_boms(product).get(product)
        values = {
            "product_qty": 1.0,
            "uom_id": product.uom_id.id,
            "bom_line_ids": [Command.clear()] + [
                Command.create(line._bom_line_values()) for line in self.line_ids
            ],
        }
        if default and not default.tectora_bom_key:
            default.write(values)
            bom = default
        else:
            # A variant BoM comes before a template one, whatever its sequence.
            variant = (
                (default and default.product_id)
                or (len(product.product_tmpl_id.product_variant_ids) > 1 and product)
            )
            bom = self.env["mrp.bom"].create(dict(
                values,
                product_tmpl_id=product.product_tmpl_id.id,
                product_id=variant.id if variant else False,
                type=default.type if default else "phantom",
                code=SAVED_REFERENCE,
                company_id=default.company_id.id if default else False,
                sequence=(default.sequence - 1) if default else 0,
            ))
        self.source_bom_id = bom
        self.order_id.message_post(
            body=_(
                "Stuklijst van %(product)s opgeslagen als standaard "
                "(%(bom)s).",
                product=product.display_name,
                bom=bom._get_html_link(),
            )
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Standaardstuklijst"),
                "message": _(
                    "De stuklijst is de standaard voor %s: nieuwe offertes "
                    "vertrekken ervan.",
                    product.display_name,
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }


class TectoraSaleBomLine(models.Model):
    _name = "tectora.sale.bom.line"
    _description = "Component van een stuklijst op maat"
    _order = "bom_id, sequence, id"

    bom_id = fields.Many2one(
        "tectora.sale.bom", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(default=10)
    currency_id = fields.Many2one(related="bom_id.currency_id")
    product_id = fields.Many2one(
        "product.product", string="Component", required=True
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Eenheid",
        compute="_compute_product_uom_id",
        store=True,
        precompute=True,
        readonly=False,
        required=True,
    )
    quantity = fields.Float(
        string="Hoeveelheid",
        default=1.0,
        digits="Product Unit",
        help="Per eenheid van het verkochte product (per m², per m, ...), of "
        "voor de hele lijn bij een vaste hoeveelheid.",
    )
    fixed_quantity = fields.Boolean(
        string="Vast",
        help="De hoeveelheid geldt voor de hele orderlijn en groeit niet mee "
        "met de verkochte hoeveelheid.",
    )
    total_quantity = fields.Float(
        string="Totaal",
        compute="_compute_total_quantity",
        digits="Product Unit",
        help="Wat de lijn nodig heeft: hoeveelheid × verkochte hoeveelheid, "
        "of de vaste hoeveelheid.",
    )
    unit_cost = fields.Float(
        string="Kostprijs",
        compute="_compute_unit_cost",
        store=True,
        precompute=True,
        readonly=False,
        digits="Product Price",
        help="Kostprijs per eenheid van de component; standaard de kostprijs "
        "van het product.",
    )
    cost_subtotal = fields.Monetary(
        string="Kost",
        compute="_compute_cost_subtotal",
        currency_field="currency_id",
    )

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        for line in self:
            if line.product_id and (
                not line.product_uom_id
                or not line.product_uom_id._has_common_reference(line.product_id.uom_id)
            ):
                line.product_uom_id = line.product_id.uom_id

    @api.depends("product_id", "product_uom_id")
    def _compute_unit_cost(self):
        for line in self:
            product = line.product_id
            if not product:
                line.unit_cost = 0.0
                continue
            cost = product.standard_price
            if product.tectora_recalc and product.tectora_recalc_size > 0.0:
                # Counted in m² or m³ here, bought per piece of that size.
                cost /= product.tectora_recalc_size
            elif line.product_uom_id and line.product_uom_id != product.uom_id:
                cost = product.uom_id._compute_price(cost, line.product_uom_id)
            line.unit_cost = cost

    @api.depends("quantity", "fixed_quantity", "bom_id.quantity_in_product_uom")
    def _compute_total_quantity(self):
        for line in self:
            line.total_quantity = (
                line.quantity
                if line.fixed_quantity
                else line.quantity * line.bom_id.quantity_in_product_uom
            )

    @api.depends("total_quantity", "unit_cost")
    def _compute_cost_subtotal(self):
        for line in self:
            line.cost_subtotal = line.total_quantity * line.unit_cost

    @api.constrains("product_id", "product_uom_id")
    def _check_uom(self):
        for line in self:
            if (
                line.product_id
                and line.product_uom_id
                and not line.product_uom_id._has_common_reference(line.product_id.uom_id)
            ):
                raise ValidationError(
                    _(
                        "De eenheid %(unit)s past niet bij %(product)s (eenheid "
                        "%(product_unit)s).",
                        unit=line.product_uom_id.name,
                        product=line.product_id.display_name,
                        product_unit=line.product_id.uom_id.name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.bom_id._check_editable()
        lines._notify_order()
        return lines

    def write(self, vals):
        self.bom_id._check_editable()
        result = super().write(vals)
        self._notify_order()
        return result

    def unlink(self):
        self.bom_id._check_editable()
        orders = self.bom_id.order_id
        result = super().unlink()
        if not self.env.context.get("tectora_sale_bom_batch"):
            orders._tectora_sale_bom_changed()
        return result

    def _notify_order(self):
        if not self.env.context.get("tectora_sale_bom_batch"):
            self.bom_id.order_id._tectora_sale_bom_changed()

    def _bom_line_values(self):
        """The component as a line of an mrp.bom made for one unit of the
        product."""
        self.ensure_one()
        return {
            "product_id": self.product_id.id,
            "product_qty": self.quantity,
            "uom_id": self.product_uom_id.id,
            "tectora_fixed_qty": self.fixed_quantity,
            "sequence": self.sequence,
        }
