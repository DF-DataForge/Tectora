# -*- coding: utf-8 -*-
"""The order list (bestellijst) of a project.

Every standard part (``tectora.order.list.template``) becomes a line on the
project's order list: tick it off, choose the supplier, follow the order and
delivery dates and create the request for quotation from it ("Stock eerst"
only orders the shortage). The project dashboard shows its progress and the
next parts to order; the order list page works through it top to bottom.
"""
from odoo import api, fields, models

from odoo.addons.tectora_project_tasks.models.project_task import TASK_DONE


class ProjectProject(models.Model):
    _inherit = "project.project"

    tectora_order_line_ids = fields.One2many(
        "tectora.project.order.line", "project_id", string="Bestellijst"
    )
    tectora_order_done_count = fields.Integer(
        string="Afgevinkt", compute="_compute_tectora_order_progress"
    )
    tectora_order_total_count = fields.Integer(
        string="Onderdelen", compute="_compute_tectora_order_progress"
    )
    tectora_order_progress = fields.Integer(
        string="Voortgang bestellijst (%)", compute="_compute_tectora_order_progress"
    )

    @api.depends("tectora_order_line_ids.checked")
    def _compute_tectora_order_progress(self):
        for project in self:
            lines = project.tectora_order_line_ids
            done = len(lines.filtered("checked"))
            project.tectora_order_total_count = len(lines)
            project.tectora_order_done_count = done
            project.tectora_order_progress = round(100 * done / len(lines)) if lines else 0

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        if not self.env.context.get("tectora_skip_task_phases"):
            projects.filtered(lambda p: not p.is_template)._tectora_create_order_list()
        return projects

    # ------------------------------------------------------------- order list
    def _tectora_create_order_list(self):
        """One order list line per standard part. Nothing happens without
        parts, or on a project that has an order list already."""
        templates = self.env["tectora.order.list.template"].search([])
        if not templates:
            return False
        values = []
        for project in self.filtered(lambda p: not p.tectora_order_line_ids):
            for template in templates:
                values.append({
                    "project_id": project.id,
                    "template_id": template.id,
                    "sequence": template.sequence,
                    "name": template.name,
                    "order_action": template.order_action,
                    "supplier_note": template.supplier_note,
                    "partner_id": template.partner_ids[:1].id,
                })
        self.env["tectora.project.order.line"].create(values)
        return True

    def _tectora_sync_order_list_task(self):
        """The task that follows the order list is done as soon as every
        line is ticked off, and open again otherwise."""
        for project in self.filtered("tectora_task_phases"):
            lines = project.tectora_order_line_ids
            done = bool(lines) and all(lines.mapped("checked"))
            tasks = self.env["project.task"].search([
                ("project_id", "=", project.id),
                ("tectora_template_id.order_list_auto", "=", True),
            ])
            tasks.filtered(lambda t: (t.state == TASK_DONE) != done).action_tectora_toggle_done(done=done)

    # ----------------------------------------------------------------- actions
    def action_tectora_create_order_list(self):
        self._tectora_create_order_list()
        return True

    def action_tectora_open_order_board(self):
        """The order list page of the project."""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "tectora_project_order_list",
            "name": self.env._("Bestellijst · %s", self.name),
            "context": {"active_id": self.id},
            "params": {"project_id": self.id},
        }

    def action_tectora_open_order_lines(self):
        """The order list as a standard, editable list."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Bestellijst · %s", self.name),
            "res_model": "tectora.project.order.line",
            "views": [(False, "list"), (False, "form")],
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    # ------------------------------------------------------------------ boards
    def _tectora_task_data(self, task):
        data = super()._tectora_task_data(task)
        if task.tectora_order_list_auto:
            data["link"] = {
                "label": self.env._(
                    "bestellijst %(done)s/%(total)s",
                    done=self.tectora_order_done_count,
                    total=self.tectora_order_total_count,
                ),
                "method": "action_tectora_open_order_board",
            }
        return data

    def tectora_get_order_list_data(self):
        """Everything the order list block and page show."""
        self.ensure_one()
        Line = self.env["tectora.project.order.line"]
        actions = dict(Line._fields["order_action"]._description_selection(self.env))
        statuses = dict(Line._fields["status"]._description_selection(self.env))
        lines = []
        for line in self.tectora_order_line_ids:
            suggested = line.allowed_partner_ids
            if line.partner_id and line.partner_id not in suggested:
                suggested |= line.partner_id
            lines.append({
                "id": line.id,
                "name": line.name,
                "action": line.order_action,
                "action_label": actions.get(line.order_action),
                "checked": line.checked,
                "partner_id": line.partner_id.id or False,
                "partner_name": line.partner_id.name or "",
                "suppliers": [{"id": p.id, "name": p.name} for p in suggested],
                "supplier_note": line.supplier_note or "",
                "order_date": line.order_date and fields.Date.to_string(line.order_date) or "",
                "expected_date": line.expected_date and fields.Date.to_string(line.expected_date) or "",
                "status": line.status,
                "status_label": statuses.get(line.status),
                "late": line.is_late,
                "purchase_count": line.purchase_count,
                "product_count": len(line.product_line_ids),
                "shortage": any(line.product_line_ids.mapped("shortage_qty")),
            })
        return {
            "project": {
                "id": self.id,
                "name": self.name,
                "can_create": bool(
                    self.env["tectora.order.list.template"].search_count([], limit=1)
                ),
            },
            "lines": lines,
            "done": self.tectora_order_done_count,
            "total": self.tectora_order_total_count,
            "progress": self.tectora_order_progress,
            "late": len([line for line in lines if line["late"]]),
        }
