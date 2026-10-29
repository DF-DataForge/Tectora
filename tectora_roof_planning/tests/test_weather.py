# -*- coding: utf-8 -*-
"""Weather forecasts on the work blocks, with Open-Meteo answered by a mock."""
from datetime import datetime, time, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.tectora_roof_planning.models import weather


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def forecast_payload(start, days):
    """Open-Meteo's daily answer: today cloudy, tomorrow dry and mild, the
    day after rain and wind."""
    dates = [str(start + timedelta(days=index)) for index in range(days)]
    return {
        "daily": {
            "time": dates,
            "weather_code": [3, 1, 63] + [3] * (days - 3),
            "temperature_2m_max": [14, 16, 12] + [14] * (days - 3),
            "temperature_2m_min": [9, 8, 7] + [9] * (days - 3),
            "precipitation_sum": [0, 0, 6.4] + [0] * (days - 3),
            "precipitation_probability_max": [20, 10, 90] + [20] * (days - 3),
            "wind_gusts_10m_max": [30, 25, 62] + [30] * (days - 3),
        }
    }


@tagged("post_install", "-at_install")
class TestWeather(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.env.user.tz = "Europe/Brussels"
        cls.roof = cls.env["tectora.roof.project"].create({
            "name": "Werf Heule", "bg_lat": 50.8371, "bg_lng": 3.2389,
        })
        cls.today = fields.Date.context_today(cls.env["tectora.roof.planning"])

    def _block(self, first_day, last_day):
        return self.env["tectora.roof.planning"].create({
            "project_id": self.roof.id,
            "start_datetime": datetime.combine(self.today + timedelta(days=first_day), time(6)),
            "end_datetime": datetime.combine(self.today + timedelta(days=last_day), time(15)),
        })

    def test_refresh_puts_the_worst_day_on_the_block(self):
        dry = self._block(1, 1)
        wet = self._block(1, 2)
        calls = []

        def fake_get(url, params=None, timeout=None):
            calls.append((url, params))
            return FakeResponse(forecast_payload(self.today, weather.FORECAST_DAYS))

        with patch.object(weather.requests, "get", fake_get):
            action = self.env["tectora.roof.planning"].action_tectora_refresh_weather()
        self.assertEqual(len(calls), 1, "one call for both blocks at the same site")
        self.assertEqual(calls[0][1]["latitude"], "50.84")
        self.assertEqual(action["params"]["type"], "success")

        self.assertFalse(dry.weather_alert)
        self.assertEqual(dry.weather_icon, "🌤️")
        self.assertTrue(wet.weather_alert)
        self.assertEqual(wet.weather_icon, "🌧️", "the worst day of the block")
        self.assertIn("regen", wet.weather_alert_reason)
        self.assertIn("windstoten", wet.weather_alert_reason)
        self.assertEqual(len(wet.weather_days.splitlines()), 2)
        self.assertTrue(wet.display_name.startswith("⚠️🌧️ "))

        # Moved to the dry day: the kept forecast, no new call.
        with patch.object(weather.requests, "get", fake_get):
            wet.write({
                "end_datetime": datetime.combine(self.today + timedelta(days=1), time(15)),
            })
        self.assertEqual(len(calls), 1)
        self.assertFalse(wet.weather_alert)

    def test_failing_api_keeps_the_planner_working(self):
        block = self._block(1, 1)

        def failing_get(url, params=None, timeout=None):
            raise weather.requests.ConnectionError("offline")

        with patch.object(weather.requests, "get", failing_get):
            action = self.env["tectora.roof.planning"].action_tectora_refresh_weather()
        self.assertEqual(action["params"]["type"], "warning")
        self.assertFalse(block.weather_summary)

    def test_site_without_image_is_geocoded_once(self):
        roof = self.env["tectora.roof.project"].create({
            "name": "Werf zonder foto", "address": "Lostraat 15, 1703 Schepdaal",
        })
        calls = []

        def fake_get(url, params=None, timeout=None):
            calls.append(url)
            return FakeResponse({"results": [{"latitude": 50.8333, "longitude": 4.2}]})

        with patch.object(weather.requests, "get", fake_get):
            self.assertEqual(roof._tectora_weather_location(), (50.83, 4.2))
            self.assertEqual(roof._tectora_weather_location(), (50.83, 4.2))
        self.assertEqual(calls, [weather.GEOCODE_URL], "looked up once, then kept")
