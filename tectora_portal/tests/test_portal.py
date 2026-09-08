# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


class TectoraPortalCase(TransactionCase):
    """A site with a team of two, planned today, and a portal login for the
    ploegbaas."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, tz="Europe/Brussels"))
        cls.company = cls.env.company
        cls.leader = cls.env["hr.employee"].create({
            "name": "Piet Ploegbaas", "work_email": "piet.ploegbaas@example.com",
            "company_id": cls.company.id,
        })
        cls.mate = cls.env["hr.employee"].create({
            "name": "Mia Maat", "work_email": "mia.maat@example.com",
            "company_id": cls.company.id,
        })
        cls.outsider = cls.env["hr.employee"].create({
            "name": "Otto Outsider", "work_email": "otto@example.com",
            "company_id": cls.company.id,
        })
        cls.team = cls.env["tectora.roof.team"].create({
            "name": "Ploeg A", "leader_id": cls.leader.id,
        })
        cls.mate.roof_team_id = cls.team
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
            "employee_ids": [(6, 0, (cls.leader | cls.mate).ids)],
            "start_datetime": now - timedelta(hours=1),
            "end_datetime": now + timedelta(hours=7),
            "state": "published",
            "notes": "Ladder meenemen",
        })
        cls.leader.action_tectora_grant_portal_access()
        cls.portal_user = cls.leader.user_id
        cls.portal_user.write({"password": "portal-test-123"})


@tagged("post_install", "-at_install")
class TestPortalAccess(TectoraPortalCase):

    def test_grant_portal_access(self):
        self.assertTrue(self.portal_user)
        self.assertTrue(self.portal_user.share, "the employee gets an external (portal) user")
        self.assertEqual(self.portal_user.login, "piet.ploegbaas@example.com")
        self.assertEqual(self.portal_user.partner_id, self.leader.work_contact_id)
        self.assertEqual(self.leader.tectora_portal_state, "portal")
        self.assertTrue(self.leader.tectora_portal_access)
        with self.assertRaises(Exception):
            self.leader.action_tectora_grant_portal_access()

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
        self.assertFalse(Project.search(Project._tectora_portal_domain(self.env["hr.employee"])))

    def test_planned_employees(self):
        now = fields.Datetime.now()
        self.assertEqual(
            self.project._tectora_portal_planned_employees(now), self.leader | self.mate
        )
        self.assertEqual(self.project._tectora_portal_block_at(now), self.block)
        # without a block that day: the closest block's crew
        far = now + timedelta(days=10)
        self.assertEqual(self.project._tectora_portal_planned_employees(far), self.leader | self.mate)
        # without any block: the team
        self.other_project.team_id = self.team
        self.assertEqual(
            self.other_project._tectora_portal_planned_employees(now), self.team.member_ids
        )


@tagged("post_install", "-at_install")
class TestTimer(TectoraPortalCase):

    def test_start_stop_books_timesheets(self):
        Timer = self.env["tectora.roof.timer"]
        timer = Timer._start(self.project, self.leader)
        self.assertEqual(timer.state, "running")
        self.assertEqual(timer.planning_id, self.block)
        self.assertEqual(timer.employee_ids, self.leader | self.mate)
        self.assertEqual(self.project.running_timer_id, timer)
        with self.assertRaises(Exception, msg="one running timer per site"):
            Timer._start(self.project, self.mate)

        timer.start_datetime = fields.Datetime.now() - timedelta(hours=2, minutes=30)
        timer.action_stop(stopped_by=self.mate, notes="Regen")
        self.assertEqual(timer.state, "done")
        self.assertEqual(timer.stopped_by_id, self.mate)
        self.assertAlmostEqual(timer.duration_hours, 2.5, places=1)

        lines = timer.timesheet_ids
        self.assertEqual(len(lines), 2, "one timesheet line per present employee")
        self.assertEqual(lines.employee_id, self.leader | self.mate)
        dossier = self.project.project_id
        self.assertTrue(dossier, "the plannable project is created to book the hours on")
        self.assertTrue(dossier.allow_timesheets)
        self.assertEqual(lines.project_id, dossier)
        for line in lines:
            self.assertAlmostEqual(line.unit_amount, 2.5, places=1)
            self.assertIn("Regen", line.name)
        self.assertAlmostEqual(self.project.portal_hours, 5.0, places=1)
        self.assertFalse(self.project.running_timer_id)
        with self.assertRaises(Exception):
            timer.action_stop()

    def test_stop_with_confirmed_crew(self):
        timer = self.env["tectora.roof.timer"]._start(self.project, self.leader)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=1)
        timer.action_stop(employee_ids=[self.leader.id], stopped_by=self.leader)
        self.assertEqual(timer.employee_ids, self.leader)
        self.assertEqual(len(timer.timesheet_ids), 1)
        self.assertEqual(timer.timesheet_ids.employee_id, self.leader)

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
        self.assertEqual(timer.employee_ids, self.outsider)

    def test_forgotten_timer_is_stopped(self):
        timer = self.env["tectora.roof.timer"]._start(self.project, self.leader)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=20)
        self.env["tectora.roof.timer"]._cron_stop_forgotten_timers()
        self.assertEqual(timer.state, "done")
        self.assertAlmostEqual(timer.duration_hours, 16.0, places=1)
        self.assertIn("Automatisch gestopt", timer.notes)
        self.assertEqual(len(timer.timesheet_ids), 2)


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
        self.assertEqual(timer.started_by_id, self.leader)
        self.assertIn("Stop", response.text)

        timer.start_datetime = fields.Datetime.now() - timedelta(hours=3)
        response = self.url_open(
            "%s/uren/%d/stop" % (url, timer.id),
            data={"csrf_token": csrf, "tab": "report",
                  "employee_ids": [str(self.leader.id), str(self.mate.id), "999999"],
                  "notes": "Klaar"},
        )
        self.assertEqual(response.status_code, 200)
        timer.invalidate_recordset()
        self.assertEqual(timer.state, "done")
        self.assertEqual(len(timer.timesheet_ids), 2)
        self.assertEqual(timer.employee_ids, self.leader | self.mate)

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
        self.assertEqual(report.employee_id, self.leader)
        self.assertEqual(len(report.image_ids), 1)
        self.assertIn("Dampscherm gelegd", response.text)

        photo = self.url_open("%s/foto/%d" % (url, report.image_ids.id))
        self.assertEqual(photo.status_code, 200)
        self.assertTrue(photo.headers.get("Content-Type", "").startswith("image/"))

        pdf = self.url_open(url + "/pdf/meetblad")
        self.assertEqual(pdf.status_code, 200)

    def test_no_employee(self):
        user = self.env["res.users"].create({
            "name": "Los Portaal", "login": "los@example.com", "password": "portal-test-123",
            "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
        })
        self.authenticate(user.login, "portal-test-123")
        response = self.url_open("/my/werven")
        self.assertEqual(response.status_code, 200)
        self.assertIn("geen medewerkersfiche", response.text)
        response = self.url_open("/my/werven/%d" % self.project.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn("geen medewerkersfiche", response.text)


# a 1x1 PNG
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)
