# -*- coding: utf-8 -*-
"""The dossier on/off switch became a choice of quotation style: orders that
had the standard document keep it."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sale_order' AND column_name = 'tectora_dossier_layout'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE sale_order
        SET tectora_quotation_style = 'standard'
        WHERE tectora_dossier_layout IS NOT TRUE
        """
    )
    cr.execute(
        """
        UPDATE sale_order
        SET tectora_quotation_style = 'dossier'
        WHERE tectora_quotation_style IS NULL
        """
    )
