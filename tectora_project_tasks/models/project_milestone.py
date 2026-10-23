# -*- coding: utf-8 -*-
from odoo import fields, models

from .project_task import TASK_DONE


class ProjectMilestone(models.Model):
    _inherit = "project.milestone"

    tectora_phase_id = fields.Many2one(
        "tectora.project.phase", string="Projectfase",
        index="btree_not_null", ondelete="restrict",
    )
    tectora_auto_reached = fields.Boolean(
        copy=False,
        help="Automatisch bereikt omdat alle taken van de fase klaar zijn.",
    )

    def write(self, vals):
        if "is_reached" in vals and "tectora_auto_reached" not in vals:
            vals = dict(vals, tectora_auto_reached=False)
        return super().write(vals)

    def _tectora_sync_reached(self):
        """A phase milestone is reached as soon as all its active main tasks
        are done. A milestone reached by hand stays reached."""
        for milestone in self.filtered(
            lambda m: m.tectora_phase_id and m.project_id.tectora_task_phases
        ):
            # Only the active tasks count: a switched-off option never blocks
            # the phase, whatever context the caller runs in.
            tasks = self.env["project.task"].with_context(active_test=True).search(
                [("milestone_id", "=", milestone.id), ("parent_id", "=", False)]
            )
            all_done = bool(tasks) and all(task.state == TASK_DONE for task in tasks)
            if all_done and not milestone.is_reached:
                milestone.write({"is_reached": True, "tectora_auto_reached": True})
            elif not all_done and milestone.is_reached and milestone.tectora_auto_reached:
                milestone.write({"is_reached": False, "tectora_auto_reached": False})
