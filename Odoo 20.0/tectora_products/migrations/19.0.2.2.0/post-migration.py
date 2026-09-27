# -*- coding: utf-8 -*-
"""Add the missing chapters and the demolition sub-categories.

Two changes that existing databases cannot pick up on their own:

* the works tree now carries every chapter of the price book, including the
  ones nobody sells from yet (07. Oversteken, 09. Worst case scenario,
  10. Algemene nota's, 11. Garantiepakket EPDM Solutions, 13. Upsale) -- a
  category that does not exist cannot be filed into by hand either;
* "03. Afbraakwerken plat dak" is split into nine sub-categories by what gets
  removed, so its 40 items are re-filed.

Only products inside the works tree are moved: a category somebody chose
outside it is left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"]
    created = Product._tectora_ensure_category_tree()
    moved = Product._tectora_recategorise()
    _logger.info(
        "tectora_products: %s categories added, %s products re-categorised",
        created, moved,
    )
