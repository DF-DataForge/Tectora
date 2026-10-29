# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Bestellijst op de materiaallijst",
    "summary": "Wat via de bestellijst besteld wordt of uit het magazijn komt, "
    "staat ook op de materiaallijst van het project",
    "description": """
Data Forge Dakmeting — Bestellijst op de materiaallijst
=======================================================
The order list (Bestellijst) and the material list (Materiaallijst) of a
project each kept their own track of what was ordered: a request for
quotation or a delivery from stock made on the order list left the material
list at "Te bestellen".

With this module, the material list follows the order list:

* a product ordered on the order list: its material line gets the purchase
  order line and the vendor, so Inkooporder, Leverancier and Inkoopstatus
  (Offerteaanvraag, Besteld, Ontvangen) follow that purchase order;
* a product the order list takes from the warehouse: its material line
  shows "Uit voorraad", with the outgoing delivery and its state.

A material line that is already on a purchase order (from the material
list's own "Inkooporders aanmaken") keeps it.

Installs itself as soon as the Bestellijst and Dakmeting — Inkoop are
installed.
    """,
    "version": "20.0.1.0.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_project_order_list", "tectora_purchase"],
    "data": [],
    "auto_install": True,
    "installable": True,
}
