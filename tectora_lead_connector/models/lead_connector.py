# -*- coding: utf-8 -*-
"""Lead connectors: external lead platforms that push quote requests.

One record per platform account. The platform POSTs every new quote request
to the connector's webhook URL (see ``controllers/main.py``); the request is
checked, logged (``tectora.lead.connector.log``) and turned into a CRM lead.
"""
import hmac
import logging
import secrets
import time
from hashlib import sha256

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.tools import email_normalize

_logger = logging.getLogger(__name__)

WEBHOOK_ROUTE = "/tectora/leads"


class LeadConnectorError(Exception):
    """A request the connector refuses.

    ``permanent`` requests are answered with 406 so the platform stops
    retrying (malformed payloads); the others with 401 so a mistake in the
    configuration (wrong secret) can be fixed before the retries run out.
    """

    def __init__(self, message, permanent=False):
        super().__init__(message)
        self.permanent = permanent


class TectoraLeadConnector(models.Model):
    _name = "tectora.lead.connector"
    _description = "Leadconnector"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    provider = fields.Selection(
        [("aannemeroffertes", "AannemerOffertes.be")],
        required=True,
        default="aannemeroffertes",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    access_token = fields.Char(
        string="URL-token",
        groups="sales_team.group_sale_manager",
        required=True,
        copy=False,
        default=lambda self: secrets.token_urlsafe(24),
        help="Geheim deel van de webhook-URL. Opnieuw genereren maakt de oude "
        "URL ongeldig.",
    )
    webhook_url = fields.Char(
        compute="_compute_webhook_url", groups="sales_team.group_sale_manager"
    )
    secret = fields.Char(
        string="Ondertekeningsgeheim",
        copy=False,
        groups="sales_team.group_sale_manager",
        help="De sleutel waarmee het platform elke webhook ondertekent "
        "(HMAC-SHA256 van X-Timestamp + X-Token). Leeg = geen controle op de "
        "handtekening (enkel om te testen).",
    )
    max_age_hours = fields.Integer(
        string="Maximale ouderdom (uur)",
        default=24,
        help="Weiger aanvragen waarvan X-Timestamp meer dan dit aantal uur "
        "afwijkt van nu. 0 = niet controleren. Ruim genoeg houden: het "
        "platform probeert tot ongeveer 17 uur lang opnieuw.",
    )

    # what the leads get
    lead_type = fields.Selection(
        [("lead", "Lead"), ("opportunity", "Verkoopkans")],
        string="Aanmaken als",
        required=True,
        default="opportunity",
    )
    team_id = fields.Many2one(
        "crm.team",
        string="Verkoopteam",
        domain="[('company_id', 'in', (company_id, False))]",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Verkoper",
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
    )
    source_id = fields.Many2one(
        "utm.source",
        string="Bron",
        default=lambda self: self.env.ref(
            "tectora_lead_connector.utm_source_lead_aannemeroffertes",
            raise_if_not_found=False,
        ),
    )
    medium_id = fields.Many2one("utm.medium", string="Medium")
    tag_ids = fields.Many2many("crm.tag", string="Labels")

    log_ids = fields.One2many("tectora.lead.connector.log", "connector_id")
    log_count = fields.Integer(compute="_compute_log_count")
    lead_count = fields.Integer(compute="_compute_log_count")

    _access_token_unique = models.Constraint(
        "UNIQUE(access_token)", "Het URL-token moet uniek zijn."
    )

    @api.depends("access_token", "provider")
    def _compute_webhook_url(self):
        for connector in self:
            base_url = connector.get_base_url()
            connector.webhook_url = (
                f"{base_url}{WEBHOOK_ROUTE}/{connector.provider}/{connector.access_token}"
                if connector.access_token
                else False
            )

    def _compute_log_count(self):
        groups = self.env["tectora.lead.connector.log"]._read_group(
            [("connector_id", "in", self.ids)],
            ["connector_id"],
            ["__count", "lead_id:count"],
        )
        counts = {connector.id: (total, leads) for connector, total, leads in groups}
        for connector in self:
            connector.log_count, connector.lead_count = counts.get(connector.id, (0, 0))

    def action_regenerate_token(self):
        for connector in self:
            connector.access_token = secrets.token_urlsafe(24)

    def action_view_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Ontvangen aanvragen"),
            "res_model": "tectora.lead.connector.log",
            "view_mode": "list,form",
            "domain": [("connector_id", "=", self.id)],
            "context": {"default_connector_id": self.id},
        }

    def action_view_leads(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Leads"),
            "res_model": "crm.lead",
            "view_mode": "list,form",
            "domain": [("id", "in", self.log_ids.lead_id.ids)],
            "context": {"active_test": False},
        }

    # ------------------------------------------------------------ webhook
    def _check_signature(self, timestamp, token, signature):
        """Verify the headers of a webhook POST (AannemerOffertes.be scheme).

        signature = hex(HMAC-SHA256(secret, X-Timestamp + X-Token))
        """
        self.ensure_one()
        secret = self.sudo().secret
        if not secret:
            return
        if not (timestamp and token and signature):
            raise LeadConnectorError("Missing signature headers")
        expected = hmac.new(
            secret.encode(), f"{timestamp}{token}".encode(), sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature.strip().lower()):
            raise LeadConnectorError("Invalid signature")
        if self.max_age_hours:
            try:
                age = abs(time.time() - int(timestamp))
            except ValueError:
                raise LeadConnectorError("Invalid timestamp") from None
            if age > self.max_age_hours * 3600:
                raise LeadConnectorError("Timestamp too far from current time")

    def _receive(self, payload, token=None):
        """Log a received quote request and turn it into a lead.

        Returns the log record. A request that was received before (same
        external id) and already has its lead is not processed again, so
        retries and replays never create a second lead.
        """
        self.ensure_one()
        if not isinstance(payload, dict):
            raise LeadConnectorError("Payload is not a JSON object", permanent=True)
        external_id = str(payload.get("id") or "").strip()
        if not external_id:
            raise LeadConnectorError("Payload has no id", permanent=True)

        Log = self.env["tectora.lead.connector.log"]
        log = Log.search(
            [("connector_id", "=", self.id), ("external_id", "=", external_id)],
            limit=1,
        )
        if log and log.state == "done":
            log.duplicate_count += 1
            return log
        values = {"payload": payload, "token": token, "state": "new", "error": False}
        if log:
            log.write(values)
        else:
            log = Log.create(
                dict(values, connector_id=self.id, external_id=external_id)
            )
        log._process()
        return log

    # ------------------------------------------------- AannemerOffertes.be
    def _aannemeroffertes_lead_values(self, payload):
        """crm.lead values for a New Quote Request payload."""
        self.ensure_one()
        address = payload.get("address") or {}
        request_type = payload.get("type") or {}
        site = payload.get("site") or {}

        first = (payload.get("first_name") or "").strip()
        last = (payload.get("last_name") or "").strip()
        contact_name = " ".join(filter(None, [first, last])) or (
            payload.get("fullname") or ""
        ).strip()
        type_label = (request_type.get("description") or request_type.get("name") or "").strip()
        locality = (address.get("locality") or payload.get("location") or "").strip()
        name = " - ".join(
            filter(None, [type_label or _("Offerteaanvraag"), contact_name, locality])
        )

        email = (payload.get("email") or "").strip()
        country = self.env["res.country"]
        if address.get("country_code"):
            country = country.search(
                [("code", "=ilike", address["country_code"].strip())], limit=1
            )

        values = {
            "name": name,
            "type": self.lead_type,
            "company_id": self.company_id.id,
            "contact_name": contact_name or False,
            "email_from": email or False,
            "phone": (payload.get("phonenumber") or "").strip() or False,
            "street": (address.get("address") or "").strip() or False,
            "street2": (address.get("dependent_locality") or "").strip() or False,
            "zip": (address.get("postal_code") or "").strip() or False,
            "city": locality or False,
            "country_id": country.id or False,
            "description": self._aannemeroffertes_description(payload, site, type_label),
            "source_id": self.source_id.id or False,
            "medium_id": self.medium_id.id or False,
            "tag_ids": [fields.Command.set(self.tag_ids.ids)],
        }
        if self.team_id:
            values["team_id"] = self.team_id.id
        if self.user_id:
            values["user_id"] = self.user_id.id
        elif not self.team_id:
            # no owner configured: leave it to the team / assignment rules
            values["user_id"] = False

        title = self._match_title(payload.get("title"))
        if title:
            values["tectora_title_id"] = title.id
        lang = self._match_lang(payload.get("locale"))
        if lang:
            values["lang_id"] = lang.id
        partner = self._match_partner(email)
        if partner:
            values["partner_id"] = partner.id
        return values

    def _aannemeroffertes_description(self, payload, site, type_label):
        rows = [
            (_("Aanvraag"), payload.get("id")),
            (_("Platform"), site.get("description") or site.get("name")),
            (_("Soort werk"), type_label),
            (_("Ontvangen op"), payload.get("timestamp")),
            (_("Gewenste planning"), payload.get("date_planned")),
            (_("Locatie"), payload.get("location")),
            (_("Ook verstuurd naar"), ", ".join(
                str(c) for c in payload.get("competitors") or [] if c
            )),
        ]
        maps = ((payload.get("raw") or {}).get("google_from_link") or {}).get("value")
        parts = []
        if payload.get("description"):
            parts.append(Markup("<p>%s</p>") % escape(payload["description"]).replace(
                "\n", Markup("<br/>")
            ))
        items = Markup("").join(
            Markup("<li><strong>%s:</strong> %s</li>") % (label, value)
            for label, value in rows
            if value
        )
        if maps and str(maps).startswith(("http://", "https://")):
            items += Markup('<li><a href="%s" target="_blank">%s</a></li>') % (
                maps,
                _("Bekijk op de kaart"),
            )
        if items:
            parts.append(Markup("<ul>%s</ul>") % items)
        return Markup("").join(parts) or False

    # ------------------------------------------------------------ helpers
    def _match_title(self, title):
        """The salutation (tectora.partner.title) for "Mr", "Mrs", "Dhr", ..."""
        Title = self.env["tectora.partner.title"]
        title = (title or "").strip().rstrip(".").lower()
        if not title:
            return Title
        aliases = {
            "mr": "male", "mister": "male", "dhr": "male", "de heer": "male",
            "meneer": "male", "m": "male", "monsieur": "male", "herr": "male",
            "mrs": "female", "ms": "female", "miss": "female", "mevr": "female",
            "mevrouw": "female", "mme": "female", "madame": "female", "frau": "female",
        }
        gender_refs = {
            "male": "tectora_roof.partner_title_mister",
            "female": "tectora_roof.partner_title_madam",
        }
        candidates = [title, f"{title}."]
        match = Title.search(
            ["|", ("shortcut", "in", candidates), ("name", "in", candidates)], limit=1
        ) or Title.search(
            ["|", ("shortcut", "=ilike", f"{title}."), ("name", "=ilike", title)], limit=1
        )
        if not match and title in aliases:
            match = self.env.ref(gender_refs[aliases[title]], raise_if_not_found=False)
            match = match if match and match.active else Title
        return match

    def _match_lang(self, locale):
        if not locale:
            return self.env["res.lang"]
        Lang = self.env["res.lang"]
        code = locale.strip().replace("-", "_")
        lang = Lang.search([("code", "=", code)], limit=1)
        if not lang:
            lang = Lang.search([("iso_code", "=", code.split("_")[0])], limit=1)
        return lang

    def _match_partner(self, email):
        normalized = email_normalize(email)
        if not normalized:
            return self.env["res.partner"]
        return self.env["res.partner"].search(
            [
                ("email_normalized", "=", normalized),
                ("company_id", "in", (self.company_id.id, False)),
            ],
            order="is_company, id",
            limit=1,
        )
