# -*- coding: utf-8 -*-
from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = "project.task"

    tectora_order_list_auto = fields.Boolean(
        related="tectora_template_id.order_list_auto", string="Volgt de bestellijst"
    )
