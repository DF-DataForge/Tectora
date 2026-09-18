# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Inkoop",
    "summary": "Bestel de materiaalbehoefte van de dakprojecten bij de "
    "ingestelde leveranciers, via dropship naar de werf of via het magazijn",
    "description": """
Data Forge Dakmeting — Inkoop
=============================
Bridge between the material requirements of the roof projects and Odoo
Purchase / Inventory.

Two logistic routes (``tectora.logistics.route``) describe where purchased
material goes, and both are installed ready to use:

* **Dropship — levering op de werf**: the vendor delivers straight to the
  site. The purchase order uses the company's dropship operation type and
  carries the site's delivery address, so confirming it creates a dropship
  transfer from the vendor to the customer.
* **Levering aan magazijn**: the vendor delivers to the warehouse. The
  purchase order uses the warehouse's receipt operation type, so confirming it
  creates a receipt into stock.

Routes can be added or changed under Dakmeting -> Logistieke routes; a
product carries its preferred route (product form, tab Inkoop) and the route
falls back on the product's Odoo routes (a product with the Dropship route is
dropshipped) and then on the default route.

Every material requirement line gets its logistic route and its vendor (the
cheapest vendor pricelist line of the product, changeable per line). From the
Materiaalbehoefte overview -- or from the Materiaallijst of a roof project --
select the lines and click *Inkooporders aanmaken*: one purchase order per
vendor, per route and per roof project (lines of several projects can be
merged for warehouse deliveries) is created at the vendor's prices, with the
project's analytic account on every line, so the purchase shows up on the
project dashboard. The lines remember their purchase order and follow it: te
bestellen, offerteaanvraag, besteld, ontvangen.

Installs itself as soon as Dakmeting, Purchase, Inventory and Dropshipping
are installed.
    """,
    "version": "19.0.1.0.0",
    "category": "Inventory/Purchase",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "purchase_stock", "stock_dropshipping"],
    "data": [
        "security/ir.model.access.csv",
        "data/logistics_route_data.xml",
        "views/logistics_route_views.xml",
        "views/roof_material_views.xml",
        "views/roof_project_views.xml",
        "views/project_project_views.xml",
        "views/product_views.xml",
        "views/purchase_order_views.xml",
        "wizard/purchase_from_material_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
