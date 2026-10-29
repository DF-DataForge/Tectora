# -*- coding: utf-8 -*-
"""Weather forecasts on the work blocks, from Open-Meteo (no API key).

A scheduled action fetches every morning the daily forecast of the next 16
days for every site with a work block in that period, and keeps it per
location and day (tectora.weather.forecast). The work blocks take a summary
from it into stored fields (icon, summary, day by day, a warning for roofing
work), so the planner shows them without calling the API. "Weer vernieuwen"
on the planner fetches the forecasts at once; moving a block takes its
weather from the kept forecasts.

The location of a site is the centre of the roof project's satellite image;
without one, the municipality of the site, looked up once with Open-Meteo's
geocoding and kept on the roof project.
"""
import logging
from datetime import datetime, time, timedelta

import pytz
import requests

from odoo import _, api, fields, models
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_DAYS = 16
TIMEOUT = 20
# Locations per call to the forecast API.
BATCH_SIZE = 50
DAILY = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_gusts_10m_max",
)
DEFAULT_TZ = "Europe/Brussels"

# WMO weather codes as Open-Meteo returns them: icon and label.
WEATHER_CODES = [
    ((0,), "☀️", "Zonnig"),
    ((1, 2), "🌤️", "Licht bewolkt"),
    ((3,), "☁️", "Bewolkt"),
    ((45, 48), "🌫️", "Mist"),
    (tuple(range(51, 58)), "🌦️", "Motregen"),
    (tuple(range(61, 68)), "🌧️", "Regen"),
    (tuple(range(71, 78)), "🌨️", "Sneeuw"),
    ((80, 81, 82), "🌦️", "Buien"),
    ((85, 86), "🌨️", "Sneeuwbuien"),
    ((95, 96, 99), "⛈️", "Onweer"),
]
SNOW_CODES = set(range(71, 78)) | {85, 86}
THUNDER_CODES = {95, 96, 99}

# When a day is no good for roofing work.
RAIN_MM = 1.0
RAIN_PROBABILITY = 60
GUSTS_KMH = 50.0
# EPDM glues and primers need at least about 5 °C.
MIN_TEMPERATURE = 5.0


def weather_label(code):
    """(icon, label) of a WMO weather code."""
    for codes, icon, label in WEATHER_CODES:
        if code in codes:
            return icon, label
    return "", ""


def round_location(latitude, longitude):
    """Forecasts are kept per 0.01° (about 1 km): sites close together
    share one."""
    return round(latitude, 2), round(longitude, 2)


class TectoraWeatherForecast(models.Model):
    """The forecast of one day at one location, as last fetched."""

    _name = "tectora.weather.forecast"
    _description = "Weersvoorspelling (per locatie en dag)"
    _order = "date, latitude, longitude"

    latitude = fields.Float(digits=(10, 2), required=True, index=True)
    longitude = fields.Float(digits=(10, 2), required=True, index=True)
    date = fields.Date(required=True, index=True)
    weather_code = fields.Integer(string="Weercode (WMO)")
    temperature_max = fields.Float(string="Max. temperatuur (°C)")
    temperature_min = fields.Float(string="Min. temperatuur (°C)")
    precipitation = fields.Float(string="Neerslag (mm)")
    precipitation_probability = fields.Integer(string="Kans op neerslag (%)")
    wind_gusts = fields.Float(string="Windstoten (km/u)")
    fetched_at = fields.Datetime(string="Opgehaald op")

    _location_date_unique = models.Constraint(
        "UNIQUE(latitude, longitude, date)",
        "Eén voorspelling per locatie en dag.",
    )

    def _icon(self):
        return weather_label(self.weather_code)[0]

    def _warnings(self):
        """Why this day is no good for roofing work (empty when it is)."""
        self.ensure_one()
        warnings = []
        if self.weather_code in THUNDER_CODES:
            warnings.append(_("onweer"))
        if self.weather_code in SNOW_CODES:
            warnings.append(_("sneeuw"))
        if self.precipitation >= RAIN_MM or self.precipitation_probability >= RAIN_PROBABILITY:
            warnings.append(_("regen"))
        if self.wind_gusts >= GUSTS_KMH:
            warnings.append(_("windstoten %s km/u", round(self.wind_gusts)))
        if self.temperature_min < MIN_TEMPERATURE:
            warnings.append(_("koud (%s °C)", round(self.temperature_min)))
        return warnings

    def _summary(self):
        """"🌧️ 8–14 °C · 6 mm (80%) · wind 45 km/u"."""
        self.ensure_one()
        parts = [
            "%s %s–%s °C" % (
                self._icon(), round(self.temperature_min), round(self.temperature_max)
            ),
        ]
        if self.precipitation or self.precipitation_probability:
            parts.append("%s mm (%s%%)" % (
                ("%.1f" % self.precipitation).replace(".", ","),
                self.precipitation_probability,
            ))
        parts.append(_("wind %s km/u", round(self.wind_gusts)))
        return " · ".join(parts)

    @api.model
    def _fetch(self, locations):
        """Fetches and keeps the forecast of the next FORECAST_DAYS days for
        the (rounded) locations; returns how many locations were updated.
        A failing call is logged and leaves the kept forecasts as they are."""
        # Kept for everyone: any planner may refresh, readers only read.
        self = self.sudo()
        locations = sorted(set(locations))
        updated = 0
        now = fields.Datetime.now()
        for start in range(0, len(locations), BATCH_SIZE):
            batch = locations[start:start + BATCH_SIZE]
            try:
                response = requests.get(FORECAST_URL, params={
                    "latitude": ",".join("%.2f" % lat for lat, _lng in batch),
                    "longitude": ",".join("%.2f" % lng for _lat, lng in batch),
                    "daily": ",".join(DAILY),
                    "timezone": DEFAULT_TZ,
                    "forecast_days": FORECAST_DAYS,
                    "wind_speed_unit": "kmh",
                }, timeout=TIMEOUT)
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError) as error:
                _logger.warning("Open-Meteo: voorspelling niet opgehaald: %s", error)
                continue
            # One location gives an object, several a list in the same order.
            results = payload if isinstance(payload, list) else [payload]
            for (latitude, longitude), result in zip(batch, results):
                daily = (result or {}).get("daily") or {}
                days = daily.get("time") or []
                existing = {
                    forecast.date: forecast
                    for forecast in self.search([
                        ("latitude", "=", latitude), ("longitude", "=", longitude),
                        ("date", "in", days),
                    ])
                }
                for index, day in enumerate(days):
                    def value(key, default=0.0):
                        values = daily.get(key) or []
                        found = values[index] if index < len(values) else None
                        return default if found is None else found

                    date = fields.Date.to_date(day)
                    values = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "date": date,
                        "weather_code": int(value("weather_code", 0)),
                        "temperature_max": value("temperature_2m_max"),
                        "temperature_min": value("temperature_2m_min"),
                        "precipitation": value("precipitation_sum"),
                        "precipitation_probability": int(value("precipitation_probability_max", 0)),
                        "wind_gusts": value("wind_gusts_10m_max"),
                        "fetched_at": now,
                    }
                    if date in existing:
                        existing[date].write(values)
                    else:
                        self.create(values)
                updated += 1
        # Days gone by are of no use any more.
        self.search([("date", "<", fields.Date.context_today(self) - timedelta(days=7))]).unlink()
        return updated


class TectoraRoofProject(models.Model):
    _inherit = "tectora.roof.project"

    weather_latitude = fields.Float(
        string="Breedtegraad (weer)", digits=(10, 4), copy=False,
        help="Opgezocht uit de gemeente van de werf wanneer er geen satellietbeeld is.",
    )
    weather_longitude = fields.Float(string="Lengtegraad (weer)", digits=(10, 4), copy=False)

    def _tectora_weather_location(self, geocode=True):
        """(latitude, longitude) of the site for the forecast, rounded, or
        None: the centre of the satellite image, else the municipality of the
        site (looked up once and kept; only when `geocode`)."""
        self.ensure_one()
        if self.bg_lat or self.bg_lng:
            return round_location(self.bg_lat, self.bg_lng)
        if self.weather_latitude or self.weather_longitude:
            return round_location(self.weather_latitude, self.weather_longitude)
        if not geocode:
            return None
        city = self._site_city()
        if not city:
            return None
        try:
            response = requests.get(GEOCODE_URL, params={
                "name": city, "count": 1, "language": "nl", "countryCode": "BE",
            }, timeout=TIMEOUT)
            response.raise_for_status()
            results = response.json().get("results") or []
        except (requests.RequestException, ValueError) as error:
            _logger.warning("Open-Meteo: gemeente %s niet gevonden: %s", city, error)
            return None
        if not results:
            return None
        # Not a change of the site: nothing to push to the order.
        self.sudo().with_context(tectora_sync=True).write({
            "weather_latitude": results[0]["latitude"],
            "weather_longitude": results[0]["longitude"],
        })
        return round_location(results[0]["latitude"], results[0]["longitude"])


class TectoraRoofPlanning(models.Model):
    _inherit = "tectora.roof.planning"

    weather_icon = fields.Char(string="Weer", copy=False)
    weather_summary = fields.Char(
        string="Weersvoorspelling", copy=False,
        help="Het slechtste weer over de dagen van het werkblok (Open-Meteo).",
    )
    weather_days = fields.Text(string="Weer per dag", copy=False)
    weather_alert = fields.Boolean(
        string="Weerswaarschuwing", copy=False,
        help="Op minstens één dag regen, sneeuw, onweer, windstoten vanaf "
        "%s km/u of minder dan %s °C: niet geschikt voor dakwerken." % (
            round(GUSTS_KMH), round(MIN_TEMPERATURE)
        ),
    )
    weather_alert_reason = fields.Char(string="Waarom", copy=False)
    weather_updated = fields.Datetime(string="Voorspelling van", copy=False)

    @api.depends(
        "project_id.name", "project_id.address", "project_id.partner_id.name",
        "project_id.partner_id.city", "project_id.total_area",
        "project_id.project_type", "employee_ids", "weather_icon", "weather_alert",
    )
    def _compute_display_name(self):
        """The planner's label with the weather in front: "⚠️🌧️ Dhr. ..."."""
        super()._compute_display_name()
        for item in self:
            prefix = ("⚠️" if item.weather_alert else "") + (item.weather_icon or "")
            if prefix:
                item.display_name = "%s %s" % (prefix, item.display_name)

    # ------------------------------------------------------------- refreshing
    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items._tectora_update_weather()
        return items

    def write(self, vals):
        res = super().write(vals)
        if {"start_datetime", "end_datetime", "project_id"} & set(vals):
            self._tectora_update_weather()
        return res

    @api.model
    def _tectora_weather_blocks(self):
        """The work blocks the forecast reaches: not over yet and starting
        within FORECAST_DAYS days."""
        now = fields.Datetime.now()
        return self.search([
            ("end_datetime", ">=", now),
            ("start_datetime", "<=", now + timedelta(days=FORECAST_DAYS)),
        ])

    @api.model
    def _tectora_refresh_weather(self):
        """Fetches the forecasts of every site with a work block in the next
        FORECAST_DAYS days and updates those blocks; returns (blocks,
        locations fetched)."""
        blocks = self._tectora_weather_blocks()
        locations = set()
        for roof in blocks.project_id:
            location = roof._tectora_weather_location()
            if location:
                locations.add(location)
        fetched = self.env["tectora.weather.forecast"]._fetch(locations) if locations else 0
        blocks._tectora_update_weather()
        return blocks, fetched

    @api.model
    def _cron_tectora_refresh_weather(self):
        blocks, fetched = self._tectora_refresh_weather()
        _logger.info(
            "Open-Meteo: %s locaties opgehaald, %s werkblokken bijgewerkt", fetched, len(blocks)
        )

    @api.model
    def action_tectora_refresh_weather(self):
        """The planner's "Weer vernieuwen": fetch now, then reload."""
        blocks, fetched = self._tectora_refresh_weather()
        if blocks and not fetched:
            message = _("De weersvoorspelling kon niet opgehaald worden (Open-Meteo).")
            kind = "warning"
        else:
            message = _("Weer vernieuwd voor %(blocks)s werkblokken (%(sites)s locaties).",
                        blocks=len(blocks), sites=fetched)
            kind = "success"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": message,
                "type": kind,
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def _tectora_update_weather(self):
        """Takes each block's weather from the kept forecasts: the worst day
        of the block in its summary, every day in the detail."""
        Forecast = self.env["tectora.weather.forecast"]
        tz = pytz.timezone(self.env.user.tz or DEFAULT_TZ)
        now = fields.Datetime.now()
        for item in self:
            values = {
                "weather_icon": False, "weather_summary": False, "weather_days": False,
                "weather_alert": False, "weather_alert_reason": False, "weather_updated": False,
            }
            location = (
                item.project_id._tectora_weather_location(geocode=False)
                if item.project_id else None
            )
            if location and item.start_datetime and item.end_datetime and item.end_datetime >= now:
                first = pytz.utc.localize(item.start_datetime).astimezone(tz).date()
                last = pytz.utc.localize(item.end_datetime).astimezone(tz).date()
                forecasts = Forecast.search([
                    ("latitude", "=", location[0]), ("longitude", "=", location[1]),
                    ("date", ">=", max(first, now.date())), ("date", "<=", last),
                ])
                if forecasts:
                    values.update(item._tectora_weather_values(forecasts))
            changed = {
                key: value for key, value in values.items() if (item[key] or False) != value
            }
            if changed:
                # Directly on the record: no shifts to sync for the weather.
                super(TectoraRoofPlanning, item).write(changed)

    def _tectora_weather_values(self, forecasts):
        def badness(forecast):
            return (
                len(forecast._warnings()),
                forecast.precipitation_probability,
                forecast.precipitation,
                forecast.wind_gusts,
            )

        worst = max(forecasts, key=badness)
        reasons = []
        for forecast in forecasts:
            for reason in forecast._warnings():
                if reason.split(" ")[0] not in [r.split(" ")[0] for r in reasons]:
                    reasons.append(reason)
        days = "\n".join(
            "%s: %s%s" % (
                format_date(self.env, forecast.date, date_format="EEE d MMM"),
                forecast._summary(),
                " ⚠️ %s" % ", ".join(forecast._warnings()) if forecast._warnings() else "",
            )
            for forecast in forecasts.sorted("date")
        )
        return {
            "weather_icon": worst._icon(),
            "weather_summary": worst._summary(),
            "weather_days": days,
            "weather_alert": bool(reasons),
            "weather_alert_reason": ", ".join(reasons) or False,
            "weather_updated": max(forecasts.mapped("fetched_at")),
        }
