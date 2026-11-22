# -*- coding: utf-8 -*-
"""On install, every company switches to the Schldr layout, so all documents
-- quotations, invoices, deliveries, purchase orders, the site sheets --
come out with the accent-edge header at once. The layout stays a choice in
Settings -> Configure Document Layout like any other.

Since Odoo 20 the table design is a choice of its own (Light, Striped, ...);
a company still on the default gets Schldr, the design the layout was drawn
with."""


def post_init_hook(env):
    view = env.ref("schldr_report_layout.external_layout_schldr", raise_if_not_found=False)
    if not view:
        return
    companies = env["res.company"].with_context(active_test=False).search([])
    companies.write({"external_report_layout_id": view.id})
    for company in companies.filtered(lambda c: not c.primary_color):
        company.primary_color = "#2F5D8A"
    companies.filtered(lambda c: c.report_tables_id == "light").write(
        {"report_tables_id": "schldr"}
    )
