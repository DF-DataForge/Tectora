# -*- coding: utf-8 -*-
import hmac
import json
import time
from hashlib import sha256

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger

SECRET = "s3cr3t-shared-with-aannemeroffertes"

SAMPLE = {
    "id": "9876543BE123456",
    "timestamp": "2026-11-04T10:36:53+01:00",
    "location": "Utrecht",
    "locale": "nl_BE",
    "site": {"name": "aannemeroffertes.be", "description": "AannemerOffertes.be"},
    "type": {"name": "building_house", "description": "Nieuw huis bouwen"},
    "title": "Mr",
    "first_name": " John",
    "last_name": "Doe",
    "fullname": "Mr John Doe",
    "email": "john.doe@example.org",
    "phonenumber": "+3238085000",
    "address": {
        "address": "Godebaldkwartier 371",
        "postal_code": "3511 DT",
        "locality": "Utrecht",
        "dependent_locality": None,
        "administrative_area": None,
        "country_code": "NL",
    },
    "competitors": ["Competitor 1", "Competitor 2", "Competitor 3"],
    "date_planned": "2 dec 2026, 10:36:53",
    "description": "Additional available information on this lead",
    "raw": {
        "google_from_link": {
            "value": "http://maps.google.nl/maps?q=Godebaldkwartier+371,3511+DT,Utrecht",
            "rawValue": None,
        },
    },
}


def sign(secret, timestamp=None, token="95adf57f30ae9161c11005452857fe25f61e1537"):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    signature = hmac.new(secret.encode(), f"{timestamp}{token}".encode(), sha256).hexdigest()
    return {"X-Timestamp": timestamp, "X-Token": token, "X-Signature": signature}


class LeadConnectorCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team = cls.env["crm.team"].create({"name": "Daken"})
        cls.tag = cls.env["crm.tag"].create({"name": "AannemerOffertes"})
        cls.connector = cls.env["tectora.lead.connector"].create({
            "name": "AannemerOffertes.be",
            "secret": SECRET,
            "team_id": cls.team.id,
            "tag_ids": [(6, 0, cls.tag.ids)],
        })


@tagged("post_install", "-at_install")
class TestAannemerOffertesLead(LeadConnectorCase):

    def test_lead_from_sample(self):
        log = self.connector._receive(dict(SAMPLE), token="abc")
        self.assertEqual(log.state, "done", log.error)
        lead = log.lead_id
        self.assertEqual(lead.name, "Nieuw huis bouwen - John Doe - Utrecht")
        self.assertEqual(lead.type, "opportunity")
        self.assertEqual(lead.contact_name, "John Doe")
        self.assertEqual(lead.email_from, "john.doe@example.org")
        self.assertEqual(lead.phone, "+3238085000")
        self.assertEqual(lead.street, "Godebaldkwartier 371")
        self.assertEqual(lead.zip, "3511 DT")
        self.assertEqual(lead.city, "Utrecht")
        self.assertEqual(lead.country_id.code, "NL")
        self.assertEqual(lead.team_id, self.team)
        self.assertEqual(lead.tag_ids, self.tag)
        self.assertEqual(
            lead.source_id,
            self.env.ref("tectora_lead_connector.utm_source_lead_aannemeroffertes"),
        )
        self.assertEqual(lead.tectora_title_id, self.env.ref("tectora_roof.partner_title_mister"))
        for text in ("Additional available information", "2 dec 2026", "Competitor 2",
                     "9876543BE123456", "maps.google.nl"):
            self.assertIn(text, str(lead.description))

    def test_same_request_twice_one_lead(self):
        first = self.connector._receive(dict(SAMPLE))
        again = self.connector._receive(dict(SAMPLE))
        self.assertEqual(first, again)
        self.assertEqual(again.duplicate_count, 1)
        self.assertEqual(
            self.env["crm.lead"].search_count([("lead_connector_log_ids", "in", first.ids)]), 1
        )

    def test_existing_contact_is_linked_and_title_goes_to_partner(self):
        partner = self.env["res.partner"].create(
            {"name": "John Doe", "email": "John.Doe@example.org"}
        )
        lead = self.connector._receive(dict(SAMPLE)).lead_id
        self.assertEqual(lead.partner_id, partner)

        other = dict(SAMPLE, id="2", email="new@example.org", title="Mevr.")
        lead = self.connector._receive(other).lead_id
        self.assertFalse(lead.partner_id)
        self.assertEqual(lead.tectora_title_id, self.env.ref("tectora_roof.partner_title_madam"))
        customer = lead._create_customer()
        self.assertEqual(customer.tectora_title_id, lead.tectora_title_id)

    def test_minimal_payload(self):
        log = self.connector._receive({"id": "min-1", "email": "x@example.org"})
        self.assertEqual(log.state, "done", log.error)
        self.assertEqual(log.lead_id.name, "Offerteaanvraag")

    def test_failure_is_kept_and_can_be_retried(self):
        payload = dict(SAMPLE, id="broken")
        original = type(self.connector)._aannemeroffertes_lead_values

        def boom(connector, payload):
            raise ValueError("boom")

        type(self.connector)._aannemeroffertes_lead_values = boom
        try:
            with mute_logger("odoo.addons.tectora_lead_connector.models.lead_connector_log"):
                log = self.connector._receive(payload)
        finally:
            type(self.connector)._aannemeroffertes_lead_values = original
        self.assertEqual(log.state, "error")
        self.assertIn("boom", log.error)
        self.assertFalse(log.lead_id)
        log.action_retry()
        self.assertEqual(log.state, "done")
        self.assertTrue(log.lead_id)

    def test_signature(self):
        from odoo.addons.tectora_lead_connector.models.lead_connector import LeadConnectorError
        headers = sign(SECRET)
        self.connector._check_signature(
            headers["X-Timestamp"], headers["X-Token"], headers["X-Signature"]
        )
        # the sample from the documentation, with its secret unknown, fails
        with self.assertRaises(LeadConnectorError):
            self.connector._check_signature(
                headers["X-Timestamp"], headers["X-Token"], "55af9adf2a187bc868b95dcac0a4256"
            )
        old = sign(SECRET, timestamp=int(time.time()) - 25 * 3600)
        with self.assertRaises(LeadConnectorError):
            self.connector._check_signature(old["X-Timestamp"], old["X-Token"], old["X-Signature"])
        self.connector.max_age_hours = 0
        self.connector._check_signature(old["X-Timestamp"], old["X-Token"], old["X-Signature"])


@tagged("post_install", "-at_install")
class TestAannemerOffertesWebhook(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connector = cls.env["tectora.lead.connector"].create({
            "name": "AannemerOffertes.be",
            "secret": SECRET,
        })
        cls.path = f"/tectora/leads/aannemeroffertes/{cls.connector.access_token}"

    def post(self, body, headers=None, path=None):
        data = body if isinstance(body, (bytes, str)) else json.dumps(body)
        return self.url_open(
            path or self.path,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )

    def test_webhook(self):
        response = self.post(SAMPLE, sign(SECRET))
        self.assertEqual(response.status_code, 200, response.text)
        lead = self.env["crm.lead"].browse(response.json()["lead_id"])
        self.assertEqual(lead.email_from, "john.doe@example.org")
        # retry of the same request: 200, no new lead
        response = self.post(SAMPLE, sign(SECRET, token="b" * 40))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lead_id"], lead.id)

    def test_webhook_refusals(self):
        self.assertEqual(self.post(SAMPLE, sign("wrong")).status_code, 401)
        self.assertEqual(self.post(SAMPLE).status_code, 401)
        self.assertEqual(self.post("not json", sign(SECRET)).status_code, 406)
        self.assertEqual(self.post({"no": "id"}, sign(SECRET)).status_code, 406)
        self.assertEqual(
            self.post(SAMPLE, sign(SECRET), path="/tectora/leads/aannemeroffertes/nope").status_code,
            404,
        )
        self.assertFalse(self.connector.log_ids)
