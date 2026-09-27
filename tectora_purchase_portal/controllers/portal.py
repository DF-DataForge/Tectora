# -*- coding: utf-8 -*-
"""The logistic lists on the site page of the employee portal."""
from odoo.addons.tectora_portal.controllers import portal as tectora_portal

# The PDF of the lists downloads through the portal's own pdf route.
tectora_portal.PDF_REPORTS["logistiek"] = (
    "tectora_purchase.action_report_logistics_lists",
    "Logistieke lijsten",
)


class TectoraEmployeePortalPurchase(tectora_portal.TectoraEmployeePortal):

    def _tectora_site_values(self, employee, project, tab, **kw):
        values = super()._tectora_site_values(employee, project, tab, **kw)
        values["logistics_lists"] = project.sudo()._logistics_lists()
        return values
