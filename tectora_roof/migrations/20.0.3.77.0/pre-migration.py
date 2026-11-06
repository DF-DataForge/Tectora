# -*- coding: utf-8 -*-
"""'Splits per dag' is gone (the scissors of the planner cut a block).
Views of other modules that hang on its button (tectora_roof_planning's
"Open in planner") are re-anchored first, so the planning form still
validates while this module is upgraded; their own upgrade then writes the
same anchor."""


def migrate(cr, version):
    cr.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'ir_ui_view' AND column_name = 'arch_db'"
    )
    row = cr.fetchone()
    cast = "::jsonb" if row and row[0] == "jsonb" else ""
    cr.execute(
        """
        UPDATE ir_ui_view
           SET arch_db = replace(arch_db::text, %%s, %%s)%s
         WHERE arch_db::text LIKE %%s
        """ % cast,
        ("@name='action_split'", "@name='action_set_done'", "%@name='action_split'%"),
    )
