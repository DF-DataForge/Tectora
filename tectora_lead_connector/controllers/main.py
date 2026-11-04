# -*- coding: utf-8 -*-
"""Webhook endpoint of the lead connectors.

    POST /tectora/leads/<provider>/<access token>

Answers, following the AannemerOffertes.be webhook contract:

* 200 -- the request is stored and has its lead (also for a request that was
  received before: retries and replays never make a second lead);
* 406 -- the request is refused for good (no JSON object, no id): the
  platform does not retry;
* 401 -- the signature does not match; 404 -- unknown or archived connector;
  500 -- the lead could not be created (the error is on the log). For these
  the platform retries (up to ~17 hours), giving time to fix the setup.
"""
import json
import logging

from odoo import http
from odoo.http import request

from odoo.addons.tectora_lead_connector.models.lead_connector import (
    WEBHOOK_ROUTE,
    LeadConnectorError,
)

_logger = logging.getLogger(__name__)


class TectoraLeadConnectorController(http.Controller):

    @http.route(
        f"{WEBHOOK_ROUTE}/<string:provider>/<string:access_token>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def tectora_lead_webhook(self, provider, access_token, **kwargs):
        connector = (
            request.env["tectora.lead.connector"]
            .sudo()
            .search(
                [("provider", "=", provider), ("access_token", "=", access_token)],
                limit=1,
            )
        )
        if not connector:
            return self._answer(404, "Unknown connector")

        headers = request.httprequest.headers
        token = headers.get("X-Token")
        try:
            connector._check_signature(
                headers.get("X-Timestamp"), token, headers.get("X-Signature")
            )
            try:
                payload = json.loads(request.httprequest.get_data() or b"null")
            except ValueError:
                raise LeadConnectorError("Body is not valid JSON", permanent=True) from None
            log = connector.with_company(connector.company_id)._receive(payload, token=token)
        except LeadConnectorError as error:
            _logger.warning("Lead connector %s refused a request: %s", connector.name, error)
            return self._answer(406 if error.permanent else 401, str(error))

        if log.state != "done":
            return self._answer(500, "Lead could not be created", log.external_id)
        return self._answer(200, "OK", log.external_id, log.lead_id.id)

    @staticmethod
    def _answer(status, message, external_id=None, lead_id=None):
        body = {"status": status, "message": message}
        if external_id:
            body["id"] = external_id
        if lead_id:
            body["lead_id"] = lead_id
        return request.make_json_response(body, status=status)
