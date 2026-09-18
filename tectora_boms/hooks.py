# -*- coding: utf-8 -*-
"""Load the shipped bills of materials on install.

Two sets: the export, of which only the confident matches are created
(``docs/stuklijst_koppeling.md`` has the analysis and the queue of decisions
the rest needs), and the demo set, one complete bill of materials per works
item keyed on product codes (``docs/demo_stuklijsten.md``), plus the labour
norms the export's werkuren lines give per works item. Upgrades run the
same thing through migrations/, since Odoo only calls a post_init_hook on
install.
"""
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    env["mrp.bom"]._tectora_import_shipped_boms()
    env["mrp.bom"]._tectora_import_demo_boms()
    env["product.template"]._tectora_import_labour_norms()
