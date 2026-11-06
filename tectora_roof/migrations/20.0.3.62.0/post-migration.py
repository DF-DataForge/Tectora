# -*- coding: utf-8 -*-
"""The site address of a roof project becomes a contact (site_partner_id),
the delivery address of its order. Existing roof projects get:

* the delivery address of their order, when they have one;
* else their customer, when the typed site address is the customer's (or
  empty);
* else a new delivery address under the customer, from the typed address
  ("Lostraat 15, 1703 Schepdaal").

Nothing is pushed to the orders: they already carry their delivery address.
"""
import logging
import re

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

ADDRESS = re.compile(r"^(?P<street>.+?),\s*(?P<zip>\d{4,5})\s+(?P<city>[^,]+?)\s*(?:,\s*(?P<country>.+))?$")


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"tectora_sync": True, "tracking_disable": True})
    Roof = env["tectora.roof.project"].with_context(active_test=False)
    counts = {"order": 0, "customer": 0, "created": 0}
    for roof in Roof.search([("site_partner_id", "=", False)]):
        order = roof.sale_order_id
        partner = roof.partner_id
        site = order.partner_shipping_id if order else False
        if site:
            counts["order"] += 1
        elif partner:
            typed = (roof.address or "").strip()
            if not typed or typed == partner._tectora_one_line_address():
                site = partner
                counts["customer"] += 1
            else:
                match = ADDRESS.match(typed)
                values = {
                    "parent_id": partner.commercial_partner_id.id,
                    "type": "delivery",
                    "country_id": partner.country_id.id or roof.company_id.country_id.id or False,
                }
                if match:
                    values.update(street=match["street"], zip=match["zip"], city=match["city"])
                else:
                    values["street"] = typed
                site = env["res.partner"].create(values)
                counts["created"] += 1
        if site:
            roof.write({"site_partner_id": site.id})
    _logger.info(
        "tectora_roof: site address as a contact: %(order)s from the order, "
        "%(customer)s the customer, %(created)s new delivery addresses", counts,
    )
