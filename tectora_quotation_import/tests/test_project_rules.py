# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import BaseCase, tagged

from ..models import project_rules


def order(id_, name, total, confirmed=True, vat="", project=None):
    return {"id": id_, "names": {name}, "vat": vat, "total": total,
            "confirmed": confirmed, "project": project}


def project(number, customer, total, vat=""):
    return {"number": number, "customer": customer, "vat": vat, "total": total}


@tagged("post_install", "-at_install")
class TestProjectRules(BaseCase):

    def test_match_on_customer_and_total(self):
        orders = [
            order(1, "Dhr. Peeters", 100.0),
            order(2, "Dhr. Peeters", 50.0),
            order(3, "Dhr. Peeters", 25.0),
            order(4, "Garage Noord BV", 99.0, vat="BE0477472701"),
        ]
        projects = [
            project("P1", "Dhr.  PEETERS", 75.0),          # two orders together
            project("P2", "Dhr. Peeters", 100.0),
            project("P3", "Garage Noord", 99.0, vat="BE0477472701"),  # on the VAT number
            project("P4", "Dhr. Peeters", 0.0),
        ]
        assignment, ambiguous = project_rules.match_projects(projects, orders)
        self.assertEqual(sorted(assignment["P1"]), [2, 3])
        self.assertEqual(assignment["P2"], [1])
        self.assertEqual(assignment["P3"], [4])
        self.assertNotIn("P4", assignment)
        self.assertFalse(ambiguous)

    def test_confirmed_order_wins_and_an_order_is_used_once(self):
        orders = [
            order(1, "Fam. Claeys", 500.0, confirmed=False),
            order(2, "Fam. Claeys", 500.0, confirmed=True),
            order(3, "Fam. Claeys", 300.0, project="OLD"),
        ]
        assignment, ambiguous = project_rules.match_projects(
            [project("P1", "Fam. Claeys", 500.0), project("P2", "Fam. Claeys", 300.0)], orders
        )
        self.assertEqual(assignment["P1"], [2])
        self.assertNotIn("P2", assignment, "order 3 belongs to project OLD")
        self.assertFalse(ambiguous)

    def test_teams(self):
        teams = [(1, "Team 1"), (2, "Team 2"), (3, "Drenica"), (4, "Kepr Algemene schrijnwerken")]
        self.assertEqual(project_rules.guess_teams("TEAM 1 TECTORA: MARIUSZ & MARCIN", teams), [1])
        self.assertEqual(project_rules.guess_teams("TEAM 1 + TEAM 2", teams), [1, 2])
        self.assertEqual(project_rules.guess_teams("DRENICA TEAM 2", teams), [3])
        self.assertEqual(project_rules.guess_teams("KÉPR Algemene schrijnwerken", teams), [4])
        self.assertEqual(project_rules.guess_teams("TM TOTALE RENOVATIE BV", teams), [])

    def test_phase_and_window(self):
        self.assertEqual(project_rules.phase("afgesloten"), "closed")
        self.assertEqual(project_rules.phase("Slotfactuur bezorgd en in afwachting betaling"),
                         "executed")
        self.assertEqual(project_rules.phase("Alle materialen zijn besteld bij leveranciers"),
                         "open")
        # Three working days ending on Monday 2 November: Thursday to Monday.
        self.assertEqual(project_rules.working_days_window(date(2026, 11, 2), 2.4),
                         (date(2026, 10, 29), date(2026, 11, 2)))
        # A deadline on a Saturday ends on the Friday before.
        self.assertEqual(project_rules.working_days_window(date(2026, 10, 31), 0),
                         (date(2026, 10, 30), date(2026, 10, 30)))
