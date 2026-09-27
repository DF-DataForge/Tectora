# -*- coding: utf-8 -*-
"""Load the supplier catalogue on upgrade.

The catalogue import lives in a post_init_hook, which Odoo only runs when a
module is *installed*. Databases that already have this module therefore need
this migration to pick up the new catalogue (and to archive the previous
price-book products) with a plain "Upgrade" from the Apps list.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    result = env["product.template"]._tectora_import_product_catalog()
    _logger.info("tectora_products: catalogue migration result: %s", result)
