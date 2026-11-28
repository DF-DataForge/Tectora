# -*- coding: utf-8 -*-
import base64
import re
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


class TectoraPortalCase(TransactionCase):
    """A site with a ploeg, planned today, and a portal login for the
    ploegbaas. Everything runs on contacts: ``leader`` / ``mate`` /
    ``outsider`` are the contacts (the first two of employees, so they get
    timesheet lines), ``helper`` is a contact without an employee."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, tz="Europe/Brussels"))
        cls.company = cls.env.company
        cls.leader_employee = cls.env["hr.employee"].create({
            "name": "Piet Ploegbaas", "work_email": "piet.ploegbaas.test@example.com",
            "company_id": cls.company.id,
        })
        cls.mate_employee = cls.env["hr.employee"].create({
            "name": "Mia Maat", "work_email": "mia.maat.test@example.com",
            "company_id": cls.company.id,
        })
        cls.outsider_employee = cls.env["hr.employee"].create({
            "name": "Otto Outsider", "work_email": "otto.test@example.com",
            "company_id": cls.company.id,
        })
        cls.leader = cls.leader_employee.work_contact_id
        cls.mate = cls.mate_employee.work_contact_id
        cls.outsider = cls.outsider_employee.work_contact_id
        cls.helper = cls.env["res.partner"].create({
            "name": "Karel Contact", "email": "karel.contact.test@example.com",
        })
        cls.team = cls.env["tectora.roof.team"].create({
            "name": "Ploeg A", "leader_partner_id": cls.leader.id,
            "partner_ids": [(6, 0, cls.mate.ids)],
        })
        cls.customer = cls.env["res.partner"].create({
            "name": "Klant Dakwerk", "street": "Kerkstraat 1", "city": "Wortegem",
        })
        cls.project = cls.env["tectora.roof.project"].create({
            "name": "Plat dak garage", "partner_id": cls.customer.id,
            "address": "Kerkstraat 1, 9790 Wortegem",
        })
        cls.other_project = cls.env["tectora.roof.project"].create({
            "name": "Ander dak", "partner_id": cls.customer.id,
        })
        now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        cls.block = cls.env["tectora.roof.planning"].create({
            "project_id": cls.project.id,
            "team_id": cls.team.id,
            "partner_ids": [(6, 0, (cls.leader | cls.mate).ids)],
            "start_datetime": now - timedelta(hours=1),
            "end_datetime": now + timedelta(hours=7),
            "state": "published",
            "notes": "Ladder meenemen",
        })
        cls.leader_employee.action_tectora_grant_portal_access()
        cls.portal_user = cls.leader.user_ids
        cls.portal_user.write({"password": "portal-test-123"})


@tagged("post_install", "-at_install")
class TestPortalAccess(TectoraPortalCase):

    def test_grant_portal_access(self):
        self.assertTrue(self.portal_user)
        self.assertTrue(self.portal_user.share, "the employee gets an external (portal) user")
        self.assertEqual(self.portal_user.login, "piet.ploegbaas.test@example.com")
        self.assertEqual(self.portal_user.partner_id, self.leader)
        self.assertEqual(self.leader.tectora_portal_state, "portal")
        self.assertTrue(self.leader.tectora_portal_access)
        self.assertEqual(self.leader_employee.tectora_portal_state, "portal")
        self.assertFalse(self.leader_employee.user_id, "the login hangs on the contact, not the employee")
        with self.assertRaises(Exception):
            self.leader.action_tectora_grant_portal_access()

    def test_grant_portal_access_to_contact(self):
        """A contact without an employee gets its login just the same."""
        self.assertFalse(self.helper._tectora_is_worker(), "not in a ploeg, not planned")
        self.team.partner_ids = [(4, self.helper.id)]
        self.assertTrue(self.helper._tectora_is_worker())
        self.assertEqual(self.helper.tectora_portal_state, "none")
        self.helper.action_tectora_grant_portal_access()
        user = self.helper.user_ids
        self.assertTrue(user.share)
        self.assertEqual(user.login, "karel.contact.test@example.com")
        self.assertEqual(self.helper.tectora_portal_state, "portal")
        self.assertFalse(self.helper._tectora_employees())

    def test_ploeg_and_block_of_contacts(self):
        self.team.partner_ids = [(4, self.helper.id)]
        self.assertEqual(self.team.member_partner_ids, self.leader | self.mate | self.helper)
        self.assertEqual(self.team.member_ids, self.leader_employee | self.mate_employee)
        self.assertEqual(self.team.leader_id, self.leader_employee)
        self.assertEqual(self.block.employee_ids, self.leader_employee | self.mate_employee)
        # a block put on the ploeg takes its contacts along
        self.block.write({"team_id": self.team.id})
        self.assertEqual(self.block.partner_ids, self.leader | self.mate | self.helper)
        self.assertEqual(self.block.employee_ids, self.leader_employee | self.mate_employee)
        self.assertIn("3 pers.", self.block.display_name)
        # employees set on a block (older code): their contacts, the others stay
        self.block.employee_ids = self.outsider_employee
        self.assertEqual(self.block.partner_ids, self.helper | self.outsider)
        # an employee put on a ploeg brings their contact along
        self.outsider_employee.roof_team_id = self.team
        self.assertIn(self.outsider, self.team.partner_ids)
        self.outsider_employee.roof_team_id = False
        self.assertNotIn(self.outsider, self.team.partner_ids)

    def test_grant_needs_email(self):
        nobody = self.env["hr.employee"].create({"name": "Geen Mail"})
        with self.assertRaises(Exception):
            nobody.action_tectora_grant_portal_access()

    def test_portal_domain(self):
        Project = self.env["tectora.roof.project"]
        seen = Project.search(Project._tectora_portal_domain(self.leader))
        self.assertIn(self.project, seen)
        self.assertNotIn(self.other_project, seen)
        # the team member sees the site through the block and the team
        self.assertIn(self.project, Project.search(Project._tectora_portal_domain(self.mate)))
        # a team-assigned project without a block is visible to its team
        self.other_project.team_id = self.team
        self.assertIn(self.other_project, Project.search(Project._tectora_portal_domain(self.mate)))
        self.assertIn(self.other_project, Project.search(Project._tectora_portal_domain(self.leader)))
        self.assertFalse(Project.search(Project._tectora_portal_domain(self.outsider)))
        self.assertFalse(Project.search(Project._tectora_portal_domain(self.env["res.partner"])))
        # a contact without an employee: through the ploeg, or through a block
        self.assertFalse(Project.search(Project._tectora_portal_domain(self.helper)))
        self.block.partner_ids = [(4, self.helper.id)]
        self.assertEqual(Project.search(Project._tectora_portal_domain(self.helper)), self.project)
        self.team.partner_ids = [(4, self.helper.id)]
        self.assertIn(self.other_project, Project.search(Project._tectora_portal_domain(self.helper)))

    def test_planning_horizon(self):
        """A work block beyond the employee's horizon stays hidden: the site
        it is on does not show, nor does the block, until it comes within a
        week or a month."""
        Project = self.env["tectora.roof.project"]
        now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        later = self.env["tectora.roof.planning"].create({
            "project_id": self.other_project.id,
            "partner_ids": [(6, 0, self.outsider.ids)],
            "start_datetime": now + timedelta(days=20),
            "end_datetime": now + timedelta(days=20, hours=8),
            "state": "published",
        })
        self.assertEqual(self.outsider.tectora_portal_planning_horizon, "all")
        self.assertIn(self.other_project, Project.search(Project._tectora_portal_domain(self.outsider)))
        self.assertEqual(self.other_project._tectora_portal_visible_blocks(self.outsider), later)

        self.outsider.tectora_portal_planning_horizon = "week"
        self.assertNotIn(self.other_project, Project.search(Project._tectora_portal_domain(self.outsider)))
        self.assertFalse(self.other_project._tectora_portal_visible_blocks(self.outsider))
        self.assertFalse(self.other_project._tectora_portal_next_block(now, self.outsider))

        self.outsider.tectora_portal_planning_horizon = "month"
        self.assertIn(self.other_project, Project.search(Project._tectora_portal_domain(self.outsider)))
        self.assertEqual(self.other_project._tectora_portal_next_block(now, self.outsider), later)

        # Today's block stays visible on the shortest horizon.
        self.leader.tectora_portal_planning_horizon = "week"
        self.assertIn(self.project, Project.search(Project._tectora_portal_domain(self.leader)))
        self.assertEqual(self.project._tectora_portal_visible_blocks(self.leader), self.block)

    def test_planned_people(self):
        now = fields.Datetime.now()
        self.assertEqual(
            self.project._tectora_portal_planned_partners(now), self.leader | self.mate
        )
        self.assertEqual(self.project._tectora_portal_block_at(now), self.block)
        # without a block that day: the closest block's crew
        far = now + timedelta(days=10)
        self.assertEqual(self.project._tectora_portal_planned_partners(far), self.leader | self.mate)
        # without any block: the team
        self.other_project.team_id = self.team
        self.assertEqual(
            self.other_project._tectora_portal_planned_partners(now), self.team.member_partner_ids
        )


@tagged("post_install", "-at_install")
class TestTimer(TectoraPortalCase):

    def test_start_stop_books_timesheets(self):
        Timer = self.env["tectora.roof.timer"]
        timer = Timer._start(self.project, self.leader)
        self.assertEqual(timer.state, "running")
        self.assertEqual(timer.planning_id, self.block)
        self.assertTrue(self.block.portal_running, "the planner shows the running timer")
        self.assertEqual(timer.partner_ids, self.leader | self.mate)
        self.assertEqual(self.project.running_timer_id, timer)
        with self.assertRaises(Exception, msg="one running timer per site"):
            Timer._start(self.project, self.mate)

        timer.start_datetime = fields.Datetime.now() - timedelta(hours=2, minutes=30)
        timer.action_stop(stopped_by=self.mate, notes="Regen")
        self.assertEqual(timer.state, "done")
        self.assertEqual(timer.stopped_by_partner_id, self.mate)
        self.assertAlmostEqual(timer.duration_hours, 2.5, places=1)

        lines = timer.timesheet_ids
        self.assertEqual(len(lines), 2, "one timesheet line per present employee")
        self.assertEqual(lines.employee_id, self.leader_employee | self.mate_employee)
        dossier = self.project.project_id
        self.assertTrue(dossier, "the plannable project is created to book the hours on")
        self.assertTrue(dossier.allow_timesheets)
        self.assertEqual(lines.project_id, dossier)
        # Without a choice the hours are execution hours, on that task.
        self.assertEqual(timer.work_kind, "uitvoering")
        self.assertEqual(lines.task_id.tectora_work_kind, "uitvoering")
        self.assertEqual(lines.task_id.project_id, dossier)
        for line in lines:
            self.assertAlmostEqual(line.unit_amount, 2.5, places=1)
            self.assertIn("Regen", line.name)
        self.assertAlmostEqual(self.project.portal_hours, 5.0, places=1)
        self.assertFalse(self.project.running_timer_id)
        with self.assertRaises(Exception):
            timer.action_stop()

    def test_stop_with_confirmed_crew(self):
        timer = self.env["tectora.roof.timer"]._start(
            self.project, self.leader, work_kind="afbraak"
        )
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=1)
        timer.action_stop(partner_ids=[self.leader.id], stopped_by=self.leader)
        self.assertEqual(timer.partner_ids, self.leader)
        self.assertEqual(len(timer.timesheet_ids), 1)
        # Demolition hours go on the task Afbraakwerken, kept apart from the
        # execution hours of the other registrations.
        task = timer.timesheet_ids.task_id
        self.assertEqual(task.tectora_work_kind, "afbraak")
        self.assertEqual(task.name, "Afbraakwerken")
        self.assertIn("Afbraakwerken", timer.timesheet_ids.name)
        other = self.env["tectora.roof.timer"]._start(self.project, self.leader)
        other.start_datetime = fields.Datetime.now() - timedelta(hours=1)
        other.action_stop(partner_ids=[self.leader.id])
        self.assertNotEqual(other.timesheet_ids.task_id, task)
        self.assertEqual(other.timesheet_ids.task_id.tectora_work_kind, "uitvoering")
        self.assertEqual(timer.timesheet_ids.employee_id, self.leader_employee)

    def test_contact_without_employee(self):
        """Registration runs on the contact: someone without an employee is
        planned, registered and counted; only a timesheet line needs an
        employee."""
        self.block.partner_ids = [(4, self.helper.id)]
        Timer = self.env["tectora.roof.timer"]
        timer = Timer._start(self.project, self.helper)
        self.assertEqual(timer.started_by_partner_id, self.helper)
        self.assertEqual(timer.partner_ids, self.leader | self.mate | self.helper)
        self.assertEqual(timer.employee_ids, self.leader_employee | self.mate_employee)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=2)
        timer.action_stop(stopped_by=self.helper)
        self.assertEqual(timer.timesheet_ids.employee_id, self.leader_employee | self.mate_employee)
        self.assertAlmostEqual(timer.contact_hours, 2.0, places=1)
        self.assertAlmostEqual(timer.registered_hours, 6.0, places=1)
        self.assertAlmostEqual(self.project.portal_hours, 6.0, places=1)
        self.assertAlmostEqual(self.block.portal_hours, 6.0, places=1)
        # entirely without employees: nothing to book, everything registered
        own = Timer._log_manual(self.project, self.helper, fields.Date.today(), 3, scope="individual")
        self.assertEqual(own.partner_ids, self.helper)
        self.assertFalse(own.timesheet_ids)
        self.assertAlmostEqual(own.registered_hours, 3.0, places=2)
        # with an hourly cost on the contact the hours are booked on the project
        self.assertFalse(timer.contact_line_ids, "no hourly cost: nothing to book")
        self.helper.tectora_hourly_cost = 40.0
        paid = Timer._log_manual(self.project, self.helper, fields.Date.today(), 5, scope="individual")
        self.assertFalse(paid.timesheet_ids)
        line = paid.contact_line_ids
        self.assertEqual(len(line), 1)
        dossier = self.project.project_id
        self.assertEqual(line.account_id, dossier.account_id)
        self.assertEqual(line.partner_id, self.helper)
        self.assertAlmostEqual(line.unit_amount, 5.0, places=2)
        self.assertAlmostEqual(line.amount, -200.0, places=2)
        self.assertAlmostEqual(paid.contact_cost, 200.0, places=2)
        self.assertAlmostEqual(paid.registered_hours, 5.0, places=2)
        dossier.invalidate_recordset()
        sheet_hours = sum(dossier.timesheet_ids.mapped("unit_amount"))
        sheet_cost = -sum(dossier.timesheet_ids.mapped("amount"))
        self.assertAlmostEqual(dossier.tectora_timesheet_hours, sheet_hours + 2.0 + 3.0 + 5.0, places=1)
        self.assertAlmostEqual(dossier.tectora_timesheet_cost, sheet_cost + 200.0, places=2)
        # in a crew registration: timesheets for the employees, a cost line for the contact
        crew = Timer._log_manual(
            self.project, self.leader, fields.Date.today(), 2,
            partners=self.leader | self.helper,
        )
        self.assertEqual(crew.timesheet_ids.employee_id, self.leader_employee)
        self.assertEqual(crew.contact_line_ids.partner_id, self.helper)
        self.assertAlmostEqual(crew.contact_cost, 80.0, places=2)
        crew.action_cancel()
        self.assertFalse(crew.contact_line_ids or crew.timesheet_ids)
        # a ploeg led by a contact without an employee
        self.team.leader_partner_id = self.helper
        self.assertFalse(self.team.leader_id)
        self.assertTrue(self.project._tectora_portal_hours_policy(self.helper)["team"])
        self.assertFalse(self.project._tectora_portal_hours_policy(self.leader)["team"])

    def test_cancel_removes_timesheets(self):
        timer = self.env["tectora.roof.timer"]._start(self.project, self.leader)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=1)
        timer.action_stop()
        lines = timer.timesheet_ids
        self.assertTrue(lines)
        timer.action_cancel()
        self.assertEqual(timer.state, "cancelled")
        self.assertFalse(lines.exists())

    def test_start_without_planning_books_starter(self):
        timer = self.env["tectora.roof.timer"]._start(self.other_project, self.outsider)
        self.assertEqual(timer.partner_ids, self.outsider)

    def test_forgotten_timer_is_stopped(self):
        timer = self.env["tectora.roof.timer"]._start(self.project, self.leader)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=20)
        self.env["tectora.roof.timer"]._cron_stop_forgotten_timers()
        self.assertEqual(timer.state, "done")
        self.assertAlmostEqual(timer.duration_hours, 16.0, places=1)
        self.assertIn("Automatisch gestopt", timer.notes)
        self.assertEqual(len(timer.timesheet_ids), 2)


@tagged("post_install", "-at_install")
class TestHoursLogging(TectoraPortalCase):
    """The ploeg decides who logs (ploegleider and/or individually) and how
    (start – stop and/or entering the hours); the options combine."""

    def test_default_policy(self):
        policy = self.project._tectora_portal_hours_policy(self.leader)
        self.assertTrue(policy["team"] and policy["timer"])
        self.assertFalse(policy["individual"] or policy["manual"])
        mate = self.project._tectora_portal_hours_policy(self.mate)
        self.assertFalse(mate["team"], "only the ploegleider logs for the crew")
        self.assertEqual(mate["leader"], self.leader)

    def test_at_least_one_option(self):
        with self.assertRaises(Exception):
            self.team.write({"hours_by_leader": False, "hours_individual": False})
        with self.assertRaises(Exception):
            self.team.write({"hours_timer": False, "hours_manual": False})

    def test_individual_timer(self):
        self.team.write({"hours_individual": True})
        policy = self.project._tectora_portal_hours_policy(self.mate)
        self.assertTrue(policy["individual"])
        Timer = self.env["tectora.roof.timer"]
        own = Timer._start(self.project, self.mate, scope="individual")
        self.assertEqual(own.partner_ids, self.mate)
        self.assertEqual(own.scope, "individual")
        with self.assertRaises(Exception, msg="one own timer per site"):
            Timer._start(self.project, self.mate, scope="individual")
        # the crew timer runs next to it
        team_timer = Timer._start(self.project, self.leader)
        self.assertEqual(team_timer.scope, "team")
        own.start_datetime = fields.Datetime.now() - timedelta(hours=2)
        own.action_stop(partner_ids=[self.mate.id], stopped_by=self.mate)
        self.assertEqual(own.timesheet_ids.employee_id, self.mate_employee)
        # counted in the running crew timer: no own timer on top of it
        with self.assertRaises(Exception):
            Timer._start(self.project, self.mate, scope="individual")

    def test_manual_entry(self):
        self.team.write({"hours_manual": True, "hours_individual": True})
        Timer = self.env["tectora.roof.timer"]
        timer = Timer._log_manual(
            self.project, self.leader, fields.Date.today(), 7.5,
            partners=self.leader | self.mate, work_kind="afbraak",
        )
        self.assertEqual(timer.state, "done")
        self.assertEqual(timer.entry_mode, "manual")
        self.assertAlmostEqual(timer.duration_hours, 7.5, places=2)
        self.assertEqual(timer.timesheet_ids.employee_id, self.leader_employee | self.mate_employee)
        self.assertEqual(timer.timesheet_ids.task_id.tectora_work_kind, "afbraak")
        own = Timer._log_manual(
            self.project, self.mate, fields.Date.today(), 4,
            partners=self.leader, scope="individual",
        )
        self.assertEqual(own.timesheet_ids.employee_id, self.mate_employee,
                         "individually only for oneself")
        with self.assertRaises(Exception):
            Timer._log_manual(self.project, self.mate, fields.Date.today(), 0)
        with self.assertRaises(Exception):
            Timer._log_manual(self.project, self.mate,
                              fields.Date.today() + timedelta(days=2), 3)

    def test_segments(self):
        self.leader.tectora_portal_show_materials = False
        segments = self.leader._tectora_portal_segments()
        self.assertFalse(segments["materials"])
        self.assertTrue(segments["overview"] and segments["hours"])


@tagged("post_install", "-at_install")
class TestPortalRoutes(HttpCase, TectoraPortalCase):

    def _csrf(self, html):
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        self.assertTrue(match, "the page carries a csrf token")
        return match.group(1)

    def test_portal_pages(self):
        self.authenticate(self.portal_user.login, "portal-test-123")
        response = self.url_open("/my/werven")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Plat dak garage", response.text)
        self.assertNotIn("Ander dak", response.text)

        url = "/my/werven/%d" % self.project.id
        for tab in ("overview", "materials", "plan", "report"):
            response = self.url_open("%s?tab=%s" % (url, tab))
            self.assertEqual(response.status_code, 200, tab)

        # the roof plan shows the stored drawing (a binary field holds raw
        # bytes since Odoo 20, no longer base64)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        self.project.sudo().canvas_snapshot = base64.b64encode(png).decode()
        response = self.url_open("%s?tab=plan" % url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("data:image/png;base64," + base64.b64encode(png).decode(), response.text)
        self.assertIn("Ladder meenemen", response.text)
        self.assertIn("Mia Maat", response.text)

        # a site the employee is not on is not found
        response = self.url_open("/my/werven/%d" % self.other_project.id)
        self.assertEqual(response.status_code, 404)

        # home shows the card
        response = self.url_open("/my/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/my/werven", response.text)

    def test_portal_timer_and_report(self):
        self.authenticate(self.portal_user.login, "portal-test-123")
        url = "/my/werven/%d" % self.project.id
        page = self.url_open(url + "?tab=report")
        csrf = self._csrf(page.text)

        response = self.url_open(url + "/uren/start", data={"csrf_token": csrf, "tab": "report"})
        self.assertEqual(response.status_code, 200)
        timer = self.project.running_timer_id
        self.assertTrue(timer, "Start opens the site's timer")
        self.assertEqual(timer.started_by_partner_id, self.leader)
        self.assertIn("Stop", response.text)

        timer.start_datetime = fields.Datetime.now() - timedelta(hours=3)
        response = self.url_open(
            "%s/uren/%d/stop" % (url, timer.id),
            data={"csrf_token": csrf, "tab": "report",
                  "partner_ids": [str(self.leader.id), str(self.mate.id), "999999"],
                  "notes": "Klaar"},
        )
        self.assertEqual(response.status_code, 200)
        timer.invalidate_recordset()
        self.assertEqual(timer.state, "done")
        self.assertEqual(len(timer.timesheet_ids), 2)
        self.assertEqual(timer.partner_ids, self.leader | self.mate)

        response = self.url_open(
            url + "/verslag",
            data={"csrf_token": csrf, "work_done": "Dampscherm gelegd", "progress": "finished",
                  "date": fields.Date.today().isoformat(), "remarks": "Geen"},
            files={"photos": ("foto.png", _PNG, "image/png")},
        )
        self.assertEqual(response.status_code, 200)
        report = self.project.execution_report_ids
        self.assertEqual(len(report), 1)
        self.assertEqual(report.work_done, "Dampscherm gelegd")
        self.assertEqual(report.progress, "finished")
        self.assertEqual(report.author_id, self.leader)
        self.assertEqual(report.employee_id, self.leader_employee)
        self.assertEqual(len(report.image_ids), 1)
        self.assertIn("Dampscherm gelegd", response.text)

        photo = self.url_open("%s/foto/%d" % (url, report.image_ids.id))
        self.assertEqual(photo.status_code, 200)
        self.assertTrue(photo.headers.get("Content-Type", "").startswith("image/"))

        pdf = self.url_open(url + "/pdf/meetblad")
        self.assertEqual(pdf.status_code, 200)

    def test_portal_manual_hours_and_segments(self):
        self.team.write({"hours_timer": False, "hours_manual": True})
        self.leader.tectora_portal_show_materials = False
        self.authenticate(self.portal_user.login, "portal-test-123")
        url = "/my/werven/%d" % self.project.id
        page = self.url_open(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Uren ingeven", page.text)
        self.assertNotIn("Start uitvoering", page.text, "no start – stop for this ploeg")
        self.assertNotIn('id="tab-materials"', page.text, "the hidden segment is not rendered")
        csrf = self._csrf(page.text)
        response = self.url_open(url + "/uren/ingeven", data={
            "csrf_token": csrf, "date": fields.Date.today().isoformat(), "hours": "7:30",
            "work_kind": "uitvoering", "scope": "team",
            "partner_ids": [str(self.leader.id), str(self.mate.id)],
        })
        self.assertEqual(response.status_code, 200)
        timer = self.project.timer_ids.filtered(lambda t: t.entry_mode == "manual")
        self.assertEqual(len(timer), 1)
        self.assertAlmostEqual(timer.duration_hours, 7.5, places=2)
        self.assertEqual(timer.timesheet_ids.employee_id, self.leader_employee | self.mate_employee)
        # start – stop is refused for this ploeg
        self.url_open(url + "/uren/start", data={"csrf_token": csrf, "work_kind": "uitvoering"})
        self.assertFalse(self.project.timer_ids.filtered(lambda t: t.state == "running"))

    def test_portal_contact_only(self):
        """The whole portal flow for a contact without an employee."""
        self.team.write({"partner_ids": [(4, self.helper.id)], "hours_individual": True})
        self.block.partner_ids = [(4, self.helper.id)]
        self.helper.action_tectora_grant_portal_access()
        user = self.helper.user_ids
        user.write({"password": "portal-test-123"})
        self.authenticate(user.login, "portal-test-123")
        response = self.url_open("/my/werven")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Plat dak garage", response.text)
        url = "/my/werven/%d" % self.project.id
        page = self.url_open(url + "?tab=report")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Karel Contact", page.text)
        csrf = self._csrf(page.text)
        self.url_open(url + "/uren/start", data={"csrf_token": csrf, "scope": "individual"})
        timer = self.project.timer_ids.filtered(lambda t: t.state == "running")
        self.assertEqual(timer.partner_ids, self.helper)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=4)
        response = self.url_open("%s/uren/%d/stop" % (url, timer.id), data={"csrf_token": csrf})
        self.assertEqual(response.status_code, 200)
        timer.invalidate_recordset()
        self.assertEqual(timer.state, "done")
        self.assertFalse(timer.timesheet_ids)
        self.assertAlmostEqual(timer.registered_hours, 4.0, places=1)
        self.assertIn("4:00", response.text)
        response = self.url_open(url + "/verslag", data={"csrf_token": csrf, "work_done": "Opgeruimd"})
        self.assertEqual(self.project.execution_report_ids.author_id, self.helper)

    def test_no_employee(self):
        user = self.env["res.users"].create({
            "name": "Los Portaal", "login": "los@example.com", "password": "portal-test-123",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        self.authenticate(user.login, "portal-test-123")
        response = self.url_open("/my/werven")
        self.assertEqual(response.status_code, 200)
        self.assertIn("niet ingepland", response.text)
        response = self.url_open("/my/werven/%d" % self.project.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn("niet ingepland", response.text)


# a 1x1 PNG
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
