# -*- coding: utf-8 -*-
"""The ploegen app: a ploeg of contacts, the employees behind them, and the
vehicles of the wagenpark."""
from datetime import datetime

from odoo.tests import TransactionCase, tagged

from ..hooks import post_init_hook


@tagged("post_install", "-at_install")
class TestTeams(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        Partner = cls.env["res.partner"]
        cls.jan = Partner.create({"name": "Jan Dakwerker"})
        cls.piet = Partner.create({"name": "Piet Onderaannemer"})
        cls.boss = Partner.create({"name": "Baas Ploegbaas"})
        Employee = cls.env["hr.employee"]
        # Jan and the ploegbaas are employees too; Piet is a contact only.
        cls.jan_employee = Employee.create({"name": "Jan Dakwerker", "work_contact_id": cls.jan.id})
        cls.boss_employee = Employee.create({"name": "Baas Ploegbaas", "work_contact_id": cls.boss.id})
        cls.team = cls.env["tectora.roof.team"].create({
            "name": "Ploeg Noord",
            "partner_ids": [(6, 0, (cls.jan | cls.piet).ids)],
            "leader_partner_id": cls.boss.id,
        })

    def test_ploeg_of_contacts(self):
        team = self.team
        self.assertIn(self.boss, team.partner_ids, "the ploegbaas is a member")
        self.assertEqual(team.partner_count, 3)
        self.assertEqual(team.leader_id, self.boss_employee, "the ploegbaas of what works per employee")
        # The employees of the ploeg: those behind its contacts.
        self.assertEqual(team.member_ids, self.jan_employee | self.boss_employee)
        self.assertEqual(team.member_count, 2)
        self.assertEqual(self.jan.roof_team_ids, team)
        # A contact leaves: its employee is off the ploeg.
        team.partner_ids = [(3, self.jan.id)]
        self.assertEqual(team.member_ids, self.boss_employee)

    def test_ploeg_without_contacts_keeps_its_employees(self):
        team = self.env["tectora.roof.team"].create({"name": "Ploeg Zuid"})
        employee = self.env["hr.employee"].create({"name": "Mia", "roof_team_id": team.id})
        self.assertEqual(team.member_ids, employee)

    def test_vehicles(self):
        brand = self.env["fleet.vehicle.model.brand"].create({"name": "Renault"})
        model = self.env["fleet.vehicle.model"].create({"name": "Master", "brand_id": brand.id})
        van = self.env["fleet.vehicle"].create({
            "model_id": model.id, "license_plate": "1-ABC-123", "roof_team_id": self.team.id,
        })
        self.assertEqual(self.team.vehicle_ids, van)
        self.assertEqual(self.team.vehicle_count, 1)
        self.assertEqual(self.team.action_view_vehicles()["domain"], [("roof_team_id", "=", self.team.id)])
        roof = self.env["tectora.roof.project"].create({"name": "Werf"})
        block = self.env["tectora.roof.planning"].create({
            "project_id": roof.id, "team_id": self.team.id,
            "start_datetime": datetime(2026, 11, 30, 7, 0), "end_datetime": datetime(2026, 11, 30, 16, 0),
        })
        self.assertIn("1-ABC-123", block.vehicle_names)
        # The block takes the employees of the ploeg along, as before.
        block.write({"team_id": self.team.id})
        self.assertEqual(block.employee_ids, self.jan_employee | self.boss_employee)

    def test_existing_ploegen_come_along(self):
        """On install the employees of a ploeg become its contacts."""
        team = self.env["tectora.roof.team"].create({"name": "Ploeg Oost"})
        mia = self.env["hr.employee"].create({"name": "Mia", "roof_team_id": team.id})
        team.leader_id = self.boss_employee
        self.assertTrue(mia.work_contact_id)
        post_init_hook(self.env)
        self.assertEqual(team.partner_ids, mia.work_contact_id | self.boss)
        self.assertEqual(team.leader_partner_id, self.boss)
        self.assertEqual(team.member_ids, mia | self.boss_employee)
