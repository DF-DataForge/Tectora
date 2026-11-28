# -*- coding: utf-8 -*-
"""Planning runs on contacts.

The ploegen and the work blocks were made of employees; they now hold
contacts. What was planned comes along: every employee's work contact takes
their place in the ploeg and on the work blocks."""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    # Ploegbaas: the work contact of the employee that led the ploeg.
    cr.execute(
        """
        UPDATE tectora_roof_team t
           SET leader_partner_id = e.work_contact_id
          FROM hr_employee e
         WHERE e.id = t.leader_id
           AND t.leader_partner_id IS NULL
           AND e.work_contact_id IS NOT NULL
        """
    )
    # Ploegleden: only for a ploeg that has no contacts yet.
    cr.execute(
        """
        INSERT INTO tectora_roof_team_partner_rel (team_id, partner_id)
        SELECT DISTINCT src.team_id, src.partner_id
          FROM (
                SELECT e.roof_team_id AS team_id, e.work_contact_id AS partner_id
                  FROM hr_employee e
                 WHERE e.roof_team_id IS NOT NULL
                   AND e.work_contact_id IS NOT NULL
                   AND e.active
                UNION
                SELECT t.id, t.leader_partner_id
                  FROM tectora_roof_team t
                 WHERE t.leader_partner_id IS NOT NULL
               ) src
         WHERE NOT EXISTS (
                SELECT 1 FROM tectora_roof_team_partner_rel r
                 WHERE r.team_id = src.team_id
               )
        """
    )
    teams = cr.rowcount
    # Work blocks: the work contacts of the employees that were on them.
    cr.execute(
        """
        INSERT INTO tectora_roof_planning_partner_rel (planning_id, partner_id)
        SELECT DISTINCT r.planning_id, e.work_contact_id
          FROM tectora_roof_planning_employee_rel r
          JOIN hr_employee e ON e.id = r.employee_id
         WHERE e.work_contact_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    _logger.info(
        "tectora_roof: %s ploeg members and %s planned persons moved to contacts",
        teams, cr.rowcount,
    )
