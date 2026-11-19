# -*- coding: utf-8 -*-
"""Geopunt (Digitaal Vlaanderen) on the roof project: the site address
geocoded without a key and its cadastral parcel, with the API answered by a
mock."""
import io
from unittest.mock import patch

from PIL import Image

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.tectora_roof.models import geopunt, roof_project


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self.payload = payload
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise geopunt.requests.HTTPError("HTTP %s" % self.status_code)

    def json(self):
        return self.payload


LOCATION = {"LocationResult": [{
    "Municipality": "Gent", "Zipcode": "9000",
    "Thoroughfarename": "Veldstraat", "Housenumber": "10",
    "FormattedAddress": "Veldstraat 10, 9000 Gent",
    "Location": {
        "Lat_WGS84": 51.0533114, "Lon_WGS84": 3.7220956,
        "X_Lambert72": 104659.2, "Y_Lambert72": 193880.89,
    },
    "LocationType": "basisregisters_huisnummer_aangeduidDoorBeheerder",
}]}
PARCEL = {
    "municipalityName": "Gent", "departmentName": "GENT 3 AFD",
    "capakey": "44803C0113/00D000",
}


def png():
    stream = io.BytesIO()
    Image.new("RGB", (8, 8)).save(stream, "PNG")
    return stream.getvalue()


@tagged("post_install", "-at_install")
class TestGeopunt(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.roof = cls.env["tectora.roof.project"].create({
            "name": "Werf Gent", "address": "Veldstraat 10, 9000 Gent",
        })

    def _api(self, calls, location=LOCATION, parcel=PARCEL):
        def fake_get(url, params=None, headers=None, timeout=None):
            calls.append((url, params))
            if url == geopunt.LOCATION_URL:
                return FakeResponse(location)
            if url == geopunt.PARCEL_URL:
                return FakeResponse(parcel, status_code=200 if parcel else 500)
            if url == roof_project.GOOGLE_GEOCODE_URL:
                return FakeResponse({"status": "OK", "results": [{
                    "geometry": {"location": {"lat": 50.4669, "lng": 4.8675}},
                    "formatted_address": "Place d'Armes 1, 5000 Namur, België",
                }]})
            return FakeResponse(content=png())
        return patch.object(geopunt.requests, "get", fake_get)

    def test_parcel_is_looked_up_from_the_address(self):
        calls = []
        with self._api(calls):
            self.roof.action_lookup_parcel()
        self.assertEqual(self.roof.capakey, "44803C0113/00D000")
        self.assertEqual(self.roof.cadastral_department, "GENT 3 AFD")
        self.assertEqual(calls[0], (geopunt.LOCATION_URL, {"q": "Veldstraat 10, 9000 Gent", "c": 1}))
        self.assertEqual(
            calls[1], (geopunt.PARCEL_URL, {"x": 104659.2, "y": 193880.89, "srs": 31370})
        )

        # The parcel belongs to the address.
        self.roof.address = "Korenmarkt 1, 9000 Gent"
        self.assertFalse(self.roof.capakey)
        self.assertFalse(self.roof.cadastral_department)

    def test_unknown_address_or_no_parcel_is_told(self):
        with self._api([], location={"LocationResult": []}), self.assertRaises(UserError):
            self.roof.action_lookup_parcel()
        with self._api([], parcel=None), self.assertRaises(UserError):
            self.roof.action_lookup_parcel()
        self.assertFalse(self.roof.capakey)

    def test_satellite_is_geocoded_by_geopunt(self):
        self.env["ir.config_parameter"].sudo().set_str(
            "tectora_roof.google_maps_api_key", "sleutel"
        )
        calls = []
        with self._api(calls):
            self.roof.action_fetch_satellite()
        urls = [url for url, _params in calls]
        self.assertNotIn(roof_project.GOOGLE_GEOCODE_URL, urls)
        self.assertAlmostEqual(self.roof.bg_lat, 51.0533114, places=6)
        self.assertAlmostEqual(self.roof.bg_lng, 3.7220956, places=6)
        self.assertEqual(self.roof.address, "Veldstraat 10, 9000 Gent", "as typed")
        self.assertEqual(self.roof.capakey, "44803C0113/00D000")

    def test_outside_flanders_falls_back_on_the_map_service(self):
        self.env["ir.config_parameter"].sudo().set_str(
            "tectora_roof.google_maps_api_key", "sleutel"
        )
        self.roof.address = "Place d'Armes 1, 5000 Namur"
        calls = []
        with self._api(calls, location={"LocationResult": []}):
            self.roof.action_fetch_satellite()
        urls = [url for url, _params in calls]
        self.assertIn(roof_project.GOOGLE_GEOCODE_URL, urls)
        self.assertNotIn(geopunt.PARCEL_URL, urls)
        self.assertAlmostEqual(self.roof.bg_lat, 50.4669, places=4)
        self.assertFalse(self.roof.capakey)
