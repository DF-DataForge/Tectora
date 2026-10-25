# -*- coding: utf-8 -*-
"""Task follow-up per project phase.

Every phase (``tectora.project.phase``) becomes a milestone on the project;
the task templates of a phase become tasks and subtasks on that milestone.
The project dashboard shows the phases as a timeline with the open tasks of
the current phase, and a task page ticks them off per phase.
"""
from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import format_date

from .project_task import TASK_DONE


class ProjectProject(models.Model):
    _inherit = "project.project"

    tectora_task_phases = fields.Boolean(
        string="Taakopvolging per fase",
        help="De taken van het project volgen de projectfases (mijlpalen) "
        "en hun taaksjablonen.",
    )
    tectora_phase_id = fields.Many2one(
        "tectora.project.phase", string="Fase", copy=False,
        compute="_compute_tectora_phase_id", store=True, index=True,
        group_expand="_read_group_tectora_phase_id",
        help="Huidige fase: de eerste fase-mijlpaal die nog niet bereikt is.",
    )

    @api.model
    def _read_group_tectora_phase_id(self, phases, domain):
        return phases.search([])

    @api.depends(
        "tectora_task_phases", "milestone_ids.is_reached", "milestone_ids.tectora_phase_id"
    )
    def _compute_tectora_phase_id(self):
        for project in self:
            milestones = project._tectora_phase_milestones()
            if not project.tectora_task_phases or not milestones:
                project.tectora_phase_id = False
                continue
            current = milestones.filtered(lambda m: not m.is_reached)[:1] or milestones[-1:]
            project.tectora_phase_id = current.tectora_phase_id

    def _tectora_phase_milestones(self):
        self.ensure_one()
        return self.milestone_ids.filtered("tectora_phase_id").sorted(
            lambda m: (m.tectora_phase_id.sequence, m.tectora_phase_id.id)
        )

    # ------------------------------------------------------------------ create
    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        if not self.env.context.get("tectora_skip_task_phases"):
            projects.filtered(lambda p: not p.is_template)._tectora_init_task_phases()
        return projects

    def copy(self, default=None):
        # The copy carries the milestones and tasks of the original.
        return super(
            ProjectProject, self.with_context(tectora_skip_task_phases=True)
        ).copy(default=default)

    def write(self, vals):
        res = super().write(vals)
        if {"date_start", "date"} & vals.keys():
            self.filtered("tectora_task_phases")._tectora_update_deadlines()
        return res

    # ---------------------------------------------------------- initialisation
    def _tectora_init_task_phases(self):
        """Create the phase milestones and their tasks from the templates.

        Optional templates are created switched off; they are switched on
        per project on the task page. Without any phase configured nothing
        happens, so the follow-up can be started later.
        """
        phases = self.env["tectora.project.phase"].search([])
        if not phases:
            return False
        Template = self.env["tectora.task.template"]
        Task = self.env["project.task"].with_context(
            tectora_skip_milestone_sync=True, mail_create_nolog=True
        )
        Milestone = self.env["project.milestone"]
        templates = Template.search([("parent_id", "=", False)])
        for project in self.filtered(lambda p: not p.tectora_task_phases):
            project.write({"tectora_task_phases": True, "allow_milestones": True})
            existing = {m.tectora_phase_id: m for m in project.milestone_ids if m.tectora_phase_id}
            milestones = {}
            for index, phase in enumerate(phases, start=1):
                milestones[phase] = existing.get(phase) or Milestone.create({
                    "name": f"{index}. {phase.name}",
                    "sequence": phase.sequence,
                    "project_id": project.id,
                    "tectora_phase_id": phase.id,
                })
            for template in templates:
                milestone = milestones.get(template.phase_id)
                task = Task.create(project._tectora_task_values(template, milestone))
                for child in template.child_ids:
                    Task.create(project._tectora_task_values(child, milestone, parent=task))
            project._tectora_update_deadlines()
        return True

    def _tectora_task_values(self, template, milestone, parent=None):
        self.ensure_one()
        root = parent and template.parent_id or template
        return {
            "name": template.name,
            "project_id": self.id,
            "parent_id": parent.id if parent else False,
            "milestone_id": milestone.id if milestone else False,
            "tectora_template_id": template.id,
            "tectora_optional": root.optional,
            "sequence": template.sequence,
            "description": template.description,
            "user_ids": False,
            "active": not root.optional,
        }

    def _tectora_reference_date(self, reference):
        self.ensure_one()
        return {"start": self.date_start, "end": self.date}.get(reference)

    def _tectora_update_deadlines(self):
        """Deadlines of the phase milestones and the tasks follow the
        project's start and end date."""
        for milestone in self.milestone_ids.filtered("tectora_phase_id.deadline_reference"):
            phase = milestone.tectora_phase_id
            reference = milestone.project_id._tectora_reference_date(phase.deadline_reference)
            if reference:
                milestone.deadline = reference + timedelta(days=phase.deadline_offset)
        tasks = self.env["project.task"].with_context(active_test=False).search([
            ("project_id", "in", self.ids),
            ("tectora_template_id.deadline_reference", "!=", False),
        ])
        for task in tasks:
            template = task.tectora_template_id
            reference = task.project_id._tectora_reference_date(template.deadline_reference)
            if reference:
                task.date_deadline = fields.Datetime.to_datetime(
                    reference + timedelta(days=template.deadline_offset)
                ).replace(hour=12)

    # ----------------------------------------------------------------- actions
    def action_tectora_start_task_phases(self):
        """Start the task follow-up on a project that has none yet."""
        self._tectora_init_task_phases()
        return True

    def action_tectora_open_task_board(self, phase_id=False):
        """The task page of the project, filtered on a phase if given."""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "tectora_project_tasks",
            "name": self.env._("Taken · %s", self.name),
            "context": {"active_id": self.id},
            "params": {"project_id": self.id, "phase_id": phase_id or False},
        }

    def action_tectora_toggle_phase_reached(self, milestone_id):
        """Mark a phase milestone as reached (or not) by hand."""
        self.ensure_one()
        milestone = self.milestone_ids.filtered(lambda m: m.id == milestone_id)
        milestone.is_reached = not milestone.is_reached
        return True

    def action_tectora_open_phase_tasks(self, milestone_id=False):
        """The phase tasks as a standard list."""
        self.ensure_one()
        domain = [("project_id", "=", self.id), ("tectora_phase_id", "!=", False)]
        if milestone_id:
            domain.append(("milestone_id", "=", milestone_id))
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Taken · %s", self.name),
            "res_model": "project.task",
            "views": [
                (self.env.ref("tectora_project_tasks.view_task_list_tectora_phases").id, "list"),
                (False, "kanban"),
                (False, "form"),
            ],
            "domain": domain,
            "context": {
                "default_project_id": self.id,
                "default_milestone_id": milestone_id,
                "search_default_tectora_group_phase": 1,
            },
        }

    # ------------------------------------------------------------------- board
    def _tectora_task_data(self, task):
        today = fields.Date.context_today(self)
        return {
            "id": task.id,
            "name": task.name,
            "done": task.state == TASK_DONE,
            "enabled": task.active,
            "optional": task.tectora_optional,
            "deadline": task.date_deadline and format_date(self.env, task.date_deadline) or False,
            "late": bool(
                task.date_deadline and task.state != TASK_DONE
                and task.date_deadline.date() < today
            ),
            "users": ", ".join(task.user_ids.mapped("name")),
            # {"label", "method"}: a badge on the task page calling a
            # project method (an extension links a task to its own page).
            "link": False,
        }

    def tectora_get_task_board_data(self):
        """Everything the task block on the dashboard and the task page show."""
        self.ensure_one()
        env = self.env
        today = fields.Date.context_today(self)
        milestones = self._tectora_phase_milestones()
        tasks = env["project.task"].with_context(active_test=False).search(
            [("project_id", "=", self.id), ("milestone_id", "in", milestones.ids)],
            order="sequence, id",
        )
        parent_tasks = tasks.filtered(lambda t: t.parent_id not in tasks)

        phases = []
        for index, milestone in enumerate(milestones, start=1):
            phase = milestone.tectora_phase_id
            phase_tasks = parent_tasks.filtered(lambda t: t.milestone_id == milestone)
            enabled_tasks = phase_tasks.filtered("active")
            done_count = len(enabled_tasks.filtered(lambda t: t.state == TASK_DONE))
            blocks = []
            for task in phase_tasks:
                data = self._tectora_task_data(task)
                children = tasks.filtered(lambda t: t.parent_id == task)
                data["children"] = [self._tectora_task_data(child) for child in children]
                data["children_done"] = len([c for c in data["children"] if c["done"]])
                blocks.append(data)
            phases.append({
                "id": phase.id,
                "milestone_id": milestone.id,
                "name": phase.name,
                "subtitle": phase.subtitle or "",
                "sequence": index,
                "total": len(enabled_tasks),
                "done": done_count,
                "progress": round(100 * done_count / len(enabled_tasks)) if enabled_tasks else 0,
                "reached": milestone.is_reached,
                "reached_date": milestone.reached_date and format_date(env, milestone.reached_date) or "",
                "deadline": milestone.deadline and format_date(env, milestone.deadline) or "",
                "late": bool(milestone.deadline and not milestone.is_reached and milestone.deadline < today),
                "state": (
                    "done" if milestone.is_reached
                    else "current" if phase == self.tectora_phase_id else "future"
                ),
                "tasks": blocks,
            })

        open_tasks = tasks.filtered(lambda t: t.active and t.state != TASK_DONE and not t.parent_id)
        return {
            "project": {
                "id": self.id,
                "name": self.name,
                "started": self.tectora_task_phases,
                "can_start": bool(env["tectora.project.phase"].search_count([], limit=1)),
                "phase_id": self.tectora_phase_id.id or False,
            },
            "phases": phases,
            "current_tasks": [
                self._tectora_task_data(task)
                for task in open_tasks.filtered(lambda t: t.milestone_id.tectora_phase_id == self.tectora_phase_id)[:6]
            ],
            "open_count": len(open_tasks),
            "late_count": len(open_tasks.filtered(
                lambda t: t.date_deadline and t.date_deadline.date() < today
            )),
        }
