# -*- coding: utf-8 -*-
"""Import the standard parts of the order list from the standardised Excel
list.

Tab "Bestellijst", one row per part:

    Volgorde | Onderdeel | Actie | Leveranciers | Toelichting leveranciers

Actie is "Bestellen" or "Stock eerst"; Leveranciers are contact names
separated by ";" (or new lines), matched with the existing contacts.
"""
import base64
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.tectora_project_tasks.tools import xlsx

_logger = logging.getLogger(__name__)

COLUMNS = {
    "sequence": ("Volgorde", "Nr", "#"),
    "name": ("Onderdeel",),
    "order_action": ("Actie",),
    "suppliers": ("Leveranciers", "Leverancier"),
    "supplier_note": ("Toelichting leveranciers", "Toelichting", "Leveranciers volgens bestellijst"),
}
ACTIONS = {
    "bestellen": "order", "order": "order", "b": "order",
    "stock eerst": "stock_first", "stock": "stock_first", "stock first": "stock_first",
    "stock_first": "stock_first", "s": "stock_first", "eerst stock": "stock_first",
}


class TectoraOrderListImport(models.TransientModel):
    _name = "tectora.order.list.import"
    _description = "Bestellijst importeren"

    file = fields.Binary(string="Bestand (.xlsx)", attachment=False)
    filename = fields.Char(string="Bestandsnaam")
    mode = fields.Selection(
        [
            ("update", "Toevoegen en bijwerken"),
            ("replace", "Vervangen"),
        ],
        string="Bestaande onderdelen", default="update", required=True,
        help="Toevoegen en bijwerken: onderdelen met dezelfde naam worden "
        "bijgewerkt, nieuwe toegevoegd; de rest blijft. Vervangen: onderdelen "
        "die niet in het bestand staan, worden gearchiveerd (bestaande "
        "bestellijsten van projecten blijven ongewijzigd).",
    )
    create_suppliers = fields.Boolean(
        string="Ontbrekende leveranciers aanmaken",
        help="Een leverancier die niet als contact bestaat, wordt aangemaakt. "
        "Uit: hij wordt overgeslagen en vermeld in het verslag.",
    )
    template_file = fields.Binary(string="Standaardlijst", compute="_compute_template_file")
    template_filename = fields.Char(default="Bestellijst.xlsx")
    state = fields.Selection([("draft", "Nieuw"), ("done", "Klaar")], default="draft")
    summary = fields.Text(readonly=True)

    # --------------------------------------------------------------- template
    def _compute_template_file(self):
        data = self._tectora_template_workbook()
        for wizard in self:
            wizard.template_file = base64.b64encode(data).decode()

    @api.model
    def _tectora_template_workbook(self):
        header = ["Volgorde", "Onderdeel", "Actie", "Leveranciers", "Toelichting leveranciers"]
        rows = [
            [1, "Dakbedekking (EPDM)", "Bestellen", "Leverancier A; Leverancier B",
             "Levertijd ± 2 weken; bovenaan omdat het de langste levertijd heeft."],
            [2, "Isolatie", "Stock eerst", "Leverancier B", "Eerst de voorraad nakijken."],
            [3, "Dakranden en afwerkingsprofielen", "Bestellen", "Leverancier A", ""],
            [4, "Bevestigingsmiddelen en lijm", "Stock eerst", "", ""],
        ]
        explanation = [
            ["Tabblad Bestellijst", "Eén regel per onderdeel; elk nieuw project krijgt deze onderdelen "
                                    "in zijn bestellijst."],
            ["Volgorde", "Optioneel: de volgorde op de bestellijst (bovenaan wat de langste levertijd "
                         "heeft). Leeg = de volgorde van de regels."],
            ["Onderdeel", "Verplicht. Bestaat er al een onderdeel met deze naam, dan wordt het bijgewerkt."],
            ["Actie", "Bestellen (altijd bestellen voor het project) of Stock eerst (eerst de voorraad "
                      "nakijken, enkel het tekort bestellen). Leeg = Bestellen."],
            ["Leveranciers", "Namen van contacten, gescheiden door ; (puntkomma). De eerste is de "
                             "standaardleverancier. Een naam die niet als contact bestaat, wordt "
                             "overgeslagen, tenzij 'Ontbrekende leveranciers aanmaken' aangevinkt is."],
            ["Toelichting leveranciers", "Vrije tekst: wie levert wat, levertijden, ..."],
            ["", ""],
            ["Importeren", "Toevoegen en bijwerken: onderdelen met dezelfde naam worden bijgewerkt. "
                           "Vervangen: onderdelen die niet in het bestand staan, worden gearchiveerd."],
        ]
        return xlsx.build_workbook([
            ("Bestellijst", header, rows, [10, 34, 14, 34, 50]),
            ("Uitleg", ["Kolom", "Betekenis"], explanation, [24, 90]),
        ])

    def action_download_template(self):
        """The standardised list, through the usual download URL."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content?model={self._name}&id={self.id}&field=template_file"
                   "&filename_field=template_filename&download=true",
            "target": "self",
        }

    # ----------------------------------------------------------------- import
    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Kies eerst een Excel-bestand (.xlsx)."))
        data = self.file.open().read() if hasattr(self.file, "open") else base64.b64decode(self.file)
        counters = self._tectora_import(data)
        lines = [
            self.env._("Bestand: %s", self.filename or "-"),
            self.env._("Onderdelen: %(new)s nieuw, %(upd)s bijgewerkt",
                       new=counters["created"], upd=counters["updated"]),
        ]
        if self.mode == "replace":
            lines.append(self.env._("Gearchiveerd: %s onderdelen", counters["archived"]))
        if counters["suppliers_created"]:
            lines.append(self.env._("Leveranciers aangemaakt: %s", ", ".join(counters["suppliers_created"])))
        if counters["suppliers_missing"]:
            lines.append(self.env._(
                "Niet gevonden en overgeslagen (geen contact met die naam): %s",
                ", ".join(counters["suppliers_missing"]),
            ))
        lines.append(self.env._(
            "Bestaande bestellijsten van projecten blijven ongewijzigd; nieuwe projecten krijgen deze onderdelen."
        ))
        self.write({"state": "done", "summary": "\n".join(lines)})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Bestellijst importeren"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _tectora_import(self, data):
        parts, errors = self._tectora_parse(data)
        if errors:
            raise UserError(
                self.env._("Het bestand werd niet geïmporteerd:\n%s", "\n".join(errors[:30]))
                + ("\n…" if len(errors) > 30 else "")
            )
        if not parts:
            raise UserError(self.env._("Geen onderdelen gevonden in het bestand."))
        return self._tectora_apply(parts)

    def _tectora_parse(self, data):
        try:
            rows = xlsx.read_sheet(data, ["Bestellijst", "Onderdelen"], COLUMNS, required_columns=("name",))
        except ValueError as error:
            raise UserError(str(error)) from None
        errors, parts = [], {}
        for index, row in enumerate(rows, start=1):
            name = xlsx.cell_text(row.get("name"))
            if not name:
                errors.append(self.env._("Rij %s: 'Onderdeel' is verplicht.", row["_row"]))
                continue
            action_text = xlsx.normalize(xlsx.cell_text(row.get("order_action")))
            if action_text and action_text not in ACTIONS:
                errors.append(self.env._(
                    "Rij %(row)s: 'Actie' moet Bestellen of Stock eerst zijn, niet '%(value)s'.",
                    row=row["_row"], value=xlsx.cell_text(row.get("order_action")),
                ))
                continue
            try:
                sequence = xlsx.parse_int(row.get("sequence"))
            except ValueError:
                errors.append(self.env._("Rij %s: 'Volgorde' moet een geheel getal zijn.", row["_row"]))
                continue
            suppliers = [
                part.strip() for part in re.split(r"[;\n]", xlsx.cell_text(row.get("suppliers")))
                if part.strip()
            ]
            parts[xlsx.normalize(name)] = {
                "name": name,
                "sequence": sequence * 10 if sequence is not None else index * 10,
                "order_action": ACTIONS.get(action_text, "order"),
                "suppliers": suppliers,
                "supplier_note": xlsx.cell_text(row.get("supplier_note")) or False,
            }
        return list(parts.values()), errors

    def _tectora_apply(self, parts):
        Template = self.env["tectora.order.list.template"].with_context(active_test=False)
        existing = {}
        for template in Template.search([], order="active desc, id"):
            existing.setdefault(xlsx.normalize(template.name), template)
        counters = {"created": 0, "updated": 0, "archived": 0,
                    "suppliers_created": [], "suppliers_missing": []}
        touched = Template
        for part in parts:
            partners = self._tectora_suppliers(part["suppliers"], counters)
            vals = {
                "name": part["name"],
                "sequence": part["sequence"],
                "order_action": part["order_action"],
                "supplier_note": part["supplier_note"],
                "partner_ids": [fields.Command.set(partners.ids)],
                "active": True,
            }
            template = existing.get(xlsx.normalize(part["name"]))
            if template:
                template.write(vals)
                counters["updated"] += 1
            else:
                template = Template.create(vals)
                counters["created"] += 1
            touched |= template
        if self.mode == "replace":
            stale = Template.search([("active", "=", True), ("id", "not in", touched.ids)])
            counters["archived"] = len(stale)
            stale.write({"active": False})
        _logger.info("tectora_project_order_list: order list imported (%s)", counters)
        return counters

    def _tectora_suppliers(self, names, counters):
        """The contacts for the supplier names, in that order (the first one
        is the default supplier of the part)."""
        Partner = self.env["res.partner"]
        partners = Partner
        for name in names:
            partner = Partner.search(
                [("name", "=ilike", name), ("parent_id", "=", False)],
                order="supplier_rank desc, id", limit=1,
            )
            if not partner and self.create_suppliers:
                partner = Partner.create({"name": name, "supplier_rank": 1})
                counters["suppliers_created"].append(name)
            if not partner:
                if name not in counters["suppliers_missing"]:
                    counters["suppliers_missing"].append(name)
                continue
            partners |= partner
        return partners
