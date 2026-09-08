# -*- coding: utf-8 -*-
"""On install, every company switches to the Tectora layout, so all documents
-- quotations, invoices, deliveries, purchase orders, the roofing sheets --
come out with the roof-edge header at once. The layout stays a choice in
Settings -> Configure Document Layout like any other."""


def post_init_hook(env):
    view = env.ref("tectora_report_layout.external_layout_tectora", raise_if_not_found=False)
    if not view:
        return
    companies = env["res.company"].with_context(active_test=False).search([])
    companies.write({"external_report_layout_id": view.id})
    for company in companies.filtered(lambda c: not c.primary_color):
        company.primary_color = "#008B93"
