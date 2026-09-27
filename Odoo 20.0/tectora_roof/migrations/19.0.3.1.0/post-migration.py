# -*- coding: utf-8 -*-
"""Projects are named after the customer and the municipality of the site
("Data Forge — Wortegem") instead of after the roof project's reference and
name. Rename the projects that still carry the generated old name; a name
someone changed by hand is left alone."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    roofs = env["tectora.roof.project"].search([("project_id", "!=", False)])
    for roof in roofs:
        project = roof.project_id
        old_name = "%s — %s" % (roof.code, roof.name)
        if project.name != old_name:
            continue
        new_name = roof._project_name()
        if new_name and new_name != project.name:
            project.with_context(tectora_sync=True).write({"name": new_name})
