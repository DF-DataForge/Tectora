# -*- coding: utf-8 -*-
"""Give the material lines that existed before the install their route.

Stored computed fields of a new module are computed before its data files are
loaded, so at that moment the two logistic routes do not exist yet and every
existing line ends up without one. Once the routes are there, the compute is
simply run again for those lines.
"""


def post_init_hook(env):
    lines = env["tectora.roof.material"].search([("logistics_route_id", "=", False)])
    if lines:
        lines._compute_logistics_route_id()
