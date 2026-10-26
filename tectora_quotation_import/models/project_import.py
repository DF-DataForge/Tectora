# -*- coding: utf-8 -*-
"""Import of the projects of the old system (Simpla project export), after
the quotations: every project is linked to the imported order(s) it was made
from, its roof project and project get the data of the old project, and it
is planned on the existing roofing teams."""
import logging
from datetime import datetime, time

import pytz
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import project_rules
from .import_job import QUIET

_logger = logging.getLogger(__name__)

# Working hours of a planned work block, in the planner's time zone.
DAY_START = time(7, 30)
DAY_END = time(16, 30)
DEFAULT_TZ = "Europe/Brussels"


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    tectora_legacy_project_number = fields.Char(
        string="Projectnummer oud systeem", copy=False, index=True, readonly=True,
    )
    tectora_legacy_project_status = fields.Char(
        string="Projectstatus oud systeem", copy=False, readonly=True,
    )


class ProjectImportTeam(models.Model):
    """Which roofing team(s) a 'verantwoordelijke gebruiker' of the old
    system is. Filled in by the import with its best guess (the team whose
    name it holds); correct it here and import again."""

    _name = "tectora.project.import.team"
    _description = "Ploeg van een verantwoordelijke (projectimport)"
    _order = "name"

    name = fields.Char(string="Verantwoordelijke oud systeem", required=True)
    team_ids = fields.Many2many(
        "tectora.roof.team", string="Ploeg(en)",
        help="Leeg: projecten van deze verantwoordelijke krijgen geen ploeg en "
        "worden niet ingepland. Met meer dan één ploeg krijgt het project de "
        "eerste en het werkblok de leden van alle ploegen.",
    )
    project_count = fields.Integer(string="Projecten (laatste import)", readonly=True)

    @api.model
    def _key(self, name):
        return project_rules._key(name)


class QuotationImportOptions(models.AbstractModel):
    _inherit = "tectora.quotation.import.options"

    create_missing_teams = fields.Boolean(
        string="Ontbrekende ploegen aanmaken",
        default=True,
        help="Projecten: een verantwoordelijke van het oude systeem die geen "
        "bestaande ploeg is (bv. een onderaannemer), krijgt een nieuwe "
        "dakwerkersploeg met zijn naam; een ploeg met precies die naam wordt "
        "hergebruikt. Leden en ploegbaas vul je nadien in.",
    )

    # -------------------------------------------------------- the projects
    def _parse_projects(self):
        header, rows = self._read_rows()
        try:
            projects = project_rules.parse_rows(header, rows)
        except ValueError as error:
            raise UserError(str(error))
        if not projects:
            raise UserError(_("Geen projecten gevonden in het bestand."))
        return projects

    def _project_orders(self):
        """The imported orders, as project_rules.match_projects reads them."""
        orders = self.env["sale.order"].search([
            ("tectora_legacy_number", "!=", False),
            ("state", "!=", "cancel"),
            ("company_id", "=", self.env.company.id),
        ], order="id")
        return orders, [
            {
                "id": order.id,
                "names": {order.partner_id.name or "",
                          order.partner_id.commercial_partner_id.name or ""},
                "vat": project_rules.normalise_vat(order.partner_id.commercial_partner_id.vat),
                "total": order.amount_untaxed,
                "lines": len(order.order_line.filtered(lambda line: not line.display_type)),
                "confirmed": order.state == "sale",
                "project": order.roof_project_id.tectora_legacy_project_number or None,
            }
            for order in orders
        ]

    def _project_teams(self, projects, create):
        """``(teams, new)``: {responsible key: teams} from the team table, and
        the responsibles that get a team of their own.

        A responsible not in the table yet gets the guessed teams (and, with
        ``create``, a row). With "Ontbrekende ploegen aanmaken", a responsible
        without any team gets a new roofing team of that name (an existing
        team of exactly that name is reused); only with ``create``, else it is
        only listed in ``new``.
        """
        Map = self.env["tectora.project.import.team"]
        Team = self.env["tectora.roof.team"].with_context(active_test=False)
        rows = {Map._key(row.name): row for row in Map.search([])}
        teams = self.env["tectora.roof.team"].search([])
        pairs = [(team.id, team.name) for team in teams]
        result = {}
        new = []
        counts = {}
        for project in projects:
            key = Map._key(project["responsible"])
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
            if key in result:
                continue
            row = rows.get(key)
            found = row.team_ids if row else teams.browse(
                project_rules.guess_teams(project["responsible"], pairs)
            )
            if not found and self.create_missing_teams:
                new.append(project["responsible"])
                if create:
                    found = Team.search([("name", "=ilike", project["responsible"])], limit=1)
                    if found and not found.active:
                        found.active = True
                    found = found or Team.create({"name": project["responsible"]})
            result[key] = found
            if create:
                if row:
                    if found and not row.team_ids:
                        row.team_ids = found
                else:
                    rows[key] = Map.create({"name": project["responsible"],
                                            "team_ids": [(6, 0, found.ids)]})
        if create:
            for key, row in rows.items():
                if key in counts and row.project_count != counts[key]:
                    row.project_count = counts[key]
        return result, new


class QuotationImportJob(models.Model):
    _inherit = "tectora.quotation.import.job"

    def _run_prepare(self):
        if self.kind != "projects":
            return super()._run_prepare()
        projects = self._parse_projects()
        orders, order_data = self._project_orders()
        assignment, ambiguous = project_rules.match_projects(projects, order_data)
        user = self.create_uid or self.env.user
        return projects, {"ambiguous": ambiguous}, {
            "assignment": assignment,
            "teams": self._project_teams(projects, create=True)[0],
            "tz": user.tz or self.env.user.tz or DEFAULT_TZ,
        }

    def _run_counters(self):
        if self.kind != "projects":
            return super()._run_counters()
        return {
            "linked": 0, "updated": 0, "skipped": 0, "roofs_created": 0,
            "projects_created": 0, "planned": 0, "closed": 0,
            "unmatched": [], "not_confirmed": [], "no_team": {},
            "no_deadline": 0, "description_cut": 0, "errors": [],
        }

    def _run_item(self, project, run, counters):
        if self.kind != "projects":
            return super()._run_item(project, run, counters)
        order_ids = run["assignment"].get(project["number"])
        if not order_ids:
            counters["unmatched"].append("%s %s" % (project["number"], project["name"]))
            return
        try:
            with self.env.cr.savepoint():
                self._link_project(project, self.env["sale.order"].browse(order_ids),
                                   run, counters)
        except Exception as error:
            _logger.exception("tectora_quotation_import: project %s", project["number"])
            counters["errors"].append("%s: %s" % (project["number"], error))

    def _link_project(self, project, orders, run, counters):
        number = project["number"]
        phase = project_rules.phase(project["status"])
        key = self.env["tectora.project.import.team"]._key(project["responsible"])
        teams = run["teams"].get(key) or self.env["tectora.roof.team"]
        if key and not teams:
            counters["no_team"][project["responsible"]] = (
                counters["no_team"].get(project["responsible"], 0) + 1
            )
        if project["description_cut"]:
            counters["description_cut"] += 1
        known = all(
            order.roof_project_id.tectora_legacy_project_number == number for order in orders
        )
        if known and self.existing_mode == "skip":
            counters["skipped"] += 1
            return
        planned_roof = None
        for order in orders:
            order = order.with_context(**QUIET)
            roof = order.roof_project_id
            if not roof:
                # A finished site imported without roof project gets it now.
                order._tectora_create_roof_project(raise_if_failed=True)
                roof = order.roof_project_id
                counters["roofs_created"] += 1
            roof = roof.with_context(**QUIET)
            if order.state == "sale" and not roof.project_id:
                roof._ensure_project()
                counters["projects_created"] += 1
            elif order.state != "sale":
                counters["not_confirmed"].append("%s (%s)" % (number, order.name))
            values = {
                "tectora_legacy_project_number": number,
                "tectora_legacy_project_status": project["status"],
            }
            if teams:
                values["team_id"] = teams[:1].id
            if project["deadline"]:
                values["date_deadline"] = project["deadline"]
            if project["site"]:
                values["address"] = project["site"]
            if phase == "closed":
                values["state"] = "done"
            elif order.state == "sale" and roof.state not in ("confirmed", "done"):
                values["state"] = "confirmed"
            roof.write(values)
            if project["description"] and roof.project_id \
                    and not roof.project_id.description:
                roof.project_id.with_context(**QUIET).description = Markup("<p>%s</p>") % (
                    Markup("<br/>").join(escape(l) for l in project["description"].splitlines())
                )
            if planned_roof is None:
                planned_roof = roof
        if self.plan_projects and planned_roof:
            if not project["deadline"]:
                counters["no_deadline"] += 1
            elif teams and not planned_roof.planning_ids:
                self._plan_project(planned_roof, orders, teams, project, phase, run["tz"])
                counters["planned"] += 1
        counters["updated" if known else "linked"] += 1
        if phase == "closed":
            counters["closed"] += 1

    def _plan_project(self, roof, orders, teams, project, phase, tz_name):
        """A work block of the team(s), ending on the deadline and as many
        working days long as the orders are estimated at."""
        days = sum(orders.mapped("tectora_estimated_days"))
        first, last = project_rules.working_days_window(project["deadline"], days)
        tz = pytz.timezone(tz_name)

        def utc(day, moment):
            local = tz.localize(datetime.combine(day, moment))
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        roof.write({
            "planned_date_begin": utc(first, DAY_START),
            "planned_date_end": utc(last, DAY_END),
        })
        blocks = roof.planning_ids or roof._create_planning_item()
        values = {"state": "done" if phase in ("closed", "executed") else "published"}
        if len(teams) > 1:
            values["employee_ids"] = [(6, 0, teams.member_ids.ids)]
        blocks.write(values)

    def _run_summary(self, projects, stats, counters):
        if self.kind != "projects":
            return super()._run_summary(projects, stats, counters)
        lines = [
            _("Bestand: %(file)s — %(n)s projecten", file=self.filename or "-", n=len(projects)),
            _("%(new)s projecten gekoppeld aan hun order(s), %(upd)s bijgewerkt, "
              "%(skip)s overgeslagen (al gekoppeld)",
              new=counters["linked"], upd=counters["updated"], skip=counters["skipped"]),
            _("%(roofs)s dakprojecten en %(projects)s projecten aangemaakt voor orders "
              "die er nog geen hadden", roofs=counters["roofs_created"],
              projects=counters["projects_created"]),
            _("%s projecten afgesloten (dakproject afgerond)", counters["closed"]),
        ]
        if self.plan_projects:
            lines.append(_("%(planned)s werkblokken ingepland op hun ploeg; %(none)s "
                           "projecten zonder deadline niet ingepland",
                           planned=counters["planned"], none=counters["no_deadline"]))
        if counters["no_team"]:
            lines.append(_(
                "Zonder ploeg (vul de ploeg in bij Ploegen projectimport en "
                "importeer opnieuw): %s",
                ", ".join("%s (%s)" % item for item in sorted(counters["no_team"].items())),
            ))
        if counters["unmatched"]:
            lines.append(_("Geen order gevonden (klant + totaal offertes): %s",
                           ", ".join(counters["unmatched"])))
        if stats.get("ambiguous"):
            lines.append(_("Meer dan één passende order (de eerste genomen, kijk na): %s",
                           ", ".join(stats["ambiguous"])))
        if counters["not_confirmed"]:
            lines.append(_("Gekoppeld aan een offerte die nog niet bevestigd is "
                           "(geen project in Odoo tot ze bevestigd wordt): %s",
                           ", ".join(counters["not_confirmed"])))
        if counters["description_cut"]:
            lines.append(_("%s projectomschrijvingen niet overgenomen: de export "
                           "kapt ze af", counters["description_cut"]))
        if counters["errors"]:
            lines += ["", _("%s projecten NIET verwerkt door een fout:", len(counters["errors"]))]
            lines += ["    " + error for error in counters["errors"]]
        return "\n".join(lines)
