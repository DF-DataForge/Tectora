# -*- coding: utf-8 -*-
"""Raw materials by material type: the Grondstoffen branch no longer mirrors
the quotation chapters (Grondstoffen/02. Dakranden, Grondstoffen/04.
Opbouwwerken plat dak/Afvoer, ...) but files every raw material by what it
is: Dakbanen/EPDM, Isolatie/PIR, Zinkwerk & hemelwater, Afvoerleidingen PE &
PP, Bevestigingsmaterialen, ... The mirrored chapters left empty are removed.
The sales products keep the chapters of the roof planner."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env["product.template"]
    Product._tectora_ensure_category_tree()
    Product._tectora_recategorise()
    Product._tectora_refile_subcategories()
    moved = Product._tectora_refile_goods()
    _logger.info("tectora_products: %s raw materials filed by material type", moved)
