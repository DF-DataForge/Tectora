# -*- coding: utf-8 -*-
"""The project planner's place in the Project app.

Its own menus (Project -> Planning) are plain data. The Ploegen menu belongs
to tectora_roof (noupdate, under Dakmeting): with the planner installed it is
moved to Project -> Configuratie, since the teams are what gets planned, and
uninstalling puts it back. Runs in a savepoint and only logs on failure, so a
menu that is not where it is expected never breaks the install.
"""
import logging

_logger = logging.getLogger(__name__)

TEAMS_MENU_XMLID = "tectora_roof.menu_tectora_teams"
PROJECT_CONFIG_MENU_XMLID = "project.menu_project_config"
ROOF_ROOT_MENU_XMLID = "tectora_roof.menu_tectora_root"


def _move_teams_menu(env, parent_xmlid=PROJECT_CONFIG_MENU_XMLID, sequence=90):
    """Move "Ploegen" under ``parent_xmlid``."""
    teams_menu = env.ref(TEAMS_MENU_XMLID, raise_if_not_found=False)
    parent = env.ref(parent_xmlid, raise_if_not_found=False)
    if not teams_menu or not parent or teams_menu.parent_id == parent:
        return
    try:
        with env.cr.savepoint():
            teams_menu.write({"parent_id": parent.id, "sequence": sequence})
        _logger.info(
            "tectora_roof_planning: moved the Ploegen menu to %s", parent.complete_name
        )
    except Exception as error:
        _logger.warning(
            "tectora_roof_planning: could not move the Ploegen menu: %s", error
        )


def post_init_hook(env):
    _move_teams_menu(env)


def uninstall_hook(env):
    """Ploegen goes back to the Dakmeting app."""
    _move_teams_menu(env, ROOF_ROOT_MENU_XMLID, sequence=80)
