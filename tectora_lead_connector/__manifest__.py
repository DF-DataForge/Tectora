# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Leadconnectoren",
    "summary": "Offerteaanvragen van leadplatformen (AannemerOffertes.be) via "
    "een webhook automatisch als lead in de CRM",
    "description": """
Data Forge Dakmeting — Leadconnectoren
======================================
Lead platforms push their quote requests to Odoo with a webhook; every
request becomes a CRM lead without retyping.

* **AannemerOffertes.be**: CRM › Configuration › Leadconnectoren gives the
  webhook URL to mail to the platform. Every POST is verified with the
  HMAC-SHA256 signature (X-Timestamp + X-Token, the shared secret) and the
  age of the timestamp, and answered the way the platform expects: 200 when
  the lead is there, 406 for a request that can never be processed (so the
  platform stops retrying), another code to make it retry.
* The lead gets the contact (salutation, name, e-mail, phone, address,
  language), the kind of work as title, the planning, the extra information
  and the competitors in its notes, and the source, sales team, salesperson,
  tags and type (lead or opportunity) configured on the connector. A known
  e-mail address links the existing contact.
* Every request is kept (CRM › Configuration › Ontvangen leadaanvragen) with
  its content, its state and its lead; the same request received again
  (retries, replays) never makes a second lead, and a request that failed can
  be processed again with one click.
    """,
    "version": "20.0.1.0.0",
    "category": "Sales/CRM",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["crm", "tectora_roof"],
    "data": [
        "security/ir.access.csv",
        "data/utm_source_data.xml",
        "views/lead_connector_views.xml",
        "views/crm_lead_views.xml",
    ],
    "installable": True,
}
