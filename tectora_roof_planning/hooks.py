# -*- coding: utf-8 -*-
"""Graft the roof planning onto Odoo's own Planning app.

Planning is an Enterprise app, so neither its view nor its menu external ids
can be referenced from here with any certainty (a wrong ``inherit_id`` would
break the install). Everything is therefore looked up at install/upgrade time
by what the records *are* rather than by xmlid:

* its planning.slot views, by model and type, get an extension view carrying
  the dakproject and ploeg fields;
* its "Inplannen" menu, by counting which menu has the most planning.slot
  children, gets the "Per ploeg" planner as its first entry, and the app is
  pointed at it so it becomes the planner Planning opens on;
* its "Configuratie" menu, by looking at what its children configure, adopts
  the Ploegen menu from the Dakmeting app.

Every step runs in its own savepoint and only logs on failure, so a Planning
release whose structure differs never breaks the install -- and
``uninstall_hook`` puts the app's default planner and the Ploegen menu back.
"""
import logging

_logger = logging.getLogger(__name__)

FORM_FIELDS = """
            <field name="roof_project_id"/>
            <field name="roof_team_id"/>
            <field name="roof_planning_id" readonly="1"
                   invisible="not roof_planning_id"/>
"""

# (view type, *alternative archs): the first arch that applies is kept, so a
# view whose structure differs from the expected one still gets the fields.
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
        # Choosing the dakproject and the ploeg on a shift is the whole point
        # of the team planner, so try a few anchors: the first one that fits
        # Odoo's own form wins.
        """
        <xpath expr="//field[@name='resource_id']" position="after">
            %s
        </xpath>
        """ % FORM_FIELDS,
        """
        <xpath expr="//sheet//group[1]" position="inside">
            %s
        </xpath>
        """ % FORM_FIELDS,
        """
        <xpath expr="//sheet" position="inside">
            <group>%s</group>
        </xpath>
        """ % FORM_FIELDS,
        """
        <xpath expr="//form" position="inside">
            <group>%s</group>
        </xpath>
        """ % FORM_FIELDS,
    ),
]


def _extend_planning_views(env):
    View = env["ir.ui.view"]
    for view_type, *archs in VIEW_EXTENSIONS:
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
            _extend_one_view(env, base, view_type, archs)


def _extend_one_view(env, base, view_type, archs):
    """Apply the first arch that fits, each try in its own savepoint."""
    View = env["ir.ui.view"]
    name = "planning.slot.%s.tectora.roof" % view_type
    existing = View.search(
        [("name", "=", name), ("inherit_id", "=", base.id)], limit=1
    )
    last_error = None
    for index, arch in enumerate(archs):
        values = {
            "name": name,
            "model": "planning.slot",
            "type": view_type,
            "inherit_id": base.id,
            "mode": "extension",
            "priority": 99,
            "arch_db": "<data>%s</data>" % arch,
        }
        try:
            # ir.ui.view.create/write validate the inheritance themselves
            # (_check_xml), so an xpath that does not resolve raises here.
            with env.cr.savepoint():
                if existing:
                    existing.write(values)
                else:
                    existing = View.create(values)
            _logger.info(
                "tectora_roof_planning: extended planning.slot %s view %s "
                "(variant %s)", view_type, base.id, index + 1,
            )
            return True
        except Exception as error:
            last_error = error
            existing = View.search(
                [("name", "=", name), ("inherit_id", "=", base.id)], limit=1
            )
    _logger.warning(
        "tectora_roof_planning: could not extend the planning.slot %s view "
        "(%s): %s", view_type, base.id, last_error,
    )
    return False


TEAM_ACTION_XMLID = "tectora_roof_planning.action_planning_slot_by_roof_team"
TEAM_MENU_XMLID = "tectora_roof_planning.menu_planning_slot_by_roof_team"
TEAMS_MENU_XMLID = "tectora_roof.menu_tectora_teams"
# Where the Planning app pointed before the team planner became the default,
# so uninstalling puts it back.
ROOT_ACTION_PARAM = "tectora_roof_planning.previous_planning_root_action"
PARENT_MENU_PARAM = "tectora_roof_planning.previous_teams_menu_parent"


def _action_model(menu):
    """res_model of the window action a menu points at, or "".

    ``ir.ui.menu.action`` is a reference field: a dangling one raises on read
    instead of coming back empty, so every read goes through here.
    """
    try:
        action = menu.action
        if not action or action._name != "ir.actions.act_window":
            return ""
        return action.res_model or ""
    except Exception:
        return ""


def _action_reference(menu):
    """"model,id" of the action a menu points at, or ""."""
    try:
        action = menu.action
        return "%s,%s" % (action._name, action.id) if action and action.id else ""
    except Exception:
        return ""


# Models whose menus mark a Planning configuration submenu.
CONFIG_MODEL_PREFIXES = ("planning.", "resource.")


def _planning_menus(env):
    """The Planning app's "Inplannen" and "Configuratie" menus.

    Planning is Enterprise, so its menu external ids cannot be relied on. They
    are found through the models their children act on: the schedule menu is
    the one with the most planning.slot children, and the configuration menu is
    another child of the same app whose own children configure planning.
    Returns (schedule, root, config); any of them may be empty.
    """
    Menu = env["ir.ui.menu"].with_context(active_test=False)
    ours = env.ref(TEAM_MENU_XMLID, raise_if_not_found=False)
    votes = {}
    for menu in Menu.search([]):
        if ours and menu == ours:
            continue  # our own menu must not decide where it belongs
        if menu.parent_id and _action_model(menu) == "planning.slot":
            votes[menu.parent_id] = votes.get(menu.parent_id, 0) + 1
    if not votes:
        return Menu, Menu, Menu
    schedule = max(votes, key=votes.get)
    root = schedule
    while root.parent_id:
        root = root.parent_id
    config = Menu.browse()
    for menu in Menu.search([("parent_id", "=", root.id)]):
        if menu == schedule or not menu.child_id:
            continue
        if any(
            _action_model(child).startswith(CONFIG_MODEL_PREFIXES)
            for child in menu.child_id
        ):
            config = menu
            break
    return schedule, root, config


def _install_team_planner(env):
    """Add "Per ploeg" to the Planning app and make it the planner it opens on."""
    Menu = env["ir.ui.menu"]
    action = env.ref(TEAM_ACTION_XMLID, raise_if_not_found=False)
    if not action:
        return
    schedule, root, config = _planning_menus(env)
    if not schedule:
        _logger.info(
            "tectora_roof_planning: no Planning schedule menu found; the team "
            "planner is reachable through its action only"
        )
        return
    reference = "%s,%s" % (action._name, action.id)
    siblings = Menu.with_context(active_test=False).search(
        [("parent_id", "=", schedule.id)]
    )
    ours = env.ref(TEAM_MENU_XMLID, raise_if_not_found=False)
    sequences = [menu.sequence for menu in siblings - (ours or Menu)]
    values = {
        "name": "Per ploeg",
        "parent_id": schedule.id,
        "action": reference,
        "sequence": (min(sequences) - 1) if sequences else 1,
    }
    menu = env.ref(TEAM_MENU_XMLID, raise_if_not_found=False)
    try:
        with env.cr.savepoint():
            if menu:
                menu.write(values)
            else:
                menu = Menu.create(values)
                env["ir.model.data"]._update_xmlids(
                    [{"xml_id": TEAM_MENU_XMLID, "record": menu, "noupdate": True}]
                )
            _logger.info(
                "tectora_roof_planning: team planner menu %s under %s",
                menu.id, schedule.complete_name,
            )
    except Exception as error:
        _logger.warning(
            "tectora_roof_planning: could not add the team planner menu: %s", error
        )
        return

    # The app itself opens on the team planner.
    Param = env["ir.config_parameter"].sudo()
    current_ref = _action_reference(root)
    if current_ref and current_ref != reference and not Param.get_param(
        ROOT_ACTION_PARAM
    ):
        Param.set_param(ROOT_ACTION_PARAM, current_ref)
    try:
        with env.cr.savepoint():
            root.action = reference
    except Exception as error:
        _logger.warning(
            "tectora_roof_planning: could not make the team planner the default "
            "planner: %s", error
        )

    # Teams are planning configuration, not measurement configuration.
    _move_teams_menu(env, config)


def _move_teams_menu(env, config):
    """Move "Ploegen" from the Dakmeting app to Planning -> Configuratie."""
    teams_menu = env.ref(TEAMS_MENU_XMLID, raise_if_not_found=False)
    if not teams_menu or not config:
        return
    if teams_menu.parent_id == config:
        return
    Param = env["ir.config_parameter"].sudo()
    if teams_menu.parent_id and not Param.get_param(PARENT_MENU_PARAM):
        Param.set_param(PARENT_MENU_PARAM, str(teams_menu.parent_id.id))
    try:
        with env.cr.savepoint():
            teams_menu.write({"parent_id": config.id, "sequence": 90})
        _logger.info(
            "tectora_roof_planning: moved the Ploegen menu to %s",
            config.complete_name,
        )
    except Exception as error:
        _logger.warning(
            "tectora_roof_planning: could not move the Ploegen menu: %s", error
        )


def post_init_hook(env):
    _extend_planning_views(env)
    _install_team_planner(env)
    # Existing shifts get their roof project from their work block or from the
    # project dossier they hang on.
    slots = env["planning.slot"].search([])
    if slots:
        slots._tectora_derive_roof_project()


def uninstall_hook(env):
    """Give the Planning app its own default planner and menu layout back."""
    Param = env["ir.config_parameter"].sudo()
    _schedule, root, _config = _planning_menus(env)
    previous = Param.get_param(ROOT_ACTION_PARAM)
    action = env.ref(TEAM_ACTION_XMLID, raise_if_not_found=False)
    ours = "%s,%s" % (action._name, action.id) if action else ""
    if root and _action_reference(root) == ours:
        # Without a stored previous action the menu had none: clear it rather
        # than leave it pointing at the action this uninstall is about to
        # delete, so Odoo falls back on the first child menu again. A default
        # somebody changed since is left alone.
        try:
            with env.cr.savepoint():
                root.action = previous or False
        except Exception as error:
            _logger.warning(
                "tectora_roof_planning: could not restore the Planning app's "
                "default action: %s", error
            )
    Param.set_param(ROOT_ACTION_PARAM, "")

    teams_menu = env.ref(TEAMS_MENU_XMLID, raise_if_not_found=False)
    parent_id = Param.get_param(PARENT_MENU_PARAM)
    if teams_menu and parent_id:
        try:
            with env.cr.savepoint():
                teams_menu.write({"parent_id": int(parent_id), "sequence": 80})
        except Exception as error:
            _logger.warning(
                "tectora_roof_planning: could not move the Ploegen menu back: %s",
                error,
            )
    Param.set_param(PARENT_MENU_PARAM, "")
