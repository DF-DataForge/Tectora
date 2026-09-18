# -*- coding: utf-8 -*-
from odoo import fields, models

from .sale_order import QUOTATION_STYLES


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    tectora_google_maps_api_key = fields.Char(
        string="Google Maps API key",
        config_parameter="tectora_roof.google_maps_api_key",
        help="Used for geocoding and satellite imagery (Static Maps API). "
        "Takes precedence over Mapbox when both are set.",
    )
    tectora_mapbox_token = fields.Char(
        string="Mapbox access token",
        config_parameter="tectora_roof.mapbox_token",
        help="Fallback mapping provider when no Google Maps key is configured.",
    )
    tectora_standard_quotation = fields.Boolean(
        string="Standaard offerte",
        config_parameter="tectora_roof.standard_quotation",
        help="Nieuwe offertes gebruiken het standaard offertedocument van Odoo "
        "in plaats van de Tectora-offerte; per offerte aan te passen.",
    )
    tectora_quotation_style = fields.Selection(
        QUOTATION_STYLES,
        string="Standaardstijl offerte",
        config_parameter="tectora_roof.quotation_style",
        default="dossier",
        help="De stijl die een nieuwe Tectora-offerte krijgt; per offerte aan "
        "te passen.",
    )
