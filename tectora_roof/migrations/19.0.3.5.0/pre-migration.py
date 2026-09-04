# -*- coding: utf-8 -*-
"""The yes/no questions of the Werf tab become checkboxes. Their columns held
a selection (yes/no/na); set them aside so the upgrade can create the boolean
columns, the post-migration maps the answers back."""

FIELDS = [
    "checkin_at_work", "asbestos_present", "material_direct_roof", "material_through_building", "material_via_side", "aerial_lift_needed", "transport_over_building", "scaffolding_needed", "mobile_scaffolding_needed", "concrete_drilling_needed", "hvac_contractor_needed", "precautions_needed", "generator_needed", "site_toilet_needed", "site_hut_needed", "easy_parking", "parking_ban_needed", "driveway_paved",
]


def migrate(cr, version):
    for name in FIELDS:
        cr.execute(
            """
            SELECT udt_name FROM information_schema.columns
            WHERE table_name = 'tectora_roof_project' AND column_name = %s
            """,
            (name,),
        )
        row = cr.fetchone()
        if not row or row[0] == "bool":
            continue
        cr.execute(
            'ALTER TABLE tectora_roof_project RENAME COLUMN "%s" TO "%s_tristate"'
            % (name, name)
        )
