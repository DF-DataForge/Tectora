# -*- coding: utf-8 -*-
"""Map the old three-state answers onto the new checkboxes: "yes" is ticked,
"no" and "/" are not. The set-aside columns are dropped afterwards."""

FIELDS = [
    "checkin_at_work", "asbestos_present", "material_direct_roof", "material_through_building", "material_via_side", "aerial_lift_needed", "transport_over_building", "scaffolding_needed", "mobile_scaffolding_needed", "concrete_drilling_needed", "hvac_contractor_needed", "precautions_needed", "generator_needed", "site_toilet_needed", "site_hut_needed", "easy_parking", "parking_ban_needed", "driveway_paved",
]


def migrate(cr, version):
    for name in FIELDS:
        cr.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'tectora_roof_project' AND column_name = %s
            """,
            (name + "_tristate",),
        )
        if not cr.fetchone():
            continue
        cr.execute(
            'UPDATE tectora_roof_project SET "%s" = ("%s_tristate" = \'yes\')'
            % (name, name)
        )
        cr.execute('ALTER TABLE tectora_roof_project DROP COLUMN "%s_tristate"' % name)
