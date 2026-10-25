"""Demo data for the explainer videos (docs/video_scripts/*/README.md).

Run it in an Odoo shell on a *demo* database, before every recording:

    odoo shell -c odoo.conf -d tectora_demo < tools/video_pipeline/seed_demo.py

It is idempotent: it (re)creates the Familie Peeters case and removes the
roof projects and quotations an earlier take left behind, so every take
starts from the same screen.
"""

DEMO_LOGIN = "admin"  # the user the recording logs in as
DEMO_PARTNER = "Familie Peeters"
DEMO_OPPORTUNITY = "Renovatie plat dak Peeters"

if env.cr.dbname in ("tectora", "production", "prod"):
    raise SystemExit("seed_demo.py refuses to run on a production database")

belgium = env.ref("base.be")
eur = env.ref("base.EUR")
eur.active = True

# `odoo shell` runs as the system user; the videos show the demo login.
user = env["res.users"].search([("login", "=", DEMO_LOGIN)], limit=1)
if not user:
    raise SystemExit(f"no user with login {DEMO_LOGIN!r}")
company = user.company_id
company.write({"name": "Tectora", "country_id": belgium.id, "currency_id": eur.id})
env["product.pricelist"].search([("company_id", "in", (company.id, False))]).currency_id = eur
user.write({"name": "Jan Verbeke", "lang": "nl_BE", "tz": "Europe/Brussels"})
if "tour_enabled" in user._fields:
    user.tour_enabled = False  # no onboarding pointers in the picture

partner = env["res.partner"].search([("name", "=", DEMO_PARTNER)], limit=1)
partner_vals = {
    "name": DEMO_PARTNER,
    "is_company": False,
    "street": "Kerkstraat 14",
    "zip": "8870",
    "city": "Izegem",
    "country_id": belgium.id,
    "email": "familie.peeters@example.com",
    "phone": "+32 51 00 00 00",
    "lang": "nl_BE",
}
if partner:
    partner.write(partner_vals)
else:
    partner = env["res.partner"].create(partner_vals)

# Leftovers of an earlier take.
orders = env["sale.order"].search([("partner_id", "=", partner.id)])
orders.filtered(lambda o: o.state not in ("draft", "cancel"))._action_cancel()
orders.unlink()
env["tectora.roof.project"].search([("partner_id", "=", partner.id)]).unlink()

lead = env["crm.lead"].with_context(active_test=False).search(
    [("name", "=", DEMO_OPPORTUNITY)], limit=1
)
first_stage = env["crm.stage"].search([], order="sequence", limit=1)
lead_vals = {
    "name": DEMO_OPPORTUNITY,
    "type": "opportunity",
    "partner_id": partner.id,
    "street": partner.street,
    "zip": partner.zip,
    "city": partner.city,
    "country_id": belgium.id,
    "expected_revenue": 14500,
    "user_id": user.id,
    "stage_id": first_stage.id,
    "active": True,
}
if lead:
    lead.write(lead_vals)
else:
    lead = env["crm.lead"].create(lead_vals)

env.cr.commit()
print(f"Demo data ready: partner {partner.id}, opportunity {lead.id}")
