# -*- coding: utf-8 -*-
"""The portal runs on contacts.

Portal settings, hour registrations and execution reports were kept per
employee; they now hang on the contact. Everything comes along through the
employees' work contacts."""
import logging

_logger = logging.getLogger(__name__)

SETTINGS = (
    "tectora_portal_planning_horizon",
    "tectora_portal_show_overview",
    "tectora_portal_show_materials",
    "tectora_portal_show_plan",
    "tectora_portal_show_report",
    "tectora_portal_show_hours",
)


def _has_column(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    if not version:
        return
    # What each employee saw on the portal: now on their work contact.
    for column in SETTINGS:
        if _has_column(cr, "hr_employee", column) and _has_column(cr, "res_partner", column):
            cr.execute(
                """
                UPDATE res_partner p
                   SET {column} = e.{column}
                  FROM hr_employee e
                 WHERE e.work_contact_id = p.id
                   AND e.{column} IS NOT NULL
                """.format(column=column)
            )
    # Hour registrations: the crew and who started / stopped them.
    cr.execute(
        """
        INSERT INTO tectora_roof_timer_partner_rel (timer_id, partner_id)
        SELECT DISTINCT r.timer_id, e.work_contact_id
          FROM tectora_roof_timer_employee_rel r
          JOIN hr_employee e ON e.id = r.employee_id
         WHERE e.work_contact_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    moved = cr.rowcount
    for old, new in (
        ("started_by_id", "started_by_partner_id"),
        ("stopped_by_id", "stopped_by_partner_id"),
    ):
        if _has_column(cr, "tectora_roof_timer", old):
            cr.execute(
                """
                UPDATE tectora_roof_timer t
                   SET {new} = e.work_contact_id
                  FROM hr_employee e
                 WHERE e.id = t.{old} AND t.{new} IS NULL
                """.format(old=old, new=new)
            )
    # Execution reports: written by the contact.
    if _has_column(cr, "tectora_roof_execution_report", "employee_id"):
        cr.execute(
            """
            UPDATE tectora_roof_execution_report r
               SET author_id = e.work_contact_id
              FROM hr_employee e
             WHERE e.id = r.employee_id
               AND e.work_contact_id IS NOT NULL
            """
        )
    _logger.info("tectora_portal: %s registered persons moved to contacts", moved)
