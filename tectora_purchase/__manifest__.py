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

A third route, **Uit voorraad**, is for material that lies in the warehouse
and is not purchased at all.

Every material requirement line gets its logistic route, its vendor (the
cheapest vendor pricelist line of the product, changeable per line) and the
free stock of its product. *Inkoop organiseren* -- from the Dakmeting menu or
from a roof project -- is the ordering board: one kanban column per route,
cards ordered per vendor, vendor and stock on every card; dragging a card to
another column decides how that material is delivered.

*Inkooporders aanmaken* (on the board, on the Materiaalbehoefte list, on the
roof project) then orders what is on the board at the vendors' prices, with
the project's analytic account on every line so the purchase shows on the
project dashboard:

* a **dropship** order is always one roof project: it carries the site
  address, the project reference, the planned start of the works as expected
  arrival, and -- when the same project also has material coming through the
  warehouse or from stock -- the flag *Extra materiaal af te halen aan het
  magazijn* with the list of that material, shown on the order, on the roof
  project and in the project's chatter;
* a **warehouse** order is one per vendor, its lines grouped per roof project
  under a section line naming the project, the site and the planned start, so
  the vendor sees which delivery belongs to which project.

The lines remember their purchase order and follow it: te bestellen, uit
voorraad, offerteaanvraag, besteld, ontvangen.

Every roof project has three **logistic lists** (tab Logistiek, and the
report *Logistieke lijsten*, each list also printable on its own): the pick
list of the own warehouse, the receipts of project-specific orders at the
warehouse and the dropship deliveries on site, each with the purchase orders
and transfers behind it, tick boxes per line and the logistics responsible of
the project. With the employee portal installed, the same lists are on the
site's Materialen tab, with the PDF.

Installs itself as soon as Dakmeting, Purchase, Inventory and Dropshipping
are installed.
    """,
    "version": "19.0.1.2.0",
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
        "report/purchase_order_report.xml",
        "report/logistics_lists_report.xml",
        "wizard/purchase_from_material_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
