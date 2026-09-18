# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path

from odoo import _, api, models
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)

LABOUR_NORMS = Path(__file__).parent.parent / "data" / "labour_norms.json"
NORM_FIELD = "tectora_minutes_per_uom"  # defined by tectora_roof


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _tectora_import_labour_norms(self, overwrite=False):
        """Fill "Geschatte tijd per eenheid" from data/labour_norms.json: the
        werkuren of the Stuklijst export per works item, in minutes.

        The field belongs to tectora_roof; without it there is nothing to
        fill. A norm the office already typed in is kept unless ``overwrite``
        is set (the menu action does, install and upgrade do not).
        """
        if NORM_FIELD not in self._fields:
            _logger.info(
                "tectora_boms: %s not installed here, labour norms not loaded",
                NORM_FIELD,
            )
            return {}
        if not LABOUR_NORMS.exists():
            _logger.warning("tectora_boms: %s missing, no labour norms loaded", LABOUR_NORMS)
            return {}
        data = json.loads(LABOUR_NORMS.read_text(encoding="utf-8"))
        norms = {entry["code"]: entry["minutes"] for entry in data.get("norms") or []}
        templates = self.with_context(active_test=False).search(
            [("default_code", "in", list(norms))]
        )
        report = {"norms": len(norms), "set": 0, "kept": 0, "unchanged": 0}
        found = set()
        for template in templates:
            found.add(template.default_code)
            minutes = norms[template.default_code]
            current = template[NORM_FIELD]
            if not float_compare(current, minutes, precision_digits=1):
                report["unchanged"] += 1
                continue
            if current and not overwrite:
                report["kept"] += 1
                continue
            template[NORM_FIELD] = minutes
            report["set"] += 1
        report["missing"] = sorted(set(norms) - found)
        _logger.info(
            "tectora_boms: labour norms: %(set)s products set, %(kept)s kept their "
            "own value, %(unchanged)s already equal, %(missing_count)s codes not in "
            "the database",
            dict(report, missing_count=len(report["missing"])),
        )
        return report

    @api.model
    def _tectora_labour_norms_action(self):
        """Load the norms from a menu, overwriting, and say what happened."""
        report = self._tectora_import_labour_norms(overwrite=True)
        if not report:
            message = _(
                "Het veld 'Geschatte tijd per eenheid' bestaat niet in deze "
                "database (module Tectora Dakmeting niet geïnstalleerd)."
            )
            kind = "warning"
        else:
            message = _(
                "%(set)s producten kregen hun tijdnorm uit de werkuren van de "
                "stuklijstexport (%(unchanged)s stonden al juist).",
                set=report["set"], unchanged=report["unchanged"],
            )
            if report["missing"]:
                message += " " + _(
                    "%s productcodes uit het bestand staan niet in de database.",
                    len(report["missing"]),
                )
            kind = "success"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Tijdnormen"),
                "message": message,
                "type": kind,
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
