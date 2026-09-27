# -*- coding: utf-8 -*-
def post_init_hook(env):
    # The supplier catalogue replaced the price book as the product source;
    # the price-book importer stays available for reference/rollback.
    env["product.template"]._tectora_import_product_catalog()
    # The quotation templates quote those products, so they come second.
    env["sale.order.template"]._tectora_import_quotation_templates()
