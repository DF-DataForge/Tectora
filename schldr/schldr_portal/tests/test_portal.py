# -*- coding: utf-8 -*-
import json
import re
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged


class SchldrPortalCase(TransactionCase):
    """A site with a team of two, planned today, and a portal login for the
    ploegbaas."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, tz="Europe/Brussels"))
        cls.company = cls.env.company
        cls.leader = cls.env["hr.employee"].create({
            "name": "Piet Ploegbaas", "work_email": "piet.ploegbaas.test@example.com",
            "company_id": cls.company.id,
        })
        cls.mate = cls.env["hr.employee"].create({
            "name": "Mia Maat", "work_email": "mia.maat.test@example.com",
            "company_id": cls.company.id,
        })
        cls.outsider = cls.env["hr.employee"].create({
            "name": "Otto Outsider", "work_email": "otto.test@example.com",
            "company_id": cls.company.id,
        })
        cls.team = cls.env["schldr.team"].create({
            "name": "Ploeg A", "leader_id": cls.leader.id,
        })
        cls.mate.schldr_team_id = cls.team
        cls.customer = cls.env["res.partner"].create({
            "name": "Klant Schilderwerk", "street": "Kerkstraat 1", "city": "Wortegem",
        })
        cls.project = cls.env["schldr.project"].create({
            "name": "Woning Kerkstraat", "partner_id": cls.customer.id,
            "address": "Kerkstraat 1, 9790 Wortegem",
        })
        cls.other_project = cls.env["schldr.project"].create({
            "name": "Andere woning", "partner_id": cls.customer.id,
        })
        now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        cls.block = cls.env["schldr.planning"].create({
            "project_id": cls.project.id,
            "team_id": cls.team.id,
            "employee_ids": [(6, 0, (cls.leader | cls.mate).ids)],
            "start_datetime": now - timedelta(hours=1),
            "end_datetime": now + timedelta(hours=7),
            "state": "published",
            "notes": "Ladder meenemen",
        })
        cls.leader.action_schldr_grant_portal_access()
        cls.portal_user = cls.leader.user_id
        cls.portal_user.write({"password": "portal-test-123"})


@tagged("post_install", "-at_install")
class TestPortalAccess(SchldrPortalCase):

    def test_grant_portal_access(self):
        self.assertTrue(self.portal_user)
        self.assertTrue(self.portal_user.share, "the employee gets an external (portal) user")
        self.assertEqual(self.portal_user.login, "piet.ploegbaas.test@example.com")
        self.assertEqual(self.portal_user.partner_id, self.leader.work_contact_id)
        self.assertEqual(self.leader.schldr_portal_state, "portal")
        self.assertTrue(self.leader.schldr_portal_access)
        with self.assertRaises(Exception):
            self.leader.action_schldr_grant_portal_access()

    def test_grant_needs_email(self):
        nobody = self.env["hr.employee"].create({"name": "Geen Mail"})
        with self.assertRaises(Exception):
            nobody.action_schldr_grant_portal_access()

    def test_portal_domain(self):
        Project = self.env["schldr.project"]
        seen = Project.search(Project._schldr_portal_domain(self.leader))
        self.assertIn(self.project, seen)
        self.assertNotIn(self.other_project, seen)
        # the team member sees the site through the block and the team
        self.assertIn(self.project, Project.search(Project._schldr_portal_domain(self.mate)))
        # a team-assigned project without a block is visible to its team
        self.other_project.team_id = self.team
        self.assertIn(self.other_project, Project.search(Project._schldr_portal_domain(self.mate)))
        self.assertIn(self.other_project, Project.search(Project._schldr_portal_domain(self.leader)))
        self.assertFalse(Project.search(Project._schldr_portal_domain(self.outsider)))
        self.assertFalse(Project.search(Project._schldr_portal_domain(self.env["hr.employee"])))

    def test_planning_horizon(self):
        """A work block beyond the employee's horizon stays hidden: the site
        it is on does not show, nor does the block, until it comes within a
        week or a month."""
        Project = self.env["schldr.project"]
        now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
        later = self.env["schldr.planning"].create({
            "project_id": self.other_project.id,
            "employee_ids": [(6, 0, self.outsider.ids)],
            "start_datetime": now + timedelta(days=20),
            "end_datetime": now + timedelta(days=20, hours=8),
            "state": "published",
        })
        self.assertEqual(self.outsider.schldr_portal_planning_horizon, "all")
        self.assertIn(self.other_project, Project.search(Project._schldr_portal_domain(self.outsider)))
        self.assertEqual(self.other_project._schldr_portal_visible_blocks(self.outsider), later)

        self.outsider.schldr_portal_planning_horizon = "week"
        self.assertNotIn(self.other_project, Project.search(Project._schldr_portal_domain(self.outsider)))
        self.assertFalse(self.other_project._schldr_portal_visible_blocks(self.outsider))
        self.assertFalse(self.other_project._schldr_portal_next_block(now, self.outsider))

        self.outsider.schldr_portal_planning_horizon = "month"
        self.assertIn(self.other_project, Project.search(Project._schldr_portal_domain(self.outsider)))
        self.assertEqual(self.other_project._schldr_portal_next_block(now, self.outsider), later)

        # Today's block stays visible on the shortest horizon.
        self.leader.schldr_portal_planning_horizon = "week"
        self.assertIn(self.project, Project.search(Project._schldr_portal_domain(self.leader)))
        self.assertEqual(self.project._schldr_portal_visible_blocks(self.leader), self.block)

    def test_planned_employees(self):
        now = fields.Datetime.now()
        self.assertEqual(
            self.project._schldr_portal_planned_employees(now), self.leader | self.mate
        )
        self.assertEqual(self.project._schldr_portal_block_at(now), self.block)
        # without a block that day: the closest block's crew
        far = now + timedelta(days=10)
        self.assertEqual(self.project._schldr_portal_planned_employees(far), self.leader | self.mate)
        # without any block: the team
        self.other_project.team_id = self.team
        self.assertEqual(
            self.other_project._schldr_portal_planned_employees(now), self.team.member_ids
        )


@tagged("post_install", "-at_install")
class TestTimer(SchldrPortalCase):

    def test_start_stop_books_timesheets(self):
        Timer = self.env["schldr.timer"]
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
        # Without a choice the hours are execution hours, on that task.
        self.assertEqual(timer.work_kind, "uitvoering")
        self.assertEqual(lines.task_id.schldr_work_kind, "uitvoering")
        self.assertEqual(lines.task_id.project_id, dossier)
        for line in lines:
            self.assertAlmostEqual(line.unit_amount, 2.5, places=1)
            self.assertIn("Regen", line.name)
        self.assertAlmostEqual(self.project.portal_hours, 5.0, places=1)
        self.assertFalse(self.project.running_timer_id)
        with self.assertRaises(Exception):
            timer.action_stop()

    def test_stop_with_confirmed_crew(self):
        timer = self.env["schldr.timer"]._start(
            self.project, self.leader, work_kind="voorbereiding"
        )
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=1)
        timer.action_stop(employee_ids=[self.leader.id], stopped_by=self.leader)
        self.assertEqual(timer.employee_ids, self.leader)
        self.assertEqual(len(timer.timesheet_ids), 1)
        # Preparation hours go on the task Voorbereiding, kept apart from the
        # execution hours of the other registrations.
        task = timer.timesheet_ids.task_id
        self.assertEqual(task.schldr_work_kind, "voorbereiding")
        self.assertEqual(task.name, "Voorbereiding")
        self.assertIn("Voorbereiding", timer.timesheet_ids.name)
        other = self.env["schldr.timer"]._start(self.project, self.leader)
        other.start_datetime = fields.Datetime.now() - timedelta(hours=1)
        other.action_stop(employee_ids=[self.leader.id])
        self.assertNotEqual(other.timesheet_ids.task_id, task)
        self.assertEqual(other.timesheet_ids.task_id.schldr_work_kind, "uitvoering")
        self.assertEqual(timer.timesheet_ids.employee_id, self.leader)

    def test_cancel_removes_timesheets(self):
        timer = self.env["schldr.timer"]._start(self.project, self.leader)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=1)
        timer.action_stop()
        lines = timer.timesheet_ids
        self.assertTrue(lines)
        timer.action_cancel()
        self.assertEqual(timer.state, "cancelled")
        self.assertFalse(lines.exists())

    def test_start_without_planning_books_starter(self):
        timer = self.env["schldr.timer"]._start(self.other_project, self.outsider)
        self.assertEqual(timer.employee_ids, self.outsider)

    def test_forgotten_timer_is_stopped(self):
        timer = self.env["schldr.timer"]._start(self.project, self.leader)
        timer.start_datetime = fields.Datetime.now() - timedelta(hours=20)
        self.env["schldr.timer"]._cron_stop_forgotten_timers()
        self.assertEqual(timer.state, "done")
        self.assertAlmostEqual(timer.duration_hours, 16.0, places=1)
        self.assertIn("Automatisch gestopt", timer.notes)
        self.assertEqual(len(timer.timesheet_ids), 2)


@tagged("post_install", "-at_install")
class TestPortalRoutes(HttpCase, SchldrPortalCase):

    def _csrf(self, html):
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
        self.assertTrue(match, "the page carries a csrf token")
        return match.group(1)

    def test_portal_pages(self):
        self.authenticate(self.portal_user.login, "portal-test-123")
        response = self.url_open("/my/werven")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Woning Kerkstraat", response.text)
        self.assertNotIn("Andere woning", response.text)

        url = "/my/werven/%d" % self.project.id
        for tab in ("overview", "materials", "plan", "report"):
            response = self.url_open("%s?tab=%s" % (url, tab))
            self.assertEqual(response.status_code, 200, tab)

        # the plan tab draws the plan and says which paint goes where
        work = self.env["product.product"].sudo().create({"name": "Muren schilderen", "type": "service"})
        system = self.env["schldr.paint.system"].sudo().create({
            "name": "Muren: 2 lagen mat", "product_id": work.id, "on_walls": True,
        })
        colour = self.env["schldr.colour"].sudo().create({"name": "Salie", "code": "S 3010-G30Y"})
        project = self.project.sudo()
        project.canvas_data = json.dumps({
            "defaults": {"assign": {"walls": [{"system": system.id, "colour": colour.id}]}},
            "levels": [{"rooms": [{
                "name": "Woonkamer", "height": 2600,
                "points": [[0, 0], [5000, 0], [5000, 4000], [0, 4000]],
            }]}],
        })
        project.action_sync_from_canvas()
        response = self.url_open("%s?tab=plan" % url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("data:image/png;base64,", response.text)
        self.assertIn("Woonkamer", response.text)
        self.assertIn("Muren: 2 lagen mat", response.text)
        self.assertIn("S 3010-G30Y Salie", response.text)
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
