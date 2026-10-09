# -*- coding: utf-8 -*-
"""The CRM sources (utm.source) Tectora works with ship as data. A source that
was already made by hand under the same name gets the data's external id, so
upgrading keeps it, and the leads on it, instead of adding a copy."""

SOURCES = {
    "utm_source_koude_prospectie_op_de_baan": "koude prospectie op de baan",
    "utm_source_koude_prospectie_via_mail": "koude prospectie via mail",
    "utm_source_lead_architect": "Lead architect",
    "utm_source_lead_bobex": "Lead Bobex",
    "utm_source_lead_bouwonderneming": "Lead bouwonderneming",
    "utm_source_lead_facebook": "Lead Facebook",
    "utm_source_lead_google": "Lead Google",
    "utm_source_lead_homedeal": "Lead Homedeal",
    "utm_source_lead_instagram": "Lead Instagram",
    "utm_source_lead_syndicus": "Lead syndicus",
    "utm_source_lead_trustlocal": "Lead Trustlocal",
    "utm_source_lead_via_ai": "Lead via AI",
    "utm_source_lead_via_mathias": "Lead via Mathias",
    "utm_source_lead_website": "Lead website",
    "utm_source_mond_aan_mond_reclame_visibility": "mond aan mond reclame visibility",
}


def migrate(cr, version):
    cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'utm_source' AND column_name = 'name'
        """
    )
    row = cr.fetchone()
    name_sql = "name->>'en_US'" if row and row[0] == "jsonb" else "name"
    for xmlid, name in SOURCES.items():
        cr.execute(
            "SELECT 1 FROM ir_model_data WHERE module = 'tectora_roof' AND name = %s",
            (xmlid,),
        )
        if cr.fetchone():
            continue
        cr.execute(
            f"SELECT id FROM utm_source WHERE lower(trim({name_sql})) = lower(%s) "
            "ORDER BY id LIMIT 1",
            (name,),
        )
        source = cr.fetchone()
        if source:
            cr.execute(
                """
                INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                VALUES ('tectora_roof', %s, 'utm.source', %s, TRUE)
                """,
                (xmlid, source[0]),
            )
