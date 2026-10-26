# -*- coding: utf-8 -*-
from odoo import _, fields, models

from ..models.import_job import _norm


class QuotationImport(models.TransientModel):
    """Checks the export and hands it to an import job, which runs in the
    background: a large export takes longer than a web request may last."""

    _name = "tectora.quotation.import"
    _inherit = ["tectora.quotation.import.options"]
    _description = "Offertes importeren uit het oude systeem"

    file = fields.Binary(string="Bestand (.xlsx)", required=True, attachment=False)
    filename = fields.Char(string="Bestandsnaam")
    dry_run = fields.Boolean(
        string="Testrun (enkel controleren)",
        help="Leest het bestand en toont wat de import zou doen (aantal "
        "offertes per status, nieuwe klanten, gekoppelde lijnen, ...), "
        "zonder iets aan te maken.",
    )
    state = fields.Selection(
        [("draft", "Concept"), ("done", "Uitgevoerd")], default="draft"
    )
    summary = fields.Text(string="Resultaat", readonly=True)

    def action_import(self):
        self.ensure_one()
        quotes, stats = self._parse()
        self._statuses(quotes)
        if self.dry_run:
            self.write({"state": "done", "summary": self._preview(quotes, stats)})
            return {
                "type": "ir.actions.act_window",
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
                "context": self.env.context,
            }
        values = {
            name: self[name].id if isinstance(self[name], models.BaseModel) else self[name]
            for name in self.OPTION_FIELDS
        }
        job = self.env["tectora.quotation.import.job"].create(dict(
            values,
            name=_("%(file)s (%(count)s offertes)",
                   file=self.filename or _("Import"), count=len(quotes)),
            file=self.file,
            filename=self.filename,
            quote_count=len(quotes),
        ))
        job._trigger_cron()
        return {
            "type": "ir.actions.act_window",
            "res_model": job._name,
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }

    def _preview(self, quotes, stats):
        """What the import would do, without writing anything."""
        statuses = self._statuses(quotes)
        lookups = self._prepare_lookups()
        existing = self._existing_orders(quotes)
        Status = self.env["tectora.quotation.import.status"]
        per_status = {}
        known = new_partners = matched = generic = texts = 0
        missing_taxes = set()
        total = 0.0
        for quote in quotes:
            if quote["number"] in existing:
                known += 1
                continue
            per_status[quote["status"]] = per_status.get(quote["status"], 0) + 1
            total += quote["total"]
            customer = quote["customer"]
            name_key = (_norm(customer["name"]), customer["zip"])
            if not (customer["vat"] and customer["vat"] in lookups["partners_by_vat"]) \
                    and name_key not in lookups["partners_by_name"]:
                new_partners += 1
                lookups["partners_by_name"][name_key] = True
                if customer["vat"]:
                    lookups["partners_by_vat"][customer["vat"]] = True
            for line in quote["lines"]:
                if line["kind"] == "text":
                    texts += 1
                    continue
                if _norm(line["description"]) in lookups["products"]:
                    matched += 1
                else:
                    generic += 1
                if not self._tax(line["vat_rate"], lookups):
                    missing_taxes.add(line["vat_rate"])

        order_states = dict(Status._fields["order_state"].selection)
        lines = [
            _("TESTRUN: er werd niets aangemaakt."),
            "",
            _("Bestand: %(file)s — %(quotes)s offertes, %(rows)s lijnen",
              file=self.filename or "-", quotes=len(quotes), rows=stats["rows"]),
            _("%(new)s nieuwe offertes (€ %(total)s excl. btw), %(known)s al in Odoo (%(mode)s)",
              new=sum(per_status.values()), total="{:,.2f}".format(total),
              known=known, mode=dict(self._fields["existing_mode"].selection)[self.existing_mode]),
        ]
        for status_name, count in sorted(per_status.items()):
            status = statuses[Status._key(status_name)]
            lines.append("    %s: %s → %s, verkoopkans %s" % (
                status_name, count, order_states[status.order_state],
                status._resolve_stage(self.team_id).name or "-",
            ))
        lines += [
            _("%s nieuwe klanten", new_partners),
            _("%(matched)s lijnen op een werkpost uit de catalogus, %(generic)s op "
              "de werkpost 'oud systeem'", matched=matched, generic=generic),
        ]
        if stats["multiplied"]:
            lines.append(_("%s lijnen vermenigvuldigd (bedrag = veelvoud van aantal × prijs)",
                           stats["multiplied"]))
        if stats["repriced"]:
            lines.append(_("%s lijnen waarvan de eenheidsprijs uit het bedrag herrekend wordt",
                           stats["repriced"]))
        if texts:
            lines.append(_("%(n)s titel- en tekstregels (%(what)s)", n=texts,
                           what=dict(self._fields["text_lines"].selection)[self.text_lines]))
        if missing_taxes:
            lines.append(_("Geen verkoopbtw gevonden voor: %s",
                           ", ".join("%g%%" % rate for rate in sorted(missing_taxes))))
        return "\n".join(lines)
