# -*- coding: utf-8 -*-
"""The statuses of the old system name their stage: Odoo's own stages,
renamed at Tectora to "Lopende offerte" (crm.stage_lead3) and "Gewonnen"
(crm.stage_lead4). The status data is noupdate, so the stage is set here on
the statuses that have none yet."""
from odoo import SUPERUSER_ID, api

STAGES = {
    "status_openstaand": "crm.stage_lead3",
    "status_on_hold": "crm.stage_lead3",
    "status_niet_goedgekeurd": "crm.stage_lead3",
    "status_goedgekeurd": "crm.stage_lead4",
    "status_deels_gefactureerd": "crm.stage_lead4",
    "status_gefactureerd": "crm.stage_lead4",
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for status_ref, stage_ref in STAGES.items():
        status = env.ref("tectora_quotation_import." + status_ref, raise_if_not_found=False)
        stage = env.ref(stage_ref, raise_if_not_found=False)
        if status and stage and not status.stage_id:
            status.stage_id = stage
