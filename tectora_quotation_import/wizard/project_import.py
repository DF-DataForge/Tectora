# -*- coding: utf-8 -*-
from odoo import _, fields, models

from ..models import project_rules


class ProjectImport(models.TransientModel):
    """Checks the project export and hands it to an import job (kind
    "projects"), which links every project to its orders in the background."""

    _name = "tectora.project.import"
    _inherit = ["tectora.quotation.import.options"]
    _description = "Projecten importeren uit het oude systeem"

    file = fields.Binary(string="Bestand (.xlsx)", required=True, attachment=False)
    filename = fields.Char(string="Bestandsnaam")
    dry_run = fields.Boolean(
        string="Testrun (enkel controleren)",
        help="Toont welke projecten aan welke order gekoppeld worden en op welke "
        "ploeg ze komen, zonder iets te wijzigen.",
    )
    plan_projects = fields.Boolean(
        string="Werkblokken inplannen",
        default=True,
        help="Een project met een ploeg en een deadline krijgt een werkblok op "
        "die ploeg dat op de deadline eindigt en zoveel werkdagen duurt als de "
        "order geschat is (minstens 1). Afgesloten en uitgevoerde projecten "
        "krijgen een blok 'Uitgevoerd', de andere 'Ingepland'.",
    )
    state = fields.Selection([("draft", "Concept"), ("done", "Uitgevoerd")], default="draft")
    summary = fields.Text(string="Resultaat", readonly=True)

    def action_import(self):
        self.ensure_one()
        projects = self._parse_projects()
        if self.dry_run:
            self.write({"state": "done", "summary": self._preview(projects)})
            return {
                "type": "ir.actions.act_window",
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
                "context": self.env.context,
            }
        job = self.env["tectora.quotation.import.job"].create({
            "kind": "projects",
            "name": _("%(file)s (%(count)s projecten)",
                      file=self.filename or _("Projecten"), count=len(projects)),
            "file": self.file,
            "filename": self.filename,
            "sheet_name": self.sheet_name,
            "existing_mode": self.existing_mode,
            "plan_projects": self.plan_projects,
            "create_missing_teams": self.create_missing_teams,
            "quote_count": len(projects),
        })
        job._trigger_cron()
        return {
            "type": "ir.actions.act_window",
            "res_model": job._name,
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }

    def _preview(self, projects):
        orders, order_data = self._project_orders()
        assignment, ambiguous = project_rules.match_projects(projects, order_data)
        teams, new_teams = self._project_teams(projects, create=False)
        names = {order.id: order.name for order in orders}
        states = {order.id: order.state for order in orders}
        phases = {}
        multiple = []
        not_confirmed = []
        for project in projects:
            ids = assignment.get(project["number"])
            if not ids:
                continue
            phase = project_rules.phase(project["status"])
            phases[phase] = phases.get(phase, 0) + 1
            if len(ids) > 1:
                multiple.append("%s → %s" % (project["number"], ", ".join(names[i] for i in ids)))
            not_confirmed += [names[i] for i in ids if states[i] != "sale"]
        unmatched = ["%s %s" % (p["number"], p["name"]) for p in projects
                     if p["number"] not in assignment]
        Map = self.env["tectora.project.import.team"]
        per_team = {}
        for project in projects:
            key = Map._key(project["responsible"])
            if key:
                per_team.setdefault(project["responsible"], [0, teams.get(key)])[0] += 1
        planned = sum(
            1 for p in projects
            if p["number"] in assignment and p["deadline"]
            and (teams.get(Map._key(p["responsible"])) or p["responsible"] in new_teams)
        )
        phase_labels = {"closed": _("afgesloten"), "executed": _("uitgevoerd"),
                        "open": _("lopend")}
        lines = [
            _("TESTRUN: er werd niets gewijzigd."),
            "",
            _("Bestand: %(file)s — %(n)s projecten", file=self.filename or "-", n=len(projects)),
            _("%(n)s projecten gevonden bij hun order(s): %(phases)s",
              n=len(assignment), phases=", ".join(
                  "%s %s" % (count, phase_labels[phase]) for phase, count in sorted(phases.items()))),
        ]
        if multiple:
            lines.append(_("Projecten met meer dan één order: %s", "; ".join(multiple)))
        if ambiguous:
            lines.append(_("Meer dan één passende order (de eerste genomen): %s",
                           ", ".join(ambiguous)))
        if not_confirmed:
            lines.append(_("Gekoppeld aan een offerte die nog niet bevestigd is: %s",
                           ", ".join(not_confirmed)))
        if unmatched:
            lines.append(_("Geen order gevonden: %s", ", ".join(unmatched)))
        lines += ["", _("Ploegen (verantwoordelijke → ploeg):")]
        for responsible, (count, found) in sorted(per_team.items(), key=lambda i: -i[1][0]):
            if found:
                target = ", ".join(found.mapped("name"))
            elif responsible in new_teams:
                target = _("NIEUWE PLOEG '%s'", responsible)
            else:
                target = _("GEEN PLOEG")
            lines.append("    %s (%s) → %s" % (responsible, count, target))
        if self.plan_projects:
            lines.append(_("%s projecten met ploeg en deadline worden ingepland", planned))
        return "\n".join(lines)
