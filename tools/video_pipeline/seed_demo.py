"""Demo data for the explainer videos (docs/video_scripts/standaard/README.md).

Run it in an Odoo shell on a *demo* database, before every take:

    VIDEO_STAGE=quote odoo shell -c odoo.conf -d tectora_video < tools/video_pipeline/seed_demo.py

It is idempotent: it removes what an earlier take of the Familie Peeters
case left behind and rebuilds the case up to the point where the video
starts. ``VIDEO_STAGE`` (set by make_video.py from the storyboard's
``stage``) picks that point:

* ``lead_new``       the customer exists, the opportunity does not (video 01)
* ``lead``           opportunity without notes or labels (video 02)
* ``lead_notes``     opportunity with notes, labels and a planned call (03, 04)
* ``quote``          a saved quotation from the template (05, 06, 08)
* ``quote_norecalc`` the same, with hercalculatie still off on the PIR board (07)
* ``project``        the quotation confirmed: project, tasks, work block (09–11)
* ``timer``          as ``project``, plus a running site timer (11)
"""

import os
from datetime import datetime, time, timedelta

DEMO_LOGIN = "admin"            # the office user the videos are recorded as
FOREMAN_LOGIN = "koen.devos@tectora.example"   # portal user of video 11
FOREMAN_PASSWORD = "koen"
DEMO_PARTNER = "Familie Peeters"
DEMO_OPPORTUNITY = "Renovatie plat dak Peeters"
TEMPLATE = "Renovatie plat dak - roofing 1 laag, PIR 12 cm, EPDM 1,1 mm, 2-delige dakrand"
NOTES = (
    "<p><b>Dak:</b> plat, ± 100 m², bestaande roofing 1 laag.</p>"
    "<p><b>Probleem:</b> lekt aan de lichtkoepel.</p>"
    "<p><b>Wens:</b> isoleren + EPDM.</p>"
    "<p><b>Extra:</b> lichtkoepel vervangen.</p>"
    "<p><b>Toegang:</b> via de oprit, geen stelling nodig.</p>"
    "<p><b>Timing:</b> vóór de winter. <b>Budget:</b> ± € 15.000.</p>"
)
# Quotation quantities after the measurement (video 04).
MEASURED = {"S00177": 96, "S00400": 38, "S00182": 38, "S00043": 38, "S00023": 38}
STAGES = ("lead_new", "lead", "lead_notes", "quote", "quote_norecalc", "project", "timer")

# No field tracking: it only adds chatter noise to seeded data, and it trips
# over records the clean-up below deletes.
env = env(context=dict(env.context, tracking_disable=True, mail_notrack=True))

stage = os.environ.get("VIDEO_STAGE") or "lead_new"
if stage not in STAGES:
    raise SystemExit(f"unknown VIDEO_STAGE {stage!r}; one of {', '.join(STAGES)}")
if env.cr.dbname in ("tectora", "production", "prod"):
    raise SystemExit("seed_demo.py refuses to run on a production database")

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
# make_video.py passes the folder; piped into `odoo shell` there is no __file__.
ASSETS = next(
    (p for p in (os.environ.get("VIDEO_ASSETS", ""), os.path.join(HERE, "assets"),
                 os.path.join(os.getcwd(), "tools", "video_pipeline", "assets"))
     if p and os.path.isdir(p)),
    None,
)
today = datetime.combine(datetime.now().date(), time())


def ref(xmlid):
    return env.ref(xmlid, raise_if_not_found=False)


def upsert(model, domain, values):
    record = env[model].with_context(active_test=False).search(domain, limit=1)
    if record:
        record.write(values)
    else:
        record = env[model].create(values)
    return record


def product(code):
    return env["product.product"].search([("default_code", "=", code)], limit=1)


# ------------------------------------------------------------------ company
belgium = ref("base.be")
eur = ref("base.EUR")
eur.active = True
user = env["res.users"].search([("login", "=", DEMO_LOGIN)], limit=1)
if not user:
    raise SystemExit(f"no user with login {DEMO_LOGIN!r}")
company = user.company_id
company.write({"name": "Tectora", "country_id": belgium.id, "currency_id": eur.id})
letterhead = ref("tectora_report_layout.report_layout_tectora_letterhead")
if letterhead:
    company.external_report_layout_id = letterhead.view_id
env["product.pricelist"].search([("company_id", "in", (company.id, False))]).currency_id = eur
user.write({"name": "Jan Verbeke", "lang": "nl_BE", "tz": "Europe/Brussels",
            "email": "jan.verbeke@tectora.example"})
if "tour_enabled" in user._fields:
    user.tour_enabled = False
env.ref("base.user_root").name = "OdooBot"
# No automatic lead enrichment: it posts an OdooBot message on every lead.
# (the "manual" setting in CRM is this scheduled action switched off).
enrich = env.ref("crm_iap_enrich.ir_cron_lead_enrichment", raise_if_not_found=False)
if enrich:
    enrich.sudo().active = False

# Hour norms per works item (tectora_boms ships them; load them once).
Templates = env["product.template"]
if "tectora_hours_execution_per_uom" in Templates._fields and hasattr(Templates, "_tectora_import_labour_norms") \
        and not Templates.search_count([("tectora_hours_execution_per_uom", ">", 0)]):
    Templates._tectora_import_labour_norms()

# Quotation cover and closing page (Quote Builder).
template = env["sale.order.template"].search([("name", "=", TEMPLATE)], limit=1)
if ASSETS and "quotation.document" in env:
    for name, kind in (("Voorblad Tectora", "header"), ("Achterblad Tectora", "footer")):
        file = os.path.join(ASSETS, "offerte_voorblad.pdf" if kind == "header" else "offerte_achterblad.pdf")
        with open(file, "rb") as handle:
            raw = handle.read()
        document = env["quotation.document"].with_context(active_test=False).search([("name", "=", name)], limit=1)
        if document:
            document.ir_attachment_id.write({"raw": raw})
        else:
            attachment = env["ir.attachment"].create({
                "name": name, "raw": raw, "mimetype": "application/pdf",
                "res_model": "quotation.document"})
            document = env["quotation.document"].create({"ir_attachment_id": attachment.id,
                                                         "document_type": kind})
        document.write({"document_type": kind, "add_by_default": True, "active": True,
                        "quotation_template_ids": [(6, 0, template.ids)]})

# ---------------------------------------------------------------- partners
title_family = ref("tectora_roof.partner_title_family")
partner = upsert("res.partner", [("name", "=", DEMO_PARTNER)], {
    "name": DEMO_PARTNER, "is_company": False, "street": "Kerkstraat 14", "zip": "8870",
    "city": "Izegem", "country_id": belgium.id, "email": "familie.peeters@example.com",
    "phone": "+32 51 00 00 00", "lang": "nl_BE",
    "tectora_title_id": False if stage == "lead_new" else title_family.id,
})
suppliers = {
    name: upsert("res.partner", [("name", "=", name)], {
        "name": name, "is_company": True, "supplier_rank": 1, "country_id": belgium.id,
        "city": city, "email": f"verkoop@{slug}.example",
    })
    for name, city, slug in (("Dakcenter Vlaanderen", "Roeselare", "dakcenter"),
                             ("Bouwmaterialen De Smet", "Kortrijk", "desmet"))
}

# ------------------------------------------------- leftovers of earlier takes
projects = env["project.project"].with_context(active_test=False).search([("partner_id", "=", partner.id)])
orders = env["sale.order"].search([("partner_id", "=", partner.id)])
purchases = env["purchase.order"].search(
    ["|", ("origin", "ilike", "Peeters"), ("project_id", "in", projects.ids)]
) if "project_id" in env["purchase.order"]._fields else env["purchase.order"].search([("origin", "ilike", "Peeters")])
purchases.filtered(lambda p: p.state not in ("cancel",)).button_cancel()
purchases.unlink()
pickings = orders.picking_ids if "picking_ids" in orders._fields else env["stock.picking"]
pickings.filtered(lambda p: p.state not in ("done", "cancel")).action_cancel()
roofs = env["tectora.roof.project"].with_context(active_test=False).search([("partner_id", "=", partner.id)])
for model in ("tectora.roof.timer", "tectora.roof.execution.report", "tectora.roof.planning"):
    if model in env:
        env[model].with_context(active_test=False).search([("project_id", "in", roofs.ids)]).unlink()
env["account.analytic.line"].search([("project_id", "in", projects.ids)]).unlink()
if "tectora.project.order.line" in env:
    env["tectora.project.order.line"].search([("project_id", "in", projects.ids)]).unlink()
orders.filtered(lambda o: o.state not in ("draft", "cancel"))._action_cancel()
orders.unlink()
roofs.unlink()
projects.with_context(active_test=False).task_ids.unlink()
if "project.collaborator" in env:
    env["project.collaborator"].sudo().search([("project_id", "in", projects.ids)]).unlink()
projects.unlink()
leads = env["crm.lead"].with_context(active_test=False).search(
    ["|", ("partner_id", "=", partner.id), ("name", "=", DEMO_OPPORTUNITY)])
env["calendar.event"].search([("opportunity_id", "in", leads.ids)]).unlink()
env["calendar.event"].search([("name", "ilike", "Peeters")]).unlink()
leads.unlink()

# ------------------------------------------------- a pipeline that looks alive
stages = env["crm.stage"].search([], order="sequence")
stage_new, stage_qualified, stage_proposal, stage_won = (list(stages) + [stages[-1:]] * 4)[:4]
source = ref("tectora_roof.utm_source_lead_website")
tags = {name: upsert("crm.tag", [("name", "=", name)], {"name": name})
        for name in ("Renovatie", "Nieuwbouw", "Lichtkoepel", "Industrie")}
others = [
    ("Nieuwbouw plat dak Claeys", "Bart Claeys", "Roeselare", stage_qualified, 22000, "Nieuwbouw", "lead_architect"),
    ("Dakterras renovatie Vandenberghe", "Sofie Vandenberghe", "Kortrijk", stage_proposal, 9800, "Renovatie", "lead_google"),
    ("Industriedak Verstraete NV", "Verstraete NV", "Waregem", stage_proposal, 48000, "Industrie", "lead_bouwonderneming"),
    ("Lekkage herstelling Desmet", "Lieve Desmet", "Tielt", stage_new, 1200, "Renovatie", "mond_aan_mond_reclame_visibility"),
    ("Carport EPDM Wouters", "Dirk Wouters", "Izegem", stage_won, 3400, "Nieuwbouw", "lead_facebook"),
    ("Plat dak garage Maes", "Annick Maes", "Ingelmunster", stage_new, 4600, "Renovatie", "lead_homedeal"),
]
for name, client, city, crm_stage, revenue, tag, src in others:
    other = upsert("res.partner", [("name", "=", client)], {
        "name": client, "city": city, "country_id": belgium.id, "is_company": client.endswith("NV")})
    upsert("crm.lead", [("name", "=", name)], {
        "name": name, "type": "opportunity", "partner_id": other.id, "expected_revenue": revenue,
        "stage_id": crm_stage.id, "user_id": user.id, "tag_ids": [(6, 0, tags[tag].ids)],
        "source_id": (ref(f"tectora_roof.utm_source_{src}") or source).id, "active": True,
    })

# --------------------------------------------------- project set-up (09, 10)
if "tectora.project.phase" in env:
    phases = {}
    for seq, (name, subtitle) in enumerate((("Voorbereiding", "Alles klaar voor de start"),
                                            ("Uitvoering", "De werken op het dak"),
                                            ("Oplevering", "Werf opleveren en afrekenen")), 1):
        phases[name] = upsert("tectora.project.phase", [("name", "=", name)], {
            "name": name, "subtitle": subtitle, "sequence": seq * 10, "active": True})
    Template = env["tectora.task.template"].with_context(active_test=False)
    Template.search([]).unlink()
    tasks = [
        # phase, task, sequence, optional, reference, days, subtasks
        ("Voorbereiding", "Plaatsbezoek bevestigen", 10, False, "start", -10,
         ["Afspraak met de klant", "Werfadres en toegang nakijken"]),
        ("Voorbereiding", "Bestellijst afgevinkt", 20, False, "start", -3, []),
        ("Voorbereiding", "Stelling bestellen", 30, True, "start", -5, []),
        ("Uitvoering", "Werf inrichten en container plaatsen", 10, False, "start", 0, []),
        ("Uitvoering", "Tussentijdse controle met de klant", 20, False, "start", 3, []),
        ("Oplevering", "Werf opleveren met klant", 10, False, "end", 1, []),
        ("Oplevering", "Eindfactuur", 20, False, "end", 3, []),
    ]
    for phase, name, seq, optional, refer, days, subtasks in tasks:
        values = {"name": name, "phase_id": phases[phase].id, "sequence": seq, "optional": optional,
                  "deadline_reference": refer, "deadline_offset": days}
        if name == "Bestellijst afgevinkt" and "order_list_auto" in Template._fields:
            values["order_list_auto"] = True
        parent = Template.create(values)
        for n, sub in enumerate(subtasks):
            Template.create({"name": sub, "phase_id": phases[phase].id, "parent_id": parent.id,
                             "sequence": n, "deadline_reference": refer, "deadline_offset": days})

if "tectora.order.list.template" in env:
    Parts = env["tectora.order.list.template"].with_context(active_test=False)
    Parts.search([]).unlink()
    for seq, (name, action, supplier) in enumerate((
            ("Lichtkoepels", "order", "Dakcenter Vlaanderen"),
            ("Isolatie PIR", "order", "Bouwmaterialen De Smet"),
            ("EPDM en toebehoren", "stock_first", "Dakcenter Vlaanderen"),
            ("Dakrandprofielen", "order", "Dakcenter Vlaanderen"),
            ("Container", "order", "Bouwmaterialen De Smet")), 1):
        values = {"name": name, "sequence": seq * 10, "partner_ids": [(6, 0, suppliers[supplier].ids)]}
        if action in dict(Parts._fields["order_action"].selection):
            values["order_action"] = action
        Parts.create(values)

# ------------------------------------------------------------- hercalculatie
edge = product("P00483").product_tmpl_id        # dakrand basisprofiel, 3 m per stuk
pir = product("P00512").product_tmpl_id         # Utherm 1200 × 600 mm
if "tectora_recalc" in edge._fields:
    edge.write({"tectora_recalc": True, "tectora_recalc_uom": "m", "tectora_length_mm": 3000,
                "tectora_recalc_margin": 5})
    if stage == "quote_norecalc":
        pir.write({"tectora_recalc": False, "tectora_length_mm": 0, "tectora_width_mm": 0,
                   "tectora_recalc_margin": 0})
    else:
        pir.write({"tectora_recalc": True, "tectora_recalc_uom": "m2", "tectora_length_mm": 1200,
                   "tectora_width_mm": 600, "tectora_recalc_margin": 3})
# The board's norm without waste: the safety margin covers the cutting loss.
insulation = product("S00139")
for line in env["mrp.bom"].search([("product_tmpl_id", "=", insulation.product_tmpl_id.id)]).bom_line_ids:
    if line.product_id.product_tmpl_id == pir:
        line.product_qty = 1.0

# ----------------------------------------------------------------- employees
def employee(name, job, email=None):
    return upsert("hr.employee", [("name", "=", name)], {
        "name": name, "job_title": job, "work_email": email or False, "company_id": company.id})

lead_emp = upsert("hr.employee", [("user_id", "=", user.id)], {
    "name": "Jan Verbeke", "job_title": "Projectleider", "user_id": user.id, "company_id": company.id})
foreman = employee("Koen De Vos", "Ploegbaas", FOREMAN_LOGIN)
roofer = employee("Tom Maes", "Dakwerker", "tom.maes@tectora.example")
roofer2 = employee("Ruben Claes", "Dakwerker")
# Tom gets his portal access during video 11: start without it.
if roofer.user_id:
    old = roofer.user_id
    roofer.user_id = False
    old.active = False
    old.login = f"archived-{old.id}-{old.login}"
team = upsert("tectora.roof.team", [("name", "=", "Ploeg 1")], {"name": "Ploeg 1", "leader_id": foreman.id})
(foreman | roofer | roofer2).write({"roof_team_id": team.id})
if "tectora_portal_planning_horizon" in foreman._fields:
    foreman.tectora_portal_planning_horizon = "week"
if not foreman.user_id:
    foreman.action_tectora_grant_portal_access()
foreman.user_id.sudo().write({"password": FOREMAN_PASSWORD, "lang": "nl_BE", "tz": "Europe/Brussels"})
# An office colleague to @mention in the chatter (video 02).
if not env["res.users"].with_context(active_test=False).search([("login", "=", "els.vermeulen@tectora.example")]):
    env["res.users"].with_context(no_reset_password=True).create({
        "name": "Els Vermeulen", "login": "els.vermeulen@tectora.example", "email": "els.vermeulen@tectora.example",
        "lang": "nl_BE", "tz": "Europe/Brussels", "company_id": company.id, "company_ids": [(6, 0, company.ids)],
        "group_ids" if "group_ids" in env["res.users"]._fields else "groups_id": [(6, 0, ref("base.group_user").ids)]})
# Notified in Odoo, not by mail: no failed-mail icon on the message.
env["res.users"].search([("login", "=", "els.vermeulen@tectora.example")]).notification_type = "inbox"

# -------------------------------------------------------------- the opportunity
if stage != "lead_new":
    lead = env["crm.lead"].create({
        "name": DEMO_OPPORTUNITY, "type": "opportunity", "partner_id": partner.id,
        "street": partner.street, "zip": partner.zip, "city": partner.city, "country_id": belgium.id,
        "expected_revenue": 14500, "priority": "2", "user_id": user.id, "source_id": source.id,
        "stage_id": stage_qualified.id,
    })
    if stage != "lead":
        lead.write({"description": NOTES, "tag_ids": [(6, 0, (tags["Renovatie"] | tags["Lichtkoepel"]).ids)]})
        lead.activity_schedule("mail.mail_activity_data_call", date_deadline=today.date() + timedelta(days=1),
                               summary="Plaatsbezoek afspreken", user_id=user.id)

# ---------------------------------------------------------------- the quotation
if stage.startswith("quote") or stage in ("project", "timer"):
    lead.stage_id = stage_proposal
    order = env["sale.order"].create({
        "partner_id": partner.id, "opportunity_id": lead.id, "sale_order_template_id": template.id,
        "user_id": user.id,
    })
    order._onchange_sale_order_template_id()
    for line in order.order_line:
        qty = MEASURED.get(line.product_id.default_code)
        if qty:
            line.product_uom_qty = qty
    six = env["account.tax"].search([("name", "=", "6%"), ("type_tax_use", "=", "sale"),
                                     ("company_id", "=", company.id)], limit=1)
    if six and "tectora_tax_id" in order._fields:
        order.tectora_tax_id = six
        order.action_apply_tectora_tax()
    order.action_quotation_sent() if hasattr(order, "action_quotation_sent") else None

if stage in ("project", "timer"):
    roof = order.roof_project_id if "roof_project_id" in order._fields else False
    start = today + timedelta(days=(7 - today.weekday()) % 7 or 7, hours=7)   # next Monday
    if roof:
        roof.write({"planned_date_begin": start, "planned_date_end": start + timedelta(days=4, hours=9),
                    "team_id": team.id})
    order.action_confirm()
    lead.stage_id = stage_won
    if roof and "tectora.roof.planning" in env:
        # Today's work block, so the site shows on the portal right away.
        env["tectora.roof.planning"].create({
            "project_id": roof.id, "team_id": team.id,
            "start_datetime": today + timedelta(hours=6), "end_datetime": today + timedelta(hours=15),
            "notes": "Oprit vrijlaten voor de container. Sleutel bij de buren (nr. 16).",
        })
    if stage == "timer" and roof and "tectora.roof.timer" in env:
        env["tectora.roof.timer"].create({
            "project_id": roof.id, "work_kind": "afbraak",
            "start_datetime": datetime.now() - timedelta(hours=6, minutes=30),
            "started_by_id": foreman.id, "employee_ids": [(6, 0, (foreman | roofer | roofer2).ids)],
        })
    # The portal header (video 11) shows the company logo: Tectora, not "Your logo".
    logo = os.path.join(ASSETS or "", "tectora_logo.png")
    if stage == "timer" and ASSETS and os.path.exists(logo):
        from odoo.tools.binary import BinaryBytes
        with open(logo, "rb") as handle:
            company.logo = BinaryBytes(handle.read())

# Nothing unread in the navbar during a take.
env.flush_all()
env.invalidate_all()
env["mail.notification"].search([("res_partner_id", "=", user.partner_id.id),
                                 ("is_read", "=", False)]).write({"is_read": True})
# The demo has no mail server: failed mails would show as a counter too.
env["mail.notification"].search([("notification_status", "in", ("exception", "bounce"))]).unlink()
for member in env["discuss.channel.member"].search([("partner_id", "=", user.partner_id.id)]):
    last = env["mail.message"].search([("model", "=", "discuss.channel"),
                                       ("res_id", "=", member.channel_id.id)], order="id desc", limit=1)
    if last:
        member._mark_as_read(last.id)

env.cr.commit()
print(f"Demo data ready (stage {stage})")
