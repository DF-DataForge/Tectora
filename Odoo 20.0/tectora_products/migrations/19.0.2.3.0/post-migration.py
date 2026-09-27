# -*- coding: utf-8 -*-
"""Split the works items from the raw materials.

A works item can be sold, a raw material cannot, so they no longer share a
category: the chapters keep the works items, and the same chapter structure is
mirrored under a "Grondstoffen" branch for the materials. That also keeps the
drawing's product picker clean -- its whitelist sits on the category, so a
category that holds only materials simply never offers them.

Existing databases are re-filed here, and the materials are taken out of the
sales catalogue (sale_ok). Only products the shipped catalogue knows are
touched; anything filed or flagged by hand outside it is left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"]
    created = Product._tectora_ensure_category_tree()
    moved = Product._tectora_recategorise()
    unsold = Product._tectora_enforce_goods_not_sellable()
    _logger.info(
        "tectora_products: %s categories added, %s products re-categorised, "
        "%s raw materials no longer sellable", created, moved, unsold,
    )
