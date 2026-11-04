# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests import BaseCase, tagged

from ..models import quote_rules

HEADER = (
    "offertenummer", "geldigheidstermijn", "offertedatum", "verkoop", "aantal",
    "eenheid", "kortingspercentage", "BTW-percentage", "eenheidsprijs",
    "opmerkingen", "klantnaam", "referentie klant", "straat nr", "postcode",
    "plaats", "BTW-nummer", "totaal ex BTW", "BTW", "totaal inc BTW",
    "grootboekrekening", "status",
)


def row(number, description, quantity, unit, price, total, status="openstaand",
        discount=0, vat=6, notes="", customer="Dhr. Peeters",
        vat_number="be 0477.472.701"):
    return (number, 15, "19/01/2026", description, quantity, unit, discount, vat,
            price, notes, customer, "Dak garage", "Kerkstraat 1", "8800",
            "Roeselare", vat_number, total, total * vat / 100.0,
            total * (1 + vat / 100.0), "", status)


@tagged("post_install", "-at_install")
class TestQuoteRules(BaseCase):

    def test_quotes_and_lines(self):
        rows = [
            row("2026/0001", "Verwijderen van de tapbuis", 1, "st", 22.15, 22.15),
            row("2026/0001", "ALGEMENE WERKEN", 0, "", 0, 0),
            row("2026/0001", "Leveren en plaatsen solins", 4.5, "lm BLAUW", 10, 45,
                notes="Dit document werd digitaal ondertekend &ndash; ok"),
            row("2026/0002", "Afvalverwerking", 1, "sog", 182.36, 182.36,
                status="gefactureerd"),
            (None, None, None, None, "==SUM(E2:E5)") + (None,) * 16,
        ]
        quotes, stats = quote_rules.parse_rows(HEADER, rows)
        self.assertEqual([q["number"] for q in quotes], ["2026/0001", "2026/0002"])
        first = quotes[0]
        self.assertEqual(first["date"], date(2026, 1, 19))
        self.assertEqual(first["validity_date"], date(2026, 2, 3))
        self.assertEqual(first["customer"]["vat"], "BE0477472701")
        self.assertEqual(first["customer_ref"], "Dak garage")
        self.assertEqual(first["notes"], "Dit document werd digitaal ondertekend – ok")
        self.assertEqual([line["kind"] for line in first["lines"]],
                         ["product", "text", "product"])
        self.assertEqual(first["lines"][2]["unit"], "lm")
        self.assertAlmostEqual(first["total"], 67.15)
        self.assertEqual(quotes[1]["status"], "gefactureerd")
        self.assertEqual(stats["rows"], 4)
        self.assertEqual(stats["text_lines"], 1)
        self.assertEqual(stats["product_lines"], 3)

    def test_multiplied_line_takes_the_factor(self):
        rows = [row("2026/0006", "Buitenhoek", 3, "st", 24.85, 149.10)]
        quotes, stats = quote_rules.parse_rows(HEADER, rows)
        line = quotes[0]["lines"][0]
        self.assertEqual(line["quantity"], 6)
        self.assertEqual(line["price"], 24.85)
        self.assertEqual(stats["multiplied"], 1)

    def test_other_difference_reprices(self):
        rows = [row("2026/0007", "Spouwplaat", 2, "m²", 10, 25)]
        quotes, stats = quote_rules.parse_rows(HEADER, rows)
        line = quotes[0]["lines"][0]
        self.assertEqual(line["quantity"], 2)
        self.assertAlmostEqual(line["price"], 12.5)
        self.assertEqual(stats["repriced"], 1)

    def test_discount_and_optional_line(self):
        rows = [
            row("2026/0008", "Buitenhoeken", 1, "st", 45.71, 45.2529, discount=1),
            row("2026/0008", "Gebruik van het ankerpunt", 0, "st", 175, 0),
        ]
        quotes, stats = quote_rules.parse_rows(HEADER, rows)
        lines = quotes[0]["lines"]
        self.assertEqual([line["kind"] for line in lines], ["product", "product"])
        self.assertEqual(lines[0]["discount"], 1)
        self.assertEqual(lines[1]["quantity"], 0)
        self.assertEqual(stats["multiplied"] + stats["repriced"], 0)

    def test_helpers(self):
        self.assertEqual(quote_rules.normalise_vat("0886.323.840"), "BE0886323840")
        self.assertEqual(quote_rules.normalise_vat("BE0795 292 805"), "BE0795292805")
        self.assertEqual(quote_rules.normalise_vat(""), "")
        self.assertEqual(quote_rules.clean_unit(" ORANJE"), "")
        self.assertEqual(quote_rules.clean_unit("stuks GROEN"), "stuks")
        self.assertEqual(quote_rules.clean_unit("21.4"), "")
        self.assertEqual(quote_rules.number("1.234,50"), 1234.5)
        self.assertEqual(quote_rules.parse_date("26/10/2026"), date(2026, 10, 26))

    def test_missing_column(self):
        with self.assertRaisesRegex(ValueError, "status"):
            quote_rules.parse_rows(HEADER[:-1], [])

    def test_sections_domes_and_two_roofs(self):
        def r(description, quantity=1, price=10):
            return row("2026/0020", description, quantity, "st", price, quantity * price)
        rows = [r(d, 0, 0) if d.isupper() or d.startswith("Voorschot") else r(d) for d in (
            "AFBOUWWERKEN THV DE KOEPELS",
            "AFBOUWWERKEN THV HET HOOGSTE PLAT DAK",
            "AFBOUWWERKEN THV HET LAAGSTE PLAT DAK",
            "ALGEMENE WERKEN",
            "Algemene vaste kosten",
            "DAMPSCHERM",
            "Leveren en plaatsen van de koepelschaal",
            "Leveren en plaatsen van het dampscherm",
            "OPBOUWWERKEN THV DE KOEPELS",
            "OPBOUWWERKEN THV HET HOOGSTE PLAT DAK",
            "OPBOUWWERKEN THV HET LAAGSTE PLAT DAK",
            "Verwijderen van de dakranden",
            "Verwijderen van de dakranden",
            "Verwijderen van de koepel",
            "Voorschot: 50% na akkoord.",
        )]
        rows.append(r("Gebruik van tijdelijke balustrades", 0, 9.5))
        quotes, _stats = quote_rules.parse_rows(HEADER, rows)
        blocks, notes, empty = quote_rules.arrange_sections(quotes[0])
        arranged = [(title, [line["description"] for line in lines]) for title, lines in blocks]
        self.assertEqual(arranged, [
            ("ALGEMENE WERKEN", ["Algemene vaste kosten", "Gebruik van tijdelijke balustrades"]),
            ("AFBOUWWERKEN THV HET HOOGSTE PLAT DAK", ["Verwijderen van de dakranden"]),
            ("DAMPSCHERM", ["Leveren en plaatsen van het dampscherm"]),
            ("AFBOUWWERKEN THV HET LAAGSTE PLAT DAK", ["Verwijderen van de dakranden"]),
            ("AFBOUWWERKEN THV DE KOEPELS", ["Verwijderen van de koepel"]),
            ("OPBOUWWERKEN THV DE KOEPELS", ["Leveren en plaatsen van de koepelschaal"]),
        ])
        self.assertEqual([line["description"] for line in notes], ["Voorschot: 50% na akkoord."])
        self.assertEqual(empty, ["OPBOUWWERKEN THV HET HOOGSTE PLAT DAK",
                                 "OPBOUWWERKEN THV HET LAAGSTE PLAT DAK"])

    def test_title_recognition(self):
        self.assertTrue(quote_rules.is_title("COMMERCIËLE TEGEMOETKOMING"))
        self.assertTrue(quote_rules.is_title("34.12.20 Isolatieplaten plat dak - PUR 20cm"))
        self.assertFalse(quote_rules.is_title("Werken kunnen uitgevoerd worden in maart."))
        self.assertEqual(quote_rules.section_family("ALGEMENE NOTA'S"), "nota")
        self.assertEqual(quote_rules.section_family("OPBOUWWERKEN THV DE KOEPELS"), "opbouw")
        self.assertEqual(quote_rules.section_family("MEERWERK BIJ UITVOERING"), "optie")
