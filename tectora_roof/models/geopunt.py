# -*- coding: utf-8 -*-
"""Geopunt, the geographic web services of Digitaal Vlaanderen (no API key).

* Geolocation API: an address in Flanders to its official address and its
  coordinates (WGS84 and Lambert 72).
* CaPaKey API: the cadastral parcel at a point.

Both only know Flanders (and, for addresses, not Brussels or Wallonia): the
callers fall back on another service or do without when nothing is found.
Nothing here raises: a failed call is logged and answers None.
"""
import logging

import requests

_logger = logging.getLogger(__name__)

LOCATION_URL = "https://geo.api.vlaanderen.be/geolocation/v4/Location"
PARCEL_URL = "https://geo.api.vlaanderen.be/capakey/v2/parcel"
LAMBERT72_SRS = 31370
TIMEOUT = 15


def locate(address):
    """The best match of an address in Flanders, or None::

        {"lat": 51.05, "lng": 3.72, "x": 104659.2, "y": 193880.89,
         "formatted": "Veldstraat 10, 9000 Gent", "type": "..."}

    x and y are Lambert 72 (EPSG:31370), what the CaPaKey API asks.
    """
    address = (address or "").strip()
    if not address:
        return None
    try:
        response = requests.get(
            LOCATION_URL, params={"q": address, "c": 1}, timeout=TIMEOUT
        )
        response.raise_for_status()
        results = response.json().get("LocationResult") or []
        if not results:
            return None
        result = results[0]
        point = result["Location"]
        return {
            "lat": float(point["Lat_WGS84"]),
            "lng": float(point["Lon_WGS84"]),
            "x": float(point["X_Lambert72"]),
            "y": float(point["Y_Lambert72"]),
            "formatted": result.get("FormattedAddress") or address,
            "type": result.get("LocationType") or "",
        }
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as error:
        _logger.warning("Geopunt: adres %s niet opgezocht: %s", address, error)
        return None


def parcel(x, y):
    """The cadastral parcel at a Lambert 72 point, or None::

        {"capakey": "44803C0113/00D000", "department": "GENT 3 AFD",
         "municipality": "Gent"}
    """
    try:
        response = requests.get(
            PARCEL_URL,
            params={"x": x, "y": y, "srs": LAMBERT72_SRS},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("capakey"):
            return None
        return {
            "capakey": data["capakey"],
            "department": data.get("departmentName") or "",
            "municipality": data.get("municipalityName") or "",
        }
    except (requests.RequestException, ValueError, TypeError, AttributeError) as error:
        _logger.warning("Geopunt: geen perceel op (%s, %s): %s", x, y, error)
        return None
