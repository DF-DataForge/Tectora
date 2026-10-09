# -*- coding: utf-8 -*-
"""Completing a database from a catalogue export: missing works items are
created, empty sales descriptions filled, and nothing that is already there
is overwritten."""
from odoo.tests import TransactionCase, tagged

from ..models import catalog_rules

HEADER = ["productcode", "naam NL", "aankoopprijs excl BTW", "verkoopprijs excl BTW",
          "eenheid", "leverancier", "productgroup", "lange omschrijving NL"]


@tagged("post_install", "-at_install")
class TestCatalogComplete(TransactionCase):

    def test_html_to_text(self):
        html = ('<p><em><span style="font-size: 8pt;">Transport overheen het gebouw</span></em></p>\n'
                '<p>Inname&nbsp;openbaar domein &amp; vergunning</p><ul><li>a</li><li>b</li></ul>')
        self.assertEqual(
            catalog_rules.html_to_text(html),
            "Transport overheen het gebouw\nInname openbaar domein & vergunning\n- a\n- b",
        )

    def test_description_column_and_duplicates(self):
        rows = [
            ["S90001", "Post een", 0, 85, "st", None, "ALGEMEEN", "<p>Lange tekst</p>"],
            ["S90001", "Post een bis", 0, 50, "st", None, "ALGEMEEN", ""],
        ]
        entries, stats = catalog_rules.parse_rows(HEADER, rows, {})
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["description"], "Lange tekst")
        self.assertEqual(stats["duplicate_codes"], ["S90001"])

    def test_complete_mode(self):
        Product = self.env["product.template"]
        existing = Product.create({
            "name": "Post bestaand", "default_code": "S90002", "list_price": 74.0,
        })
        described = Product.create({
            "name": "Post met tekst", "default_code": "S90003",
            "description_sale": "Eigen tekst",
        })
        without_code = Product.create({"name": "Afvalverwerking test forfaitair"})
        rows = [
            ["S90002", "Post bestaand (Simpla)", 0, 0, "st", None, "ALGEMEEN", "<p>Uitleg</p>"],
            ["S90003", "Post met tekst", 0, 10, "st", None, "ALGEMEEN", "<p>Simpla-tekst</p>"],
            ["S90004", "Afvalverwerking test forfaitair", 0, 0, "st", None, "ALGEMEEN", ""],
            ["S90005", "Nieuwe post", 0, 120, "m²", None, "ISOLATIE", "<p>Nieuw</p>"],
        ]
        entries, _stats = catalog_rules.parse_rows(HEADER, rows, {})
        counters = Product._tectora_apply_catalog(entries, {"mode": "complete"})

        self.assertEqual(existing.name, "Post bestaand", "name kept")
        self.assertEqual(existing.list_price, 74.0, "price kept")
        self.assertEqual(existing.description_sale, "Uitleg", "empty description filled")
        self.assertEqual(described.description_sale, "Eigen tekst", "description kept")
        self.assertEqual(without_code.default_code, "S90004", "reference given, no twin")
        self.assertEqual(Product.search_count([("name", "=", "Afvalverwerking test forfaitair")]), 1)
        new = Product.search([("default_code", "=", "S90005")])
        self.assertTrue(new)
        self.assertEqual(new.list_price, 120.0)
        self.assertEqual(new.description_sale, "Nieuw")
        self.assertEqual(new.type, "service")
        self.assertEqual(counters["created"], 1)
        self.assertEqual(counters["completed"], 2)
        self.assertEqual(counters["unchanged"], 1)
