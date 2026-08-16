# -*- coding: utf-8 -*-
"""Map the old single-selection product.category.tectora_usage to the new
many2many tectora_usage_ids. The obsolete column is left in place (Odoo keeps
orphaned columns); it simply stops being used."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'product_category' AND column_name = 'tectora_usage'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        INSERT INTO product_category_tectora_usage_rel (category_id, usage_id)
        SELECT c.id, u.id
        FROM product_category c
        JOIN tectora_roof_usage u ON u.code = c.tectora_usage
        WHERE c.tectora_usage IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
