# -*- coding: utf-8 -*-
"""One set of task stages for all projects of the roof projects.

Odoo 20 gives every new project four task stages of its own (New, In
Progress, Done, Cancelled), so every confirmed order added four more. The
projects now share Nieuw / Bezig / Klaar / Geannuleerd: here the projects
already made move their tasks to the shared stage of the same meaning, drop
their own copies, and those copies are removed once nothing uses them.
Stages with another name (made by hand) are left alone."""
import logging

from odoo import SUPERUSER_ID, Command, api

_logger = logging.getLogger(__name__)

# Shared stage -> names (any language) of the stages it replaces.
STAGE_NAMES = {
    "tectora_roof.project_task_type_nieuw": {"new", "nieuw"},
    "tectora_roof.project_task_type_bezig": {"in progress", "in uitvoering", "bezig",
                                             "lopend"},
    "tectora_roof.project_task_type_klaar": {"done", "klaar", "gedaan", "voltooid"},
    "tectora_roof.project_task_type_geannuleerd": {"cancelled", "canceled",
                                                   "geannuleerd"},
}
QUIET = {"tracking_disable": True, "mail_notrack": True, "active_test": False}


def _names(stage):
    names = set()
    for lang in ("en_US", "nl_BE", "nl_NL"):
        names.add((stage.with_context(lang=lang).name or "").strip().lower())
    return names


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    shared = {}
    for xmlid, names in STAGE_NAMES.items():
        stage = env.ref(xmlid, raise_if_not_found=False)
        if stage:
            shared[stage] = names
    if not shared:
        return
    shared_stages = env["project.task.type"].union(*shared)
    Task = env["project.task"].with_context(**QUIET)
    projects = env["tectora.roof.project"].with_context(active_test=False).search(
        [("project_id", "!=", False)]
    ).project_id.with_context(**QUIET)
    replaced = env["project.task.type"]
    for project in projects:
        commands = [Command.link(stage.id) for stage in shared_stages]
        for stage in project.type_ids - shared_stages:
            stage_names = _names(stage)
            target = next(
                (shared_stage for shared_stage, names in shared.items()
                 if stage_names & names),
                None,
            )
            if not target:
                continue
            Task.search([("project_id", "=", project.id), ("stage_id", "=", stage.id)]).write(
                {"stage_id": target.id}
            )
            commands.append(Command.unlink(stage.id))
            replaced |= stage
        project.write({"type_ids": commands})

    removed = 0
    for stage in replaced.with_context(active_test=False):
        if stage.project_ids or Task.search_count([("stage_id", "=", stage.id)]):
            continue  # still used by a project outside Tectora, or a task
        try:
            with cr.savepoint():
                stage.unlink()
                removed += 1
        except Exception:
            _logger.warning("Task stage %s (%s) could not be removed", stage.id, stage.name)
    _logger.info(
        "tectora_roof: %s projects on the shared task stages, %s stages removed",
        len(projects), removed,
    )
