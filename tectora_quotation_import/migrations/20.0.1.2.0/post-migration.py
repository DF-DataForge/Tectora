# -*- coding: utf-8 -*-
"""Quotations imported before 20.0.1.2.0 show "Werkpost (oud systeem)" above
the description of every generic line, and the name of a catalogue works item
twice. The generic works item now shows only the description (Omschrijving
als label); a catalogue line gets the description Odoo itself gives it."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.product"].with_context(active_test=False)
    Product.search([("default_code", "=like", "TECTORA-IMPORT%")]).write(
        {"tectora_description_label": True}
    )
    lines = env["sale.order.line"].search([
        ("order_id.tectora_legacy_number", "!=", False),
        ("display_type", "=", False),
        ("product_id.tectora_description_label", "=", False),
        ("order_id.locked", "=", False),  # a locked order cannot be changed
    ])
    for line in lines:
        if line.name and line.name.strip() == (line.product_id.name or "").strip():
            line.with_context(tectora_sync=True).write(
                {"name": line._get_sale_order_line_multiline_description_sale() or False}
            )
