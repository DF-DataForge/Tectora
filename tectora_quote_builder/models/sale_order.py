# -*- coding: utf-8 -*-
from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model_create_multi
    def create(self, vals_list):
        """Every new quotation gets its headers and footers, also when it is
        made in code (from a roof project, or with the company's default
        template): the headers and footers marked "Add by default" without a
        template come from the field's default, those of the quotation
        template only from the template's onchange in the form."""
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list):
            if "quotation_document_ids" in vals or not order.sale_order_template_id:
                continue
            documents = order.sale_order_template_id.quotation_document_ids.filtered(
                lambda doc: doc.add_by_default and doc.company_id.id in (False, order.company_id.id)
            )
            if documents - order.quotation_document_ids:
                order.quotation_document_ids |= documents
        return orders
