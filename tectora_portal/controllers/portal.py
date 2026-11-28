# -*- coding: utf-8 -*-
"""The crew's portal: /my/werven.

Every route resolves the logged-in user to their contact and only shows the
roof projects that contact is planned on (see
``tectora.roof.project._tectora_portal_domain``). The records are read and
written with sudo after that check, the way the standard portal controllers
work with their access tokens, so the portal group needs no access rights on
the roofing models.
"""
import logging
from datetime import date as date_type
from urllib.parse import quote_plus, urlencode

from werkzeug.exceptions import NotFound

from odoo import _, fields, http
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.tools.image import image_data_uri
from odoo.fields import Domain

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

_logger = logging.getLogger(__name__)

TABS = ("overview", "materials", "plan", "report")
PDF_REPORTS = {
    "meetblad": ("tectora_roof.action_report_roof_project", "Meetblad"),
    "werfblad": ("tectora_roof.action_report_roof_project_info", "Werfblad"),
}
MAX_PHOTOS = 20
MAX_PHOTO_BYTES = 15 * 1024 * 1024


class TectoraEmployeePortal(CustomerPortal):

    # ------------------------------------------------------------- resolving
    def _tectora_worker(self):
        """The contact behind the logged-in user (portal or internal) when
        it works on the sites: in a ploeg, planned on a work block, or an
        worker. The portal runs on that contact; no worker is needed."""
        Partner = request.env["res.partner"].sudo()
        user = request.env.user
        if not user or user._is_public():
            return Partner
        partner = user.partner_id.sudo()
        if partner._tectora_is_worker():
            return partner
        # A login linked to an worker whose work contact is another contact.
        worker = request.env["hr.employee"].sudo().search(
            [("user_id", "=", user.id)], order="company_id", limit=1
        )
        return worker.work_contact_id if worker else Partner

    def _tectora_sites_domain(self, worker):
        return request.env["tectora.roof.project"].sudo()._tectora_portal_domain(worker)

    def _tectora_site_for(self, worker, project_id):
        Project = request.env["tectora.roof.project"].sudo()
        project = Project.search(
            Domain.AND([[("id", "=", project_id)], self._tectora_sites_domain(worker)]),
            limit=1,
        )
        if not project:
            raise NotFound()
        return project

    def _tectora_site_url(self, project, tab="overview", message=None, error=None):
        params = {"tab": tab if tab in TABS else "overview"}
        if message:
            params["message"] = message
        if error:
            params["error"] = error
        return "/my/werven/%d?%s" % (project.id, urlencode(params))

    def _tectora_tab(self, worker, tab):
        """``tab`` if the worker sees that segment, else their first
        visible tab (``overview`` when none is)."""
        segments = worker._tectora_portal_segments()
        if tab in TABS and segments.get(tab):
            return tab
        return next((name for name in TABS if segments.get(name)), "overview")

    def _tectora_segment_refused(self, worker, project, segment, tab):
        """A redirect when ``segment`` is hidden for the worker, else None."""
        if worker._tectora_portal_segments().get(segment):
            return None
        return request.redirect(self._tectora_site_url(
            project, self._tectora_tab(worker, tab),
            error=_("Dit onderdeel staat niet open op jouw portaal."),
        ))

    def _tectora_no_worker(self, values=None):
        values = dict(values or self._prepare_portal_layout_values())
        values["page_name"] = "tectora_sites"
        return request.render("tectora_portal.portal_no_employee", values)

    # ------------------------------------------------------------------ home
    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        values["tectora_worker"] = self._tectora_worker()
        return values

    def _prepare_portal_counter_values(self, counter):
        """The counter of the card "Mijn werven" (data/portal_entry_data.xml):
        the sites the logged-in worker is on."""
        if counter == "tectora_site_count":
            worker = self._tectora_worker()
            domain = self._tectora_sites_domain(worker) if worker else [("id", "=", False)]
            return "tectora.roof.project", domain, "sudo"
        return super()._prepare_portal_counter_values(counter)

    # ------------------------------------------------------------------ list
    @http.route(
        ["/my/werven", "/my/werven/page/<int:page>"],
        type="http", auth="user", website=True,
    )
    def portal_my_sites(self, page=1, sortby=None, filterby=None, search=None,
                        search_in="all", **kw):
        values = self._prepare_portal_layout_values()
        worker = values["tectora_worker"]
        if not worker:
            return self._tectora_no_worker(values)
        Project = request.env["tectora.roof.project"].sudo()
        now = fields.Datetime.now()
        day_start, day_end = Project._tectora_portal_day_bounds(now)
        planned_domain = [("end_datetime", ">=", day_start)]
        horizon_end = worker._tectora_portal_horizon_end(now)
        if horizon_end:
            planned_domain.append(("start_datetime", "<", horizon_end))

        searchbar_filters = {
            "planned": {
                "label": _("Gepland"),
                "domain": [("planning_ids", "any", planned_domain)],
            },
            "today": {
                "label": _("Vandaag"),
                "domain": [
                    ("planning_ids", "any", [
                        ("start_datetime", "<", day_end),
                        ("end_datetime", ">", day_start),
                    ]),
                ],
            },
            "running": {
                "label": _("Uren lopen"),
                "domain": [("timer_ids", "any", [("state", "=", "running")])],
            },
            "all": {"label": _("Alle werven"), "domain": []},
        }
        searchbar_sortings = {
            "date": {"label": _("Geplande datum"), "order": "planned_date_begin asc, id desc"},
            "name": {"label": _("Project"), "order": "name asc, id desc"},
            "customer": {"label": _("Klant"), "order": "partner_id asc, id desc"},
            "state": {"label": _("Status"), "order": "state asc, id desc"},
        }
        searchbar_inputs = {
            "all": {"input": "all", "label": _("Zoek op project, klant of werfadres")},
        }
        if filterby not in searchbar_filters:
            filterby = "planned"
        if sortby not in searchbar_sortings:
            sortby = "date"

        filter_domain = searchbar_filters[filterby]["domain"]
        # Nothing planned (yet) is shown on the "planned" filter as well, so a
        # freshly assigned site never disappears from the crew's list.
        if filterby == "planned":
            filter_domain = Domain.OR([filter_domain, [("planning_ids", "=", False)]])
        domain = Domain.AND([self._tectora_sites_domain(worker), filter_domain])
        if search:
            domain = Domain.AND([domain, [
                "|", "|", "|",
                ("name", "ilike", search),
                ("code", "ilike", search),
                ("partner_id.name", "ilike", search),
                ("address", "ilike", search),
            ]])

        count = Project.search_count(domain)
        url_args = {"sortby": sortby, "filterby": filterby, "search": search, "search_in": search_in}
        pager = portal_pager(
            url="/my/werven", url_args=url_args, total=count, page=page,
            step=self._items_per_page,
        )
        projects = Project.search(
            domain, order=searchbar_sortings[sortby]["order"],
            limit=self._items_per_page, offset=pager["offset"],
        )
        request.session["tectora_sites_history"] = projects.ids[:100]

        values.update({
            "page_name": "tectora_sites",
            "worker": worker,
            "projects": projects,
            "now": now,
            "next_blocks": {
                project.id: project._tectora_portal_next_block(now, worker)
                for project in projects
            },
            "pager": pager,
            "default_url": "/my/werven",
            "searchbar_sortings": searchbar_sortings,
            "sortby": sortby,
            "searchbar_filters": searchbar_filters,
            "filterby": filterby,
            "searchbar_inputs": searchbar_inputs,
            "search_in": search_in,
            "search": search,
        })
        return request.render("tectora_portal.portal_my_sites", values)

    # ---------------------------------------------------------------- detail
    def _tectora_site_values(self, worker, project, tab, **kw):
        now = fields.Datetime.now()
        values = self._prepare_portal_layout_values()
        Timer = request.env["tectora.roof.timer"].sudo()
        policy = project._tectora_portal_hours_policy(worker)
        running = Timer._running_for(project, "team")
        my_running = Timer._running_for(project, "individual", worker)
        today_people = project._tectora_portal_planned_partners(now)
        stop_people = request.env["res.partner"].sudo()
        if running:
            stop_people = (
                running.partner_ids
                | project._tectora_portal_planned_partners(running.start_datetime)
                | worker
            ).filtered("active")
        # My hours on the site: my timesheet lines when I am an worker
        # (the back office may have corrected them), else my registrations.
        dossier = project.project_id
        my_employees = worker._tectora_employees()
        if my_employees and dossier:
            my_hours = sum(request.env["account.analytic.line"].sudo().search([
                ("project_id", "=", dossier.id), ("employee_id", "in", my_employees.ids),
            ]).mapped("unit_amount"))
        else:
            my_hours = sum(
                round(timer.duration_hours, 2)
                for timer in project.timer_ids
                if timer.state == "done" and worker in timer.partner_ids
            )
        drawing_png = (
            project._get_drawing_png()
            if project.canvas_snapshot or project.canvas_data else False
        )
        history = request.session.get("tectora_sites_history", [])
        prev_record = next_record = False
        if project.id in history:
            index = history.index(project.id)
            if index > 0:
                prev_record = "/my/werven/%d" % history[index - 1]
            if index < len(history) - 1:
                next_record = "/my/werven/%d" % history[index + 1]
        values.update({
            "page_name": "tectora_site",
            "site": project,
            "worker": worker,
            "tab": self._tectora_tab(worker, tab),
            "segments": worker._tectora_portal_segments(),
            "now": now,
            "today": fields.Date.context_today(request.env.user),
            "blocks": project._tectora_portal_visible_blocks(worker, now),
            "next_block": project._tectora_portal_next_block(now, worker),
            "planned_people": project._tectora_portal_crew(),
            "today_people": today_people,
            "running_timer": running,
            "my_running_timer": my_running,
            "can_stop_team": bool(running) and self._tectora_can_stop(running, worker, policy),
            "hours_policy": policy,
            "manual_people": self._tectora_manual_people(project, worker, now),
            "stop_people": stop_people,
            "timers": project.timer_ids.filtered(lambda timer: timer.state != "cancelled"),
            "reports": project.execution_report_ids,
            "materials": project.material_line_ids,
            "sections": project.section_ids,
            "roof_objects": project.roof_object_ids,
            "drawing_src": image_data_uri(drawing_png) if drawing_png else False,
            "info_sheet": project._info_sheet_sections(),
            "my_hours": my_hours,
            "my_hours_display": "%d:%02d" % (int(my_hours), int(round((my_hours - int(my_hours)) * 60))),
            "maps_url": "https://www.google.com/maps/search/?api=1&query=%s" % quote_plus(project.address)
            if project.address else False,
            "message": kw.get("message"),
            "error": kw.get("error"),
            "prev_record": prev_record,
            "next_record": next_record,
            "pdf_reports": PDF_REPORTS,
        })
        return values

    @http.route(["/my/werven/<int:project_id>"], type="http", auth="user", website=True)
    def portal_site(self, project_id, tab="overview", **kw):
        worker = self._tectora_worker()
        if not worker:
            return self._tectora_no_worker()
        project = self._tectora_site_for(worker, project_id)
        values = self._tectora_site_values(worker, project, tab, **kw)
        return request.render("tectora_portal.portal_site_page", values)

    # ----------------------------------------------------------------- timer
    def _tectora_can_stop(self, timer, worker, policy):
        """Who may stop a running registration: its own worker (individual),
        or whoever logs for the crew and whoever started it (team)."""
        if timer.scope == "individual":
            return worker in timer.partner_ids
        return bool(policy["team"] or timer.started_by_partner_id == worker)

    def _tectora_manual_people(self, project, worker, moment):
        """The people a ploegleider can enter hours for: the crew planned on
        the site, their ploeg and themselves."""
        team = project._tectora_portal_hours_team(worker)
        return (
            project._tectora_portal_planned_partners(moment)
            | project._tectora_portal_crew()
            | team.member_partner_ids
            | worker
        ).filtered("active")

    def _tectora_form_people(self, allowed):
        chosen = []
        for raw in request.httprequest.form.getlist("partner_ids"):
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value in allowed.ids and value not in chosen:
                chosen.append(value)
        return chosen

    @http.route(
        ["/my/werven/<int:project_id>/uren/start"],
        type="http", auth="user", methods=["POST"], website=True,
    )
    def portal_site_timer_start(self, project_id, **post):
        worker = self._tectora_worker()
        if not worker:
            return self._tectora_no_worker()
        project = self._tectora_site_for(worker, project_id)
        tab = post.get("tab") or "report"
        refused = self._tectora_segment_refused(worker, project, "hours", tab)
        if refused:
            return refused
        policy = project._tectora_portal_hours_policy(worker)
        scope = post.get("scope") or ("team" if policy["team"] else "individual")
        if scope not in ("team", "individual") or not policy["timer"] or not policy[scope]:
            return request.redirect(self._tectora_site_url(
                project, tab, error=_("Je ploeg logt de uren niet op deze manier.")
            ))
        try:
            request.env["tectora.roof.timer"].sudo()._start(
                project,
                worker,
                notes=(post.get("notes") or "").strip() or None,
                work_kind=post.get("work_kind"),
                scope=scope,
            )
        except (UserError, ValidationError) as error:
            return request.redirect(self._tectora_site_url(project, tab, error=str(error)))
        return request.redirect(
            self._tectora_site_url(project, tab, message=_("Urenregistratie gestart."))
        )

    @http.route(
        ["/my/werven/<int:project_id>/uren/<int:timer_id>/stop"],
        type="http", auth="user", methods=["POST"], website=True,
    )
    def portal_site_timer_stop(self, project_id, timer_id, **post):
        worker = self._tectora_worker()
        if not worker:
            return self._tectora_no_worker()
        project = self._tectora_site_for(worker, project_id)
        tab = post.get("tab") or "report"
        timer = project.timer_ids.filtered(
            lambda timer: timer.id == timer_id and timer.state == "running"
        )
        if not timer:
            return request.redirect(self._tectora_site_url(
                project, tab, error=_("Deze urenregistratie loopt niet (meer).")
            ))
        refused = self._tectora_segment_refused(worker, project, "hours", tab)
        if refused:
            return refused
        policy = project._tectora_portal_hours_policy(worker)
        if not self._tectora_can_stop(timer, worker, policy):
            return request.redirect(self._tectora_site_url(
                project, tab, error=_("Enkel de ploegleider kan deze urenregistratie stoppen.")
            ))
        if timer.scope == "individual":
            chosen = [worker.id]
        else:
            # Only people who can have been on the site: the planned crew,
            # the crew stored at start and the one stopping it.
            chosen = self._tectora_form_people(
                timer.partner_ids
                | project._tectora_portal_planned_partners(timer.start_datetime)
                | project._tectora_portal_crew()
                | worker
            )
        if not chosen:
            return request.redirect(self._tectora_site_url(
                project, tab, error=_("Kies minstens één persoon voor wie de uren geboekt worden.")
            ))
        try:
            timer.action_stop(
                partner_ids=chosen, stopped_by=worker,
                notes=(post.get("notes") or "").strip() or None,
            )
        except (UserError, ValidationError) as error:
            return request.redirect(self._tectora_site_url(project, tab, error=str(error)))
        except Exception:  # the hours must never be lost silently
            _logger.exception("Could not book the hours of timer %s", timer.id)
            return request.redirect(self._tectora_site_url(
                project, tab,
                error=_("De registratie is gestopt maar de uren konden niet geboekt worden; "
                        "verwittig de planning."),
            ))
        return request.redirect(self._tectora_site_url(
            project, tab,
            message=_("Gestopt: %(hours)s uur geboekt voor %(count)s perso(o)n(en).",
                      hours=timer._elapsed_display(), count=len(chosen)),
        ))

    @http.route(
        ["/my/werven/<int:project_id>/uren/ingeven"],
        type="http", auth="user", methods=["POST"], website=True,
    )
    def portal_site_hours_manual(self, project_id, **post):
        """Hours entered directly: for oneself, or by the ploegleider for the
        crew -- as the ploeg's settings allow."""
        worker = self._tectora_worker()
        if not worker:
            return self._tectora_no_worker()
        project = self._tectora_site_for(worker, project_id)
        tab = post.get("tab") or "report"
        refused = self._tectora_segment_refused(worker, project, "hours", tab)
        if refused:
            return refused
        policy = project._tectora_portal_hours_policy(worker)
        scope = post.get("scope") or ("team" if policy["team"] else "individual")
        if scope not in ("team", "individual") or not policy["manual"] or not policy[scope]:
            return request.redirect(self._tectora_site_url(
                project, tab, error=_("Je ploeg geeft de uren niet rechtstreeks in.")
            ))
        people = request.env["res.partner"].sudo()
        if scope == "team":
            allowed = self._tectora_manual_people(project, worker, fields.Datetime.now())
            people = people.browse(self._tectora_form_people(allowed))
            if not people:
                return request.redirect(self._tectora_site_url(
                    project, tab,
                    error=_("Kies minstens één persoon voor wie de uren geboekt worden."),
                ))
        hours = (post.get("hours") or "").strip().replace(",", ".")
        if ":" in hours:
            whole, _sep, minutes = hours.partition(":")
            try:
                hours = int(whole or 0) + int(minutes or 0) / 60.0
            except ValueError:
                hours = None
        try:
            timer = request.env["tectora.roof.timer"].sudo()._log_manual(
                project, worker, post.get("date"), hours,
                partners=people, work_kind=post.get("work_kind"),
                notes=(post.get("notes") or "").strip() or None, scope=scope,
            )
        except (UserError, ValidationError, ValueError) as error:
            return request.redirect(self._tectora_site_url(project, tab, error=str(error)))
        return request.redirect(self._tectora_site_url(
            project, tab,
            message=_("%(hours)s uur geboekt voor %(count)s perso(o)n(en).",
                      hours=timer._elapsed_display(), count=len(timer.partner_ids)),
        ))

    # ---------------------------------------------------------------- report
    @http.route(
        ["/my/werven/<int:project_id>/verslag"],
        type="http", auth="user", methods=["POST"], website=True,
    )
    def portal_site_report_submit(self, project_id, **post):
        worker = self._tectora_worker()
        if not worker:
            return self._tectora_no_worker()
        project = self._tectora_site_for(worker, project_id)
        refused = self._tectora_segment_refused(worker, project, "report", "report")
        if refused:
            return refused
        work_done = (post.get("work_done") or "").strip()
        if not work_done:
            return request.redirect(self._tectora_site_url(
                project, "report", error=_("Beschrijf de uitgevoerde werken.")
            ))
        Report = request.env["tectora.roof.execution.report"].sudo()
        progress = post.get("progress")
        if progress not in dict(Report._fields["progress"].selection):
            progress = "in_progress"
        report_date = fields.Date.context_today(request.env.user)
        if post.get("date"):
            try:
                report_date = date_type.fromisoformat(post["date"])
            except ValueError:
                pass
        block = project._tectora_portal_block_at(fields.Datetime.now())
        report = Report.create({
            "project_id": project.id,
            "planning_id": block.id if block else False,
            "date": report_date,
            "author_id": worker.id,
            "user_id": request.env.user.id,
            "progress": progress,
            "work_done": work_done,
            "materials_used": (post.get("materials_used") or "").strip() or False,
            "remarks": (post.get("remarks") or "").strip() or False,
        })
        attachments = self._tectora_store_photos(report)
        if attachments:
            report.write({"image_ids": [(6, 0, attachments.ids)]})
        return request.redirect(self._tectora_site_url(
            project, "report", message=_("Uitvoeringsverslag toegevoegd.")
        ))

    def _tectora_store_photos(self, report):
        Attachment = request.env["ir.attachment"].sudo()
        attachments = Attachment
        files = request.httprequest.files.getlist("photos")[:MAX_PHOTOS]
        for upload in files:
            if not upload or not upload.filename:
                continue
            data = upload.read()
            if not data or len(data) > MAX_PHOTO_BYTES:
                continue
            mimetype = upload.mimetype or ""
            if not mimetype.startswith("image/"):
                continue
            attachments |= Attachment.create({
                "name": upload.filename,
                "raw": data,
                "mimetype": mimetype,
                "res_model": report._name,
                "res_id": report.id,
            })
        return attachments

    @http.route(
        ["/my/werven/<int:project_id>/foto/<int:attachment_id>"],
        type="http", auth="user", website=True,
    )
    def portal_site_photo(self, project_id, attachment_id, width=0, height=0, **kw):
        worker = self._tectora_worker()
        if not worker:
            raise NotFound()
        project = self._tectora_site_for(worker, project_id)
        attachment = project.execution_report_ids.image_ids.filtered(
            lambda attachment: attachment.id == attachment_id
        )
        if not attachment:
            raise NotFound()
        stream = request.env["ir.binary"]._get_image_stream_from(
            attachment.sudo(), "raw", width=int(width or 0), height=int(height or 0),
        )
        return stream.get_response()

    # ------------------------------------------------------------------- pdf
    @http.route(
        ["/my/werven/<int:project_id>/pdf/<string:kind>"],
        type="http", auth="user", website=True,
    )
    def portal_site_pdf(self, project_id, kind, **kw):
        worker = self._tectora_worker()
        if not worker:
            return self._tectora_no_worker()
        project = self._tectora_site_for(worker, project_id)
        if kind not in PDF_REPORTS:
            raise NotFound()
        report_ref, label = PDF_REPORTS[kind]
        try:
            pdf, _content_type = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
                report_ref, [project.id]
            )
        except Exception:
            _logger.exception("Could not render %s for roof project %s", kind, project.id)
            return request.redirect(self._tectora_site_url(
                project, "overview", error=_("Het %s kon niet aangemaakt worden.", label.lower())
            ))
        filename = "%s %s.pdf" % (label, project.code or project.name or project.id)
        return request.make_response(pdf, headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Length", str(len(pdf))),
            ("Content-Disposition", content_disposition(filename)),
        ])
