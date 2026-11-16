# -*- coding: utf-8 -*-
"""Every quote request a lead connector received, with the lead it became."""
import json
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class TectoraLeadConnectorLog(models.Model):
    _name = "tectora.lead.connector.log"
    _description = "Ontvangen leadaanvraag"
    _order = "create_date desc, id desc"
    _rec_name = "external_id"

    connector_id = fields.Many2one(
        "tectora.lead.connector", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(related="connector_id.company_id", store=True)
    provider = fields.Selection(related="connector_id.provider")
    external_id = fields.Char(string="Aanvraag-ID", required=True, index=True)
    token = fields.Char(string="X-Token", readonly=True)
    payload = fields.Json(readonly=True)
    payload_text = fields.Text(string="Inhoud", compute="_compute_payload_text")
    state = fields.Selection(
        [("new", "Nieuw"), ("done", "Verwerkt"), ("error", "Fout")],
        default="new",
        required=True,
        readonly=True,
    )
    error = fields.Text(readonly=True)
    duplicate_count = fields.Integer(
        string="Opnieuw ontvangen",
        readonly=True,
        help="Hoe vaak dezelfde aanvraag nog binnenkwam nadat ze verwerkt was "
        "(herhaalde webhook); die maken geen nieuwe lead.",
    )
    lead_id = fields.Many2one("crm.lead", readonly=True, ondelete="set null", index=True)

    _external_id_unique = models.Constraint(
        "UNIQUE(connector_id, external_id)",
        "Een aanvraag wordt per connector maar één keer bewaard.",
    )

    def _compute_payload_text(self):
        for log in self:
            log.payload_text = (
                json.dumps(log.payload, indent=2, ensure_ascii=False)
                if log.payload
                else False
            )

    def _process(self):
        """Create the lead of each log that does not have one yet.

        Errors are kept on the log (state "error") instead of raised, so the
        log itself survives; the caller decides what to answer.
        """
        for log in self:
            if log.lead_id:
                log.state = "done"
                continue
            connector = log.connector_id
            builder = getattr(connector, f"_{connector.provider}_lead_values")
            try:
                with self.env.cr.savepoint():
                    values = builder(log.payload or {})
                    lead = (
                        self.env["crm.lead"]
                        .with_company(connector.company_id)
                        .with_context(mail_create_nosubscribe=True)
                        .create(values)
                    )
                    lead.message_post(
                        body=_(
                            "Lead ontvangen via %(connector)s (aanvraag %(ref)s).",
                            connector=connector.name,
                            ref=log.external_id,
                        )
                    )
            except Exception as error:  # noqa: BLE001 -- kept on the log
                _logger.exception(
                    "Lead connector %s: request %s could not be processed",
                    connector.name, log.external_id,
                )
                log.write({"state": "error", "error": str(error)})
            else:
                log.write({"state": "done", "error": False, "lead_id": lead.id})

    def action_retry(self):
        if self.filtered(lambda log: log.state == "done"):
            raise UserError(_("Deze aanvraag is al verwerkt."))
        self._process()
        failed = self.filtered(lambda log: log.state == "error")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "danger" if failed else "success",
                "message": failed[0].error if failed else _("Lead aangemaakt."),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_open_lead(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "res_id": self.lead_id.id,
            "view_mode": "form",
        }
