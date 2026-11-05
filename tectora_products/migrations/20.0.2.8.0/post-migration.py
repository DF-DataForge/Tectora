# -*- coding: utf-8 -*-
"""The finish of the roof's sides in categories of their own, for the
drawing's Randafwerking: 02. Dakranden/Dakrandprofielen, /Kralen, /Hoeken &
eindstukken, and 04. Opbouwwerken plat dak/Aansluitingen (out of
Afdichting). Existing products are filed on their name."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"]
    Product._tectora_ensure_category_tree()
    moved = Product._tectora_refile_subcategories()
    _logger.info("tectora_products: %s products filed for the Randafwerking", moved)
