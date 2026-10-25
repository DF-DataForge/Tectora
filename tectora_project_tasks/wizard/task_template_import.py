# -*- coding: utf-8 -*-
"""Import the phases and task templates from the standardised Excel list.

Tab "Taaksjablonen", one row per task or subtask:

    Fase | Omschrijving fase | Taak | Subtaak | Optie | Deadline t.o.v. | Dagen | Toelichting
    (+ Volgt bestellijst, with the order list module)

A row without Subtaak is a main task, a row with Subtaak a subtask of the
main task named in Taak. Optional tab "Fases" sets the milestone deadline of
a phase: Fase | Omschrijving | Deadline t.o.v. | Dagen.
"""
import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..tools import xlsx

_logger = logging.getLogger(__name__)

TASK_COLUMNS = {
    "phase": ("Fase",),
    "phase_subtitle": ("Omschrijving fase",),
    "task": ("Taak",),
    "subtask": ("Subtaak",),
    "optional": ("Optie",),
    "deadline_reference": ("Deadline t.o.v.", "Deadline tov", "Deadline"),
    "deadline_offset": ("Dagen",),
    "description": ("Toelichting",),
    "order_list_auto": ("Volgt bestellijst",),
}
PHASE_COLUMNS = {
    "phase": ("Fase",),
    "subtitle": ("Omschrijving", "Omschrijving fase"),
    "deadline_reference": ("Deadline t.o.v.", "Deadline mijlpaal t.o.v.", "Deadline tov", "Deadline"),
    "deadline_offset": ("Dagen",),
}
REFERENCES = {
    "start": "start", "startdatum": "start", "start project": "start",
    "startdatum project": "start", "begin": "start",
    "einde": "end", "eind": "end", "einddatum": "end", "einde project": "end",
    "einddatum project": "end", "end": "end",
}


class TectoraTaskTemplateImport(models.TransientModel):
    _name = "tectora.task.template.import"
    _description = "Taaksjablonen importeren"

    file = fields.Binary(string="Bestand (.xlsx)", attachment=False)
    filename = fields.Char(string="Bestandsnaam")
    mode = fields.Selection(
        [
            ("update", "Toevoegen en bijwerken"),
            ("replace", "Vervangen"),
        ],
        string="Bestaande sjablonen", default="update", required=True,
        help="Toevoegen en bijwerken: fases en taken met dezelfde naam worden "
        "bijgewerkt, nieuwe toegevoegd; de rest blijft. Vervangen: wat niet "
        "in het bestand staat, wordt gearchiveerd (bestaande projecten "
        "houden hun taken).",
    )
    template_file = fields.Binary(string="Standaardlijst", compute="_compute_template_file")
    template_filename = fields.Char(default="Taaksjablonen.xlsx")
    state = fields.Selection([("draft", "Nieuw"), ("done", "Klaar")], default="draft")
    summary = fields.Text(readonly=True)

    # --------------------------------------------------------------- template
    @api.model
    def _tectora_with_order_list(self):
        return "order_list_auto" in self.env["tectora.task.template"]._fields

    def _compute_template_file(self):
        data = self._tectora_template_workbook()
        for wizard in self:
            wizard.template_file = base64.b64encode(data).decode()

    @api.model
    def _tectora_template_workbook(self):
        """The standardised list: the columns with an example, and an
        explanation."""
        with_order_list = self._tectora_with_order_list()
        header = ["Fase", "Omschrijving fase", "Taak", "Subtaak", "Optie",
                  "Deadline t.o.v.", "Dagen", "Toelichting"]
        rows = [
            ["Voorbereiding", "vóór de uitvoering", "Werfbezoek en opmeting", "", "", "start", -14, ""],
            ["Voorbereiding", "", "Materiaal besteld", "", "", "start", -7,
             "Alles volgens de bestellijst."],
            ["Voorbereiding", "", "Materiaal besteld", "Isolatie", "", "", "", ""],
            ["Voorbereiding", "", "Materiaal besteld", "Dakbedekking", "", "", "", ""],
            ["Voorbereiding", "", "Kraan reserveren", "", "ja", "start", -3, ""],
            ["Uitvoering", "op de werf", "Afbraakwerken", "", "", "", "", ""],
            ["Uitvoering", "", "Opbouwwerken", "", "", "", "", ""],
            ["Oplevering", "en nazorg", "Oplevering met de klant", "", "", "einde", 0, ""],
        ]
        widths = [18, 22, 32, 24, 8, 16, 8, 40]
        if with_order_list:
            header.append("Volgt bestellijst")
            widths.append(16)
            for row in rows:
                row.append("ja" if row[2] == "Materiaal besteld" and not row[3] else "")
        phase_rows = [
            ["Voorbereiding", "vóór de uitvoering", "start", -1],
            ["Uitvoering", "op de werf", "einde", 0],
            ["Oplevering", "en nazorg", "einde", 7],
        ]
        explanation = [
            ["Tabblad Taaksjablonen", "Eén regel per taak of subtaak."],
            ["Fase", "Verplicht. Bestaat de fase nog niet, dan wordt ze aangemaakt. "
                     "De volgorde van de fases is de volgorde waarin ze in de lijst voorkomen."],
            ["Omschrijving fase", "Korte toelichting bij de fase (bv. 'vóór goedkeuring'); "
                                  "één keer per fase invullen volstaat."],
            ["Taak", "Verplicht. Zonder Subtaak: een hoofdtaak van de fase."],
            ["Subtaak", "Ingevuld: een subtaak van de hoofdtaak in de kolom Taak "
                        "(dezelfde naam als die hoofdtaak)."],
            ["Optie", "ja/nee. Een optie staat standaard uit en wordt per project aangezet. "
                      "Subtaken volgen hun hoofdtaak."],
            ["Deadline t.o.v.", "start (startdatum project) of einde (einddatum project); leeg = geen deadline."],
            ["Dagen", "Aantal dagen t.o.v. die datum; negatief = ervoor (bv. -7)."],
            ["Toelichting", "Uitleg bij de taak; komt in de omschrijving van de taak."],
        ]
        if with_order_list:
            explanation.append(["Volgt bestellijst", "ja/nee. De taak wordt automatisch afgevinkt "
                                                     "zodra de bestellijst volledig afgevinkt is."])
        explanation += [
            ["", ""],
            ["Tabblad Fases", "Optioneel: de deadline van de mijlpaal van een fase."],
            ["Fase / Omschrijving", "Zoals hierboven."],
            ["Deadline t.o.v. / Dagen", "start of einde, en het aantal dagen ervoor (negatief) of erna."],
            ["", ""],
            ["Importeren", "Toevoegen en bijwerken: fases en taken met dezelfde naam worden bijgewerkt. "
                           "Vervangen: wat niet in het bestand staat, wordt gearchiveerd."],
        ]
        return xlsx.build_workbook([
            ("Taaksjablonen", header, rows, widths),
            ("Fases", ["Fase", "Omschrijving", "Deadline t.o.v.", "Dagen"], phase_rows, [18, 22, 16, 8]),
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
        lines = [self.env._("Bestand: %s", self.filename or "-")]
        lines.append(self.env._(
            "Fases: %(new)s nieuw, %(upd)s bijgewerkt", new=counters["phases_created"],
            upd=counters["phases_updated"],
        ))
        lines.append(self.env._(
            "Taken: %(new)s nieuw, %(upd)s bijgewerkt", new=counters["tasks_created"],
            upd=counters["tasks_updated"],
        ))
        lines.append(self.env._(
            "Subtaken: %(new)s nieuw, %(upd)s bijgewerkt", new=counters["subtasks_created"],
            upd=counters["subtasks_updated"],
        ))
        if self.mode == "replace":
            lines.append(self.env._(
                "Gearchiveerd: %(phases)s fases, %(tasks)s taken en subtaken",
                phases=counters["phases_archived"], tasks=counters["tasks_archived"],
            ))
        lines.append(self.env._(
            "Bestaande projecten blijven ongewijzigd; nieuwe projecten krijgen deze taken."
        ))
        self.write({"state": "done", "summary": "\n".join(lines)})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Taaksjablonen importeren"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _tectora_import(self, data):
        """Parse the file, then create and update; nothing changes when the
        file has an error."""
        phases, tasks, errors = self._tectora_parse(data)
        if errors:
            raise UserError(
                self.env._("Het bestand werd niet geïmporteerd:\n%s", "\n".join(errors[:30]))
                + ("\n…" if len(errors) > 30 else "")
            )
        if not tasks and not phases:
            raise UserError(self.env._("Geen taken gevonden in het bestand."))
        return self._tectora_apply(phases, tasks)

    def _tectora_parse(self, data):
        """({phase key: values}, [task values with "children"], [errors])."""
        errors = []
        try:
            task_rows = xlsx.read_sheet(
                data, ["Taaksjablonen", "Taken"], TASK_COLUMNS, required_columns=("phase", "task")
            )
            phase_rows = xlsx.read_sheet(data, ["Fases"], PHASE_COLUMNS, required=False) or []
        except ValueError as error:
            raise UserError(str(error)) from None

        def reference(row, label):
            text = xlsx.normalize(xlsx.cell_text(row.get("deadline_reference")))
            if not text:
                return False
            if text not in REFERENCES:
                errors.append(self.env._(
                    "%(label)s rij %(row)s: 'Deadline t.o.v.' moet start of einde zijn, niet '%(value)s'.",
                    label=label, row=row["_row"], value=xlsx.cell_text(row.get("deadline_reference")),
                ))
                return False
            return REFERENCES[text]

        def days(row, label):
            try:
                return xlsx.parse_int(row.get("deadline_offset")) or 0
            except ValueError:
                errors.append(self.env._(
                    "%(label)s rij %(row)s: 'Dagen' moet een geheel getal zijn.", label=label, row=row["_row"],
                ))
                return 0

        def yes_no(row, key, column, label):
            value = xlsx.parse_bool(row.get(key))
            if value is None:
                errors.append(self.env._(
                    "%(label)s rij %(row)s: '%(column)s' moet ja of nee zijn.",
                    label=label, row=row["_row"], column=column,
                ))
                return False
            return value

        phases = {}  # normalized name -> values, in order of appearance

        def phase_for(name, row):
            key = xlsx.normalize(name)
            if key not in phases:
                phases[key] = {"name": name, "sequence": (len(phases) + 1) * 10, "row": row["_row"]}
            return phases[key]

        label = self.env._("Taaksjablonen")
        tasks = {}  # (phase key, task key) -> values
        for row in task_rows:
            phase_name = xlsx.cell_text(row.get("phase"))
            task_name = xlsx.cell_text(row.get("task"))
            if not phase_name or not task_name:
                errors.append(self.env._(
                    "%(label)s rij %(row)s: 'Fase' en 'Taak' zijn verplicht.", label=label, row=row["_row"],
                ))
                continue
            phase = phase_for(phase_name, row)
            subtitle = xlsx.cell_text(row.get("phase_subtitle"))
            if subtitle:
                phase["subtitle"] = subtitle
            key = (xlsx.normalize(phase_name), xlsx.normalize(task_name))
            task = tasks.setdefault(key, {
                "name": task_name, "phase": phase, "children": {}, "sequence": (len(tasks) + 1) * 10,
            })
            values = {
                "deadline_reference": reference(row, label),
                "deadline_offset": days(row, label),
                "description": xlsx.cell_text(row.get("description")),
            }
            subtask_name = xlsx.cell_text(row.get("subtask"))
            if subtask_name:
                task["children"][xlsx.normalize(subtask_name)] = dict(
                    values, name=subtask_name, sequence=(len(task["children"]) + 1) * 10,
                )
            else:
                values["optional"] = yes_no(row, "optional", "Optie", label)
                if "order_list_auto" in row:
                    values["order_list_auto"] = yes_no(row, "order_list_auto", "Volgt bestellijst", label)
                task.update(values)

        label = self.env._("Fases")
        for row in phase_rows:
            name = xlsx.cell_text(row.get("phase"))
            if not name:
                errors.append(self.env._("%(label)s rij %(row)s: 'Fase' is verplicht.", label=label, row=row["_row"]))
                continue
            phase = phase_for(name, row)
            subtitle = xlsx.cell_text(row.get("subtitle"))
            if subtitle:
                phase["subtitle"] = subtitle
            phase["deadline_reference"] = reference(row, label)
            phase["deadline_offset"] = days(row, label)
        return phases, list(tasks.values()), errors

    def _tectora_apply(self, phases, tasks):
        Phase = self.env["tectora.project.phase"].with_context(active_test=False)
        Template = self.env["tectora.task.template"].with_context(active_test=False)
        counters = dict.fromkeys((
            "phases_created", "phases_updated", "phases_archived", "tasks_created", "tasks_updated",
            "subtasks_created", "subtasks_updated", "tasks_archived",
        ), 0)
        existing_phases = {xlsx.normalize(p.name): p for p in Phase.search([], order="active desc, id")}
        phase_records = {}
        for key, values in phases.items():
            vals = {"name": values["name"], "sequence": values["sequence"], "active": True}
            for field in ("subtitle", "deadline_reference", "deadline_offset"):
                if field in values:
                    vals[field] = values[field]
            phase = existing_phases.get(key)
            if phase:
                phase.write(vals)
                counters["phases_updated"] += 1
            else:
                phase = Phase.create(vals)
                counters["phases_created"] += 1
            phase_records[key] = phase

        touched = Template
        for task in tasks:
            phase = phase_records[xlsx.normalize(task["phase"]["name"])]
            vals = {"name": task["name"], "phase_id": phase.id, "sequence": task["sequence"], "active": True}
            for field in ("optional", "deadline_reference", "deadline_offset", "order_list_auto"):
                if field in task and field in Template._fields:
                    vals[field] = task[field]
            if "description" in task:
                vals["description"] = task["description"] or False
            record = self._tectora_find_template(Template, phase, task["name"])
            if record:
                record.write(vals)
                counters["tasks_updated"] += 1
            else:
                record = Template.create(vals)
                counters["tasks_created"] += 1
            touched |= record
            for child in task["children"].values():
                child_vals = {
                    "name": child["name"], "phase_id": phase.id, "parent_id": record.id,
                    "sequence": child["sequence"], "active": True,
                    "deadline_reference": child["deadline_reference"],
                    "deadline_offset": child["deadline_offset"],
                    "description": child["description"] or False,
                }
                sub = self._tectora_find_template(Template, phase, child["name"], parent=record)
                if sub:
                    sub.write(child_vals)
                    counters["subtasks_updated"] += 1
                else:
                    sub = Template.create(child_vals)
                    counters["subtasks_created"] += 1
                touched |= sub

        if self.mode == "replace":
            stale = Template.search([("active", "=", True), ("id", "not in", touched.ids)])
            counters["tasks_archived"] = len(stale)
            stale.write({"active": False})
            stale_phases = Phase.search([
                ("active", "=", True), ("id", "not in", [p.id for p in phase_records.values()]),
            ])
            counters["phases_archived"] = len(stale_phases)
            stale_phases.write({"active": False})
        _logger.info("tectora_project_tasks: task templates imported (%s)", counters)
        return counters

    @api.model
    def _tectora_find_template(self, Template, phase, name, parent=None):
        key = xlsx.normalize(name)
        candidates = Template.search([
            ("phase_id", "=", phase.id), ("parent_id", "=", parent.id if parent else False),
        ], order="active desc, id")
        return candidates.filtered(lambda t: xlsx.normalize(t.name) == key)[:1]
