# -*- coding: utf-8 -*-
"""Twenty quotation templates, and the works items they need.

The export names the vendor a works item's material comes from, which filed
forty of them ("Leveren en plaatsen van de koepelschaal type: Skylux", vendor
Cintralux) as raw materials -- and a raw material is not sellable, so a dome
could not be quoted at all. Those are put back in the works branch and on sale
first; then the templates that quote them are created.

Existing templates keep their lines: once the office has tuned a template it
owns it, and only the name, the validity and the terms follow the file.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"]
    moved = Product._tectora_recategorise()
    on_sale = Product._tectora_enforce_works_sellable()
    counters = env["sale.order.template"]._tectora_import_quotation_templates()
    _logger.info(
        "tectora_products: %s products re-categorised, %s works items back on "
        "sale, quotation templates %s", moved, on_sale, counters,
    )
