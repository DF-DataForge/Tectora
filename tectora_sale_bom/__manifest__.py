# -*- coding: utf-8 -*-
{
    "name": "Data Forge Stuklijst op maat",
    "summary": "Pas de stuklijst van een orderlijn aan op de offerte en bewaar "
    "ze als standaard",
    "description": """
Data Forge Stuklijst op maat
============================
A button on every product line of a quotation opens the bill of materials of
that line: the components of the product's default stuklijst (tectora_boms),
per unit of the sold product, with their cost. The office adapts them for this
site -- another primer, a heavier insulation, an extra container -- and the
line keeps its own copy, which replaces the product's bill of materials when
the material list is built. Nothing is stored until the dialog is saved.

* Quantities per sold unit (per m², per m), or fixed for the whole line
  ("Vast": one container per site, whatever the area).
* Cost per unit, a margin (set on opening so the computed price equals the
  line's price) and the computed price, which can be applied to the order
  line or become the product's sales price.
* *Opslaan als standaardstuklijst* (Manufacturing administrators) writes the
  components onto the product as its default bill of materials, the one every
  next quotation starts from. The shipped sets of tectora_boms (export and
  demo) are refreshed by their import key on every upgrade and are therefore
  never overwritten: a bill of materials "Op maat" is put ahead of them. One
  made by hand or saved here earlier is updated in place.
* *Standaard herstellen* drops the customisation.
* On a confirmed order the material list follows every change; what is
  already on a transfer stays there and the next one carries the difference
  (tectora_roof_stock).
* Components that are kits are exploded; bills of materials get the same
  "Vast" flag on their lines, honoured in the material list.

Ported from df_custom_bom_in_so (Odoo 18), rebuilt on Tectora's material
list instead of rewriting stock moves.
    """,
    "version": "20.0.1.1.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_roof", "tectora_boms"],
    "data": [
        "security/ir.access.csv",
        "views/sale_bom_views.xml",
        "views/sale_order_views.xml",
        "views/mrp_bom_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
