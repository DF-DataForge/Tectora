# -*- coding: utf-8 -*-
from odoo import api, fields, models

TASK_DONE = "1_done"
TASK_OPEN = "01_in_progress"


class ProjectTask(models.Model):
    _inherit = "project.task"

    tectora_phase_id = fields.Many2one(
        related="milestone_id.tectora_phase_id", string="Projectfase",
        store=True, index="btree_not_null",
    )
    tectora_template_id = fields.Many2one(
        "tectora.task.template", string="Taaksjabloon", ondelete="set null"
    )
    tectora_optional = fields.Boolean(string="Optie")

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        if not self.env.context.get("tectora_skip_milestone_sync"):
            tasks.milestone_id._tectora_sync_reached()
        return tasks

    def write(self, vals):
        milestones = self.milestone_id
        res = super().write(vals)
        if (
            {"state", "active", "milestone_id"} & vals.keys()
            and not self.env.context.get("tectora_skip_milestone_sync")
        ):
            (milestones | self.milestone_id)._tectora_sync_reached()
        return res

    def action_tectora_toggle_done(self, done=None):
        """Tick a task off or reopen it.

        :param done: the state the user asked for, as they saw it; without a
            value the task is toggled.
        """
        tasks = self.with_context(tectora_skip_milestone_sync=True)
        for task in tasks:
            done_now = task.state != TASK_DONE if done is None else bool(done)
            if done_now == (task.state == TASK_DONE):
                continue
            task.state = TASK_DONE if done_now else TASK_OPEN
            if done_now:
                # Ticking a task off ticks off its subtasks too.
                task.child_ids.filtered(lambda t: t.state != TASK_DONE).state = TASK_DONE
            elif task.parent_id.state == TASK_DONE:
                task.parent_id.state = TASK_OPEN
        # A parent task is done as soon as all its subtasks are.
        for parent in tasks.parent_id:
            children = parent.child_ids
            if children and all(c.state == TASK_DONE for c in children) and parent.state != TASK_DONE:
                parent.state = TASK_DONE
        (self.milestone_id | self.parent_id.milestone_id)._tectora_sync_reached()
        return True

    def action_tectora_toggle_enabled(self):
        """Switch an optional task on or off for its project (archives it)."""
        tasks = self.with_context(active_test=False, tectora_skip_milestone_sync=True)
        for task in tasks:
            (task | task.child_ids).write({"active": not task.active})
        tasks.milestone_id._tectora_sync_reached()
        return True
