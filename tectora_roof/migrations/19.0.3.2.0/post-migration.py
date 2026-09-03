# -*- coding: utf-8 -*-
"""Team membership moved onto the employee (hr.employee.roof_team_id, one
team per employee) from the many2many on the team. Carry the existing
assignments over; an employee who was on several teams keeps the first one.
The old relation table is left in place, unused."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'tectora_roof_team_employee_rel'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE hr_employee e
        SET roof_team_id = r.team_id
        FROM (
            SELECT DISTINCT ON (employee_id) employee_id, team_id
            FROM tectora_roof_team_employee_rel
            ORDER BY employee_id, team_id
        ) r
        WHERE e.id = r.employee_id AND e.roof_team_id IS NULL
        """
    )
