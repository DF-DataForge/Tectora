# -*- coding: utf-8 -*-
"""Raw materials are filed by material type, the sales products by the
chapters of the roof planner."""
import json

from odoo.tests import TransactionCase, tagged

from ..models import catalog_rules
from ..models.product_template import DEFAULT_ROOT_CATEGORY, PRODUCT_CATALOG


@tagged("post_install", "-at_install")
class TestGoodsCategories(TransactionCase):

    def test_material_types(self):
        cases = {
            "ELEVATE EPDM FOLIE 1,5MM (15,25X30,5M) 465,13M2": "Dakbanen/EPDM",
            "ALUTRIX 600 DAMPSCHERM 0,6MM 1,08X40M": "Dampschermen & folies",
            "UTHERM ROOF L 80MM 1200/600": "Isolatie/PIR",
            "ROCKWOOL RHINOXX 50MM 100/060": "Isolatie/Minerale wol",
            "ELEVATE BONDING ADHESIVE BA-2012 20L/POT": "Lijmen, primers & kitten",
            "ELEVATE SPLICE TAPE 7,62CM": "Tapes, strips & flashings",
            "Dakrand DRB 80/62 Stock kleur": "Dakranden & profielen",
            "ZINK VM AFVOERB 80MM (2M) 0,70 MM": "Zinkwerk & hemelwater",
            "Geberit PE bocht 88° 50 x 50 mm": "Afvoerleidingen PE & PP",
            "ROOF AFVOER PE DIA 75 L 60CM MET ROOFINGSLAB": "Dakafvoeren & spuwers",
            "Isolatieschroeven 4,8 x 300mm AE": "Bevestigingsmaterialen",
            "Krachtbit 1/4\" PH 2x25 mm": "Gereedschap & verbruiksmateriaal",
        }
        for name, path in cases.items():
            self.assertEqual(catalog_rules.branch_path("04. Opbouwwerken plat dak/Afvoer", False, name),
                             "Grondstoffen/" + path, name)
        # A sales product keeps its chapter.
        self.assertEqual(
            catalog_rules.branch_path("04. Opbouwwerken plat dak/Isolatie", True, "UTHERM"),
            "04. Opbouwwerken plat dak/Isolatie",
        )

    def test_shipped_catalogue_has_no_leftovers(self):
        products = json.loads(PRODUCT_CATALOG.read_text(encoding="utf-8"))["products"]
        leftovers = [
            p["name"] for p in products
            if not p["is_service"]
            and catalog_rules.branch_path(p["category_path"], False, p["name"]).endswith("/Overige")
        ]
        self.assertFalse(leftovers)

    def test_refile_goods(self):
        Product = self.env["product.template"]
        old = Product._tectora_resolve_category(
            "Grondstoffen/04. Opbouwwerken plat dak/Afvoer", DEFAULT_ROOT_CATEGORY
        )
        geberit = Product.create({"name": "Geberit PE bocht 88° 50 x 50 mm", "categ_id": old.id})
        zinc = Product.create({"name": "ZINK VM AFVOERB 80MM (2M)", "categ_id": old.id})
        Product._tectora_refile_goods()
        self.assertEqual(geberit.categ_id.name, "Afvoerleidingen PE & PP")
        self.assertEqual(zinc.categ_id.name, "Zinkwerk & hemelwater")
        self.assertEqual(geberit.categ_id.parent_id.name, "Grondstoffen")
        self.assertFalse(old.exists(), "the emptied mirrored chapter is removed")
