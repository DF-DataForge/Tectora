# -*- coding: utf-8 -*-
"""The projects overview: the start page of the Project app.

Key figures over all the projects of the roof projects (how many are running,
planned, not planned, past their end; order value, invoiced, still to
invoice, costs and margin), the projects on site this week, starting soon,
with the most still to invoice and with the lowest margin. Every figure and
every project in a list opens the projects behind it. Other modules add their
own sections through _tectora_overview_sections (phases, late orders).
"""
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.tools.misc import format_amount, format_date

# How many projects a list on the overview shows.
OVERVIEW_LIST_SIZE = 8
# "Starting soon": a planned start within this many days.
SOON_DAYS = 14


class ProjectProject(models.Model):
    _inherit = "project.project"

    @api.model
    def _tectora_overview_projects(self):
        """The projects the overview counts: those of a roof project."""
        return self.search([("is_template", "=", False), ("roof_project_id", "!=", False)])

    @api.model
    def tectora_get_overview_data(self):
        """Everything the projects overview shows."""
        projects = self._tectora_overview_projects()
        company = self.env.company
        currency = company.currency_id
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        done = projects.filtered(lambda project: project.roof_project_id.state == "done")
        active = projects - done
        blocks = self.env["tectora.roof.planning"].search([
            ("project_id.project_id", "in", active.ids),
            ("start_datetime", "<=", datetime.combine(week_end, time.max)),
            ("end_datetime", ">=", datetime.combine(week_start, time.min)),
        ])
        blocks_now = blocks.filtered(
            lambda block: block.start_datetime <= now <= block.end_datetime
        )

        def begin(project):
            return project.roof_planned_date_begin

        def end(project):
            return project.roof_planned_date_end

        running = active.filtered(
            lambda p: (begin(p) and begin(p) <= now and (not end(p) or end(p) >= now))
        ) | blocks_now.project_id.project_id
        planned = active.filtered(lambda p: begin(p) and begin(p) > now) - running
        unplanned = active.filtered(lambda p: not begin(p) and not p.roof_project_id.planning_ids)
        overdue = active.filtered(lambda p: end(p) and end(p) < now) - running
        soon = planned.filtered(
            lambda p: begin(p).date() <= today + timedelta(days=SOON_DAYS)
        ).sorted(begin)

        def money(amount):
            return format_amount(self.env, amount, currency)

        def tile(key, label, records, help_text, value=None, tone=""):
            return {
                "key": key,
                "label": label,
                "value": value if value is not None else len(records),
                "ids": records.ids,
                "help": help_text,
                "tone": tone,
            }

        status_tiles = [
            tile("active", _("Actieve projecten"), active,
                 _("Projecten waarvan het dakproject niet afgerond is.")),
            tile("running", _("Nu bezig"), running,
                 _("De geplande periode loopt, of een werkblok loopt nu."), tone="info"),
            tile("planned", _("Gepland"), planned,
                 _("Met een geplande start in de toekomst."), tone="primary"),
            tile("unplanned", _("Niet ingepland"), unplanned,
                 _("Zonder geplande start en zonder werkblokken."), tone="warning"),
            tile("overdue", _("Einddatum voorbij"), overdue,
                 _("Het geplande einde is voorbij, maar het dakproject is niet afgerond."),
                 tone="danger"),
            tile("done", _("Afgerond"), done,
                 _("Projecten waarvan het dakproject afgerond is."), tone="success"),
        ]

        # Money: over all projects (finished ones may still have to be
        # invoiced), with the same totals as the project dashboard.
        totals = projects._tectora_profitability_by_project()
        figures = {}
        for project in projects:
            order = project.tectora_sale_order_id
            revenue = order.amount_untaxed if order and order.state in ("sale", "done") else 0.0
            project_totals = totals.get(project.id, {})
            invoiced = project_totals.get("invoiced", 0.0)
            to_invoice = project_totals.get("to_invoice", 0.0)
            costs = -project_totals.get("billed", 0.0) - project_totals.get("to_bill", 0.0)
            turnover = invoiced + to_invoice
            if not turnover and not project_totals:
                turnover = revenue
            figures[project.id] = {
                "revenue": revenue,
                "invoiced": invoiced,
                "to_invoice": to_invoice,
                "costs": costs,
                "margin": turnover - costs,
                "turnover": turnover,
            }

        def total(key):
            return sum(values[key] for values in figures.values())

        with_order = projects.filtered(lambda p: figures[p.id]["revenue"])
        to_invoice_projects = projects.filtered(lambda p: figures[p.id]["to_invoice"] > 0.005)
        with_costs = projects.filtered(lambda p: figures[p.id]["costs"])
        turnover = total("turnover")
        margin = total("margin")
        money_tiles = [
            tile("revenue", _("Orderwaarde"), with_order,
                 _("Bedrag excl. btw van de bevestigde orders."), value=money(total("revenue"))),
            tile("invoiced", _("Gefactureerd"), projects.filtered(lambda p: figures[p.id]["invoiced"]),
                 _("Gefactureerd op de orders, excl. btw."), value=money(total("invoiced"))),
            tile("to_invoice", _("Nog te factureren"), to_invoice_projects,
                 _("Nog te factureren op de orders, excl. btw."),
                 value=money(total("to_invoice")), tone="warning"),
            tile("costs", _("Kosten"), with_costs,
                 _("Geboekte kosten en bestelde, nog niet gefactureerde aankopen."),
                 value=money(total("costs"))),
            tile("margin", _("Marge"), with_order | with_costs,
                 _("Omzet min kosten, zoals op het projectdashboard."),
                 value=money(margin),
                 tone="success" if margin >= 0 else "danger"),
        ]

        def item(project, sub="", value="", tone=""):
            return {
                "id": project.id,
                "name": project.display_name,
                "partner": project.partner_id.display_name or "",
                "sub": sub,
                "value": value,
                "tone": tone,
            }

        def day(value):
            return format_date(self.env, value, date_format="EEE d MMM") if value else ""

        # On site this week: the work blocks of the week, per project.
        week = []
        for project in blocks.project_id.project_id.sorted("name"):
            project_blocks = blocks.filtered(lambda b: b.project_id.project_id == project)
            first = min(project_blocks.mapped("start_datetime"))
            last = max(project_blocks.mapped("end_datetime"))
            teams = ", ".join(project_blocks.team_id.mapped("name"))
            week.append(item(
                project,
                sub=" · ".join(filter(None, [
                    teams,
                    f"{day(fields.Datetime.context_timestamp(self, first))} – "
                    f"{day(fields.Datetime.context_timestamp(self, last))}",
                ])),
                tone="info" if project in blocks_now.project_id.project_id else "",
            ))
        week.sort(key=lambda entry: entry["tone"] != "info")

        lists = [
            {
                "key": "week",
                "title": _("Deze week op de werf"),
                "empty": _("Geen werkblokken deze week."),
                "items": week[:OVERVIEW_LIST_SIZE * 2],
                "ids": blocks.project_id.project_id.ids,
            },
            {
                "key": "soon",
                "title": _("Start binnenkort (%s dagen)", SOON_DAYS),
                "empty": _("Geen projecten die binnenkort starten."),
                "items": [
                    item(p, sub=p.roof_team_id.name or _("Nog geen ploeg"),
                         value=day(fields.Datetime.context_timestamp(self, begin(p))))
                    for p in soon[:OVERVIEW_LIST_SIZE]
                ],
                "ids": soon.ids,
            },
            {
                "key": "to_invoice",
                "title": _("Meest nog te factureren"),
                "empty": _("Niets meer te factureren."),
                "items": [
                    item(p, value=money(figures[p.id]["to_invoice"]), tone="warning")
                    for p in to_invoice_projects.sorted(
                        lambda p: -figures[p.id]["to_invoice"]
                    )[:OVERVIEW_LIST_SIZE]
                ],
                "ids": to_invoice_projects.ids,
            },
            {
                "key": "margin",
                "title": _("Laagste marge"),
                "empty": _("Nog geen projecten met omzet."),
                "items": [
                    item(
                        p,
                        sub=_("Omzet %s", money(figures[p.id]["turnover"])),
                        value="%s (%.0f%%)" % (
                            money(figures[p.id]["margin"]),
                            figures[p.id]["margin"] / figures[p.id]["turnover"] * 100.0,
                        ),
                        tone="danger" if figures[p.id]["margin"] < 0 else "",
                    )
                    for p in projects.filtered(lambda p: figures[p.id]["turnover"] > 0).sorted(
                        lambda p: figures[p.id]["margin"] / figures[p.id]["turnover"]
                    )[:OVERVIEW_LIST_SIZE]
                ],
                "ids": [],
            },
        ]

        return {
            "company": company.name,
            "today": format_date(self.env, today, date_format="EEEE d MMMM y"),
            "margin_percent": "%.1f %%" % (margin / turnover * 100.0) if turnover else "",
            "status_tiles": status_tiles,
            "money_tiles": money_tiles,
            "sections": self._tectora_overview_sections(active),
            "lists": lists,
        }

    @api.model
    def _tectora_overview_sections(self, active):
        """Extra sections of the overview, from other modules: a list of
        {"key", "title", "items": [{"label", "value", "ids", "help", "tone"}]},
        shown as bars; `active` are the projects not finished yet."""
        return []

    @api.model
    def action_tectora_overview_open_projects(self, project_ids, title=False):
        """The projects behind a figure of the overview, in the views of the
        Projecten menu (cards, list, dashboard)."""
        action = self.env["ir.actions.actions"]._for_xml_id("tectora_roof.action_tectora_projects")
        action.update({
            "name": title or action.get("name"),
            "domain": [("id", "in", list(project_ids or []))],
            "context": {},
        })
        return action
