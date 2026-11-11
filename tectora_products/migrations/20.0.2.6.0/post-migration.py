# -*- coding: utf-8 -*-
"""The build-up of a flat roof in categories of its own: Dampscherm,
Isolatie/PIR, Isolatie/Minerale wol, Isolatie/Coverboard, Dakbedekking/EPDM and
Dakbedekking/Bitumen & Resitrix under 04. Opbouwwerken plat dak (both
branches). The existing products are filed into them on their name."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"]
    created = Product._tectora_ensure_category_tree()
    moved = Product._tectora_recategorise()
    refiled = Product._tectora_refile_subcategories()
    _logger.info(
        "tectora_products: %s categories created, %s products re-categorised, "
        "%s moved to a build-up sub-category", created, moved, refiled,
    )
