# -*- coding: utf-8 -*-
"""Planner blocks are coloured per project instead of per team: give every
roof project a colour and copy it onto its work blocks."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE tectora_roof_project
        SET color = (id %% 11) + 1
        WHERE color IS NULL OR color = 0
        """
    )
    cr.execute(
        """
        UPDATE tectora_roof_planning p
        SET color = r.color
        FROM tectora_roof_project r
        WHERE p.project_id = r.id
        """
    )
