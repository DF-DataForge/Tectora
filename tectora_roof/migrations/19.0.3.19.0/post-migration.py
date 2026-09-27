# -*- coding: utf-8 -*-
"""Give every confirmed order with a project its task "Uitvoeringswerken".

The estimated execution time (hours per line, summed on the order) is a new
stored field and is computed by the upgrade itself; the task is only created
on confirmation, so the orders confirmed before this version get theirs here.
Orders whose products carry no time norm yet get no task: there is nothing to
size, and the task appears as soon as a norm is set and a quantity changes,
or the order is confirmed again.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].search([("state", "=", "sale")])
    orders._tectora_sync_execution_task()
    _logger.info(
        "tectora_roof: execution tasks synchronised for %s confirmed orders",
        len(orders),
    )
