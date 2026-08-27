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

See ``docs/stuklijst_koppeling.md`` for the analysis.
    """,
    "version": "19.0.1.0.0",
    "category": "Manufacturing",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["tectora_products", "mrp"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/bom_import_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
