# -*- coding: utf-8 -*-
def post_init_hook(env):
    env["product.template"]._tectora_import_price_book()
