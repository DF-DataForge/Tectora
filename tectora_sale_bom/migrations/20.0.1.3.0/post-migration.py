# -*- coding: utf-8 -*-
"""Bills of materials count a component with hercalculatie in its Reken-UoM:
existing lines get that unit. Their quantities already were in it."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    templates = env["product.template"].with_context(active_test=False).search(
        [("tectora_recalc", "=", True)]
    )
    templates._tectora_sync_recalc_uom()
    _logger.info("tectora_sale_bom: Reken-UoM put on the lines of %s product(s)", len(templates))
