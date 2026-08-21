# -*- coding: utf-8 -*-
"""Extend Odoo Planning's own views with the roof-project fields.

Planning is an Enterprise app, so its view external ids cannot be referenced
from here with any certainty (a wrong ``inherit_id`` would break the install).
Instead the base views are looked up by model and type at install/upgrade time
and an extension view is created for each one that is found. Every extension
is applied in its own savepoint: a view whose structure does not match simply
gets skipped, with a warning, instead of breaking the module.
"""
import logging

_logger = logging.getLogger(__name__)

# view type -> arch injected into Odoo's own view
VIEW_EXTENSIONS = [
    (
        "gantt",
        """
        <xpath expr="//gantt" position="inside">
            <field name="roof_project_id"/>
            <field name="roof_team_id"/>
        </xpath>
        """,
    ),
    (
        "search",
        """
        <xpath expr="//search" position="inside">
            <field name="roof_project_id"/>
            <field name="roof_team_id"/>
            <filter name="tectora_group_roof_project" string="Dakproject"
                    context="{'group_by': 'roof_project_id'}"/>
            <filter name="tectora_group_roof_team" string="Ploeg"
                    context="{'group_by': 'roof_team_id'}"/>
        </xpath>
        """,
    ),
    (
        "list",
        """
        <xpath expr="//list" position="inside">
            <field name="roof_project_id" optional="show"/>
            <field name="roof_team_id" optional="hide"/>
            <field name="roof_address" optional="hide"/>
        </xpath>
        """,
    ),
    (
        "form",
        """
        <xpath expr="//field[@name='resource_id']" position="after">
            <field name="roof_project_id"/>
            <field name="roof_planning_id" readonly="1"
                   invisible="not roof_planning_id"/>
        </xpath>
        """,
    ),
]


def _extend_planning_views(env):
    View = env["ir.ui.view"]
    for view_type, arch in VIEW_EXTENSIONS:
        base_views = View.search(
            [
                ("model", "=", "planning.slot"),
                ("type", "=", view_type),
                ("inherit_id", "=", False),
                ("mode", "=", "primary"),
            ]
        )
        if not base_views:
            _logger.info(
                "tectora_roof_planning: no base %s view for planning.slot", view_type
            )
            continue
        for base in base_views:
            name = "planning.slot.%s.tectora.roof" % view_type
            values = {
                "name": name,
                "model": "planning.slot",
                "type": view_type,
                "inherit_id": base.id,
                "mode": "extension",
                "priority": 99,
                "arch_db": "<data>%s</data>" % arch,
            }
            existing = View.search(
                [("name", "=", name), ("inherit_id", "=", base.id)], limit=1
            )
            try:
                with env.cr.savepoint():
                    if existing:
                        existing.write(values)
                    else:
                        View.create(values)
                _logger.info(
                    "tectora_roof_planning: extended planning.slot %s view %s",
                    view_type, base.id,
                )
            except Exception as error:
                _logger.warning(
                    "tectora_roof_planning: could not extend the planning.slot "
                    "%s view (%s): %s", view_type, base.id, error,
                )


def post_init_hook(env):
    _extend_planning_views(env)
    # Existing shifts get their roof project through the stored compute.
    slots = env["planning.slot"].search([])
    if slots:
        slots._compute_roof_project_id()
        slots.flush_recordset(["roof_project_id"])
