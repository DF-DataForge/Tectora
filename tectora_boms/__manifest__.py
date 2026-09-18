# -*- coding: utf-8 -*-
{
    "name": "Data Forge Stuklijsten",
    "summary": "Importeer de stuklijsten van de dakwerken en koppel ze aan de "
    "bestaande producten en grondstoffen",
    "description": """
Data Forge Stuklijsten
======================
Loads the works bills of materials (``Stuklijst_Tectora.xlsx``) onto the
products that are already in the database, so a confirmed sale order can
explode into a material list.

The export comes from a database that uses product variants: a component reads
``Buitenhoek DRBS (200mm, geanodiseerd)`` -- a template name plus its attribute
values. This catalogue is flat and spells the same article ``Buitenhoek DRBS
200/80 Ano``. The two share no key and barely share a vocabulary, so the match
is built out of the structure of the names, with three keys:

* an ``[article code]`` in the component name against the vendor's product code
  or a code embedded in a catalogue name, or an equal name;
* a keyword table, which is all the labour lines need;
* family tokens + the leading dimension + the finish class, which is how the
  catalogue encodes its profile ranges. Every RAL collapses onto one class
  because the catalogue carries only an anodised and a "Ral divers" article per
  range.

Two things the export cannot decide are surfaced rather than guessed: its unit
column is a packaging description ("Doos 500 stuks", "m per 3m element") whose
quantity basis flips between rows, and a third of its products have no
counterpart here. The wizard reports both and, by default, leaves those lines
out instead of loading a quantity that would be wrong by a factor of 500.

Variants are kept as several bills of materials on one product, with the
variant in the BoM reference and the default first, so nothing about the
product structure has to change.

The export ships as ``data/bom_catalog.json`` (regenerate it with
``tools/parse_bom_export.py``) and is loaded on install and on upgrade, with
only the confident matches created. The wizard takes a fresh file, can lower
the thresholds and can analyse without writing anything.

A bill of materials can also be put on a service product: Odoo's own field
only offers goods, but the works items Tectora sells are services, so the
domain is widened here.

See ``docs/stuklijst_koppeling.md`` for the analysis.

Demo set
--------
Because the export matches on names and loads mostly labour lines, the module
also ships ``data/demo_boms.json``: one complete bill of materials per works
item that has a counterpart among the raw materials (membrane with adhesive,
tape, primer and sealant; insulation with foam or screws and plates; roof
edges with profile, couplers, screws and sealant; outlets, downpipes, anchors,
penetrations, wall connections, ...), keyed on product codes with the usual
roofer's consumption norms. It is loaded on install and upgrade with the
reference "Demo" and the key ``demo:<code>``, ahead of the imported export, and
can be refreshed or removed from *Verkoop → Configuratie*. Built and checked
by ``tools/build_demo_boms.py``; see ``docs/demo_stuklijsten.md``.

Labour norms
------------
The export's labour lines (``werkuren construction``, ``werkuren afbraak``,
``werkuren veiligheid``) are Tectora's own time per unit of each works item.
``tools/build_labour_norms.py`` reads them into ``data/labour_norms.json``,
mapped by hand onto the catalogue's product families, and the module fills
"Geschatte tijd per eenheid" (a field of Tectora Dakmeting) from it on install
and upgrade, keeping any value the office typed in; *Verkoop → Configuratie →
Tijdnormen laden* reloads and overwrites.
    """,
    "version": "19.0.1.3.0",
    "category": "Manufacturing",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_products", "mrp"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "views/product_views.xml",
        "views/demo_boms_actions.xml",
        "wizard/bom_import_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "auto_install": True,
    "installable": True,
}
