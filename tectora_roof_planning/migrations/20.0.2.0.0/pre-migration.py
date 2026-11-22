# -*- coding: utf-8 -*-
"""From the bridge to the Planning app to the planner of the Project app.

Up to 20.0.1.x this module made a shift (planning.slot) per employee of a
work block and grafted itself onto the Planning app: extension views on that
app's own views, a "Per ploeg" menu, the app's default planner, its planners
per resource grouped by team, and the Ploegen menu under its configuration.
The module no longer depends on Planning and no longer defines any field on
planning.slot, so everything it left in that app is taken out here, before
the new code loads -- a view of the Planning app that still names one of
those fields would break that app:

* the views on planning.slot (those of this module's data, and the
  extensions the old post_init_hook made without an external id);
* the "Per ploeg" menu in the Planning app, and the app's default planner
  (back to what it was);
* the context of the planners per resource (back to what it was);
* the shifts the work blocks made (planning.slot with a work block): the
  work blocks themselves are the planning now, and stay untouched.

Every step runs in its own savepoint and only logs on failure.
"""
import json
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODULE = "tectora_roof_planning"
ROOT_ACTION_PARAM = "tectora_roof_planning.previous_planning_root_action"
PARENT_MENU_PARAM = "tectora_roof_planning.previous_teams_menu_parent"
RESOURCE_CONTEXTS_PARAM = "tectora_roof_planning.previous_resource_contexts"
OLD_TEAM_ACTION = "action_planning_slot_by_roof_team"
OLD_TEAM_MENU = "menu_planning_slot_by_roof_team"
# Views of this module that named fields which are gone (the shifts).
OLD_VIEWS = (
    "view_project_project_tectora_dashboard_slots",
    "view_tectora_roof_planning_form_summary_slots",
    "view_tectora_roof_planning_form_slots",
)


def _step(cr, label, function, *args):
    try:
        with cr.savepoint():
            function(*args)
    except Exception as error:
        _logger.warning("%s: migration step '%s' failed: %s", MODULE, label, error)


def _column_exists(cr, table, column):
    cr.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return bool(cr.fetchone())


def _xmlid_res_id(cr, name, model):
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s AND model = %s",
        (MODULE, name, model),
    )
    row = cr.fetchone()
    return row[0] if row else None


def _delete_views(cr):
    """This module's views on planning.slot and its views naming the
    shifts, extensions first."""
    cr.execute(
        """
        SELECT v.id
          FROM ir_ui_view v
         WHERE (v.model = 'planning.slot' AND (
                    v.name LIKE %s
                 OR v.id IN (SELECT res_id FROM ir_model_data
                              WHERE module = %s AND model = 'ir.ui.view')))
            OR v.id IN (SELECT res_id FROM ir_model_data
                         WHERE module = %s AND model = 'ir.ui.view' AND name IN %s)
         ORDER BY (v.inherit_id IS NULL), v.id DESC
        """,
        (r"planning.slot.%.tectora.roof", MODULE, MODULE, OLD_VIEWS),
    )
    view_ids = [row[0] for row in cr.fetchall()]
    for view_id in view_ids:
        def delete(view_id=view_id):
            cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))
            cr.execute(
                "DELETE FROM ir_model_data WHERE model = 'ir.ui.view' AND res_id = %s",
                (view_id,),
            )
        _step(cr, "view %s" % view_id, delete)
    _logger.info("%s: removed %s views of the Planning bridge", MODULE, len(view_ids))


def _restore_planning_app(cr, env):
    """The Planning app opens on its own planner again and loses the "Per
    ploeg" menu."""
    Param = env["ir.config_parameter"].sudo()
    action_id = _xmlid_res_id(cr, OLD_TEAM_ACTION, "ir.actions.act_window")
    menu_id = _xmlid_res_id(cr, OLD_TEAM_MENU, "ir.ui.menu")
    if menu_id:
        cr.execute("DELETE FROM ir_ui_menu WHERE id = %s", (menu_id,))
        cr.execute(
            "DELETE FROM ir_model_data WHERE module = %s AND name = %s", (MODULE, OLD_TEAM_MENU)
        )
    if action_id:
        reference = "ir.actions.act_window,%s" % action_id
        previous = Param.get_str(ROOT_ACTION_PARAM) or None
        if previous:
            # Only an action that is still there.
            try:
                model, res_id = previous.split(",")
                if not env[model].browse(int(res_id)).exists():
                    previous = None
            except Exception:
                previous = None
        # Whatever menu still points at the old team planner: the Planning
        # app's root (back to its own planner; without one kept, none, so it
        # opens its first submenu again).
        cr.execute("UPDATE ir_ui_menu SET action = %s WHERE action = %s", (previous, reference))
    Param.set_str(ROOT_ACTION_PARAM, "")
    # Ploegen moves on to Project -> Configuratie (post-migration).
    Param.set_str(PARENT_MENU_PARAM, "")


def _restore_resource_planners(cr, env):
    """The planners per resource group as they did before."""
    Param = env["ir.config_parameter"].sudo()
    try:
        previous = json.loads(Param.get_str(RESOURCE_CONTEXTS_PARAM) or "{}")
    except ValueError:
        previous = {}
    for action_id, context in previous.items():
        cr.execute(
            "UPDATE ir_act_window SET context = %s WHERE id = %s AND context LIKE %s",
            (context, int(action_id), "%tectora_%"),
        )
    # Any planner left that still groups by a field of the bridge.
    cr.execute(
        "SELECT id, name FROM ir_act_window WHERE res_model = 'planning.slot' "
        "AND context LIKE %s",
        ("%tectora_%",),
    )
    for action_id, name in cr.fetchall():
        _logger.warning(
            "%s: planner %s (%s) still names a field of the Planning bridge in "
            "its context; check it by hand", MODULE, name, action_id,
        )
    Param.set_str(RESOURCE_CONTEXTS_PARAM, "")


def _delete_block_shifts(cr):
    """The shifts the work blocks made in the Planning app."""
    if not _column_exists(cr, "planning_slot", "roof_planning_id"):
        return
    cr.execute("DELETE FROM planning_slot WHERE roof_planning_id IS NOT NULL")
    _logger.info(
        "%s: removed %s shifts of work blocks from the Planning app "
        "(the work blocks themselves stay)", MODULE, cr.rowcount,
    )


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _step(cr, "views", _delete_views, cr)
    _step(cr, "planning app", _restore_planning_app, cr, env)
    _step(cr, "resource planners", _restore_resource_planners, cr, env)
    _step(cr, "shifts", _delete_block_shifts, cr)
