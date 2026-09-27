# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class QuotationTemplateImport(models.TransientModel):
    _name = "tectora.quotation.template.import"
    _description = "Offertesjablonen laden"

    refresh = fields.Boolean(
        string="Bestaande sjablonen opnieuw opbouwen",
        default=False,
        help="Uit: bestaande sjablonen behouden hun lijnen, enkel de naam, "
        "de geldigheidsduur en de voorwaarden volgen het bestand. Aan: de "
        "lijnen van de bestaande sjablonen worden vervangen door die uit het "
        "bestand -- eigen aanpassingen gaan dan verloren.",
    )
    state = fields.Selection(
        [("draft", "Concept"), ("done", "Uitgevoerd")], default="draft"
    )
    summary = fields.Text(string="Resultaat", readonly=True)

    def action_import(self):
        self.ensure_one()
        counters = self.env["sale.order.template"]._tectora_import_quotation_templates(
            refresh=self.refresh
        )
        _logger.info("tectora_products: wizard loaded templates (%s)", counters)
        lines = [
            _("%(new)s nieuwe sjablonen, %(upd)s bijgewerkt",
              new=counters.get("created", 0), upd=counters.get("updated", 0)),
        ]
        if counters.get("relined"):
            lines.append(
                _("%s sjablonen kregen hun lijnen opnieuw uit het bestand")
                % counters["relined"]
            )
        if counters.get("missing"):
            lines.append(
                _("Opgelet: %s producten uit het bestand staan niet in de "
                  "database. Die lijnen zijn overgeslagen -- importeer eerst "
                  "de productcatalogus.") % counters["missing"]
            )
        self.write({"state": "done", "summary": "\n".join(lines)})
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
