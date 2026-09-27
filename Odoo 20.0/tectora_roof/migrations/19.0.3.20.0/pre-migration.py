# -*- coding: utf-8 -*-
"""The standard Odoo document is a checkbox now, "Standaard offerte", instead
of a value in the style list. Orders and the default setting that had the
"standard" style get the checkbox; the style falls back to the dossier. Done
before the models load, so no row holds a value the selection no longer has."""


def migrate(cr, version):
    cr.execute(
        """
        ALTER TABLE sale_order
        ADD COLUMN IF NOT EXISTS tectora_standard_quotation boolean
        """
    )
    cr.execute(
        """
        UPDATE sale_order
        SET tectora_standard_quotation = TRUE, tectora_quotation_style = 'dossier'
        WHERE tectora_quotation_style = 'standard'
        """
    )
    cr.execute(
        """
        SELECT value FROM ir_config_parameter
        WHERE key = 'tectora_roof.quotation_style'
        """
    )
    row = cr.fetchone()
    if row and row[0] == "standard":
        cr.execute(
            """
            UPDATE ir_config_parameter SET value = 'dossier'
            WHERE key = 'tectora_roof.quotation_style'
            """
        )
        cr.execute(
            """
            INSERT INTO ir_config_parameter (key, value, create_date, write_date)
            VALUES ('tectora_roof.standard_quotation', 'True', now(), now())
            ON CONFLICT (key) DO UPDATE SET value = 'True', write_date = now()
            """
        )
