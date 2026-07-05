"""Pin wpq.geo against independent reference values.

These two functions are hand-rolled (see wpq/geo.py docstring for why). A wrong
geohash decode would silently corrupt every station coordinate — and therefore
every gauge/METAR pairing — so the reference vectors here must never drift.

Run: uv run pytest
"""

import json

from wpq.config import STATIONS_FILE
from wpq.geo import geohash_decode, haversine_km


def test_geohash_decode_spec_example():
    # canonical example from the original geohash spec
    lat, lon = geohash_decode("ezs42")
    assert abs(lat - 42.605) < 1e-3
    assert abs(lon - -5.603) < 1e-3


def test_geohash_decode_high_precision_vector():
    # Wikipedia's worked example: 57.64911, 10.40744 at 11 characters
    lat, lon = geohash_decode("u4pruydqqvj")
    assert abs(lat - 57.64911) < 1e-5
    assert abs(lon - 10.40744) < 1e-5


def test_geohash_decode_matches_registry():
    # stations.json coordinates were produced by this decode (4 dp); if this
    # fails, the code no longer reproduces the coordinates the project runs on
    stations = json.loads(STATIONS_FILE.read_text())["stations"]
    for s in stations:
        lat, lon = geohash_decode(s["id"])
        assert round(lat, 4) == s["lat"], s["id"]
        assert round(lon, 4) == s["lon"], s["id"]


def test_haversine_known_distance():
    # London -> Edinburgh great-circle distance is ~534 km
    d = haversine_km(51.5074, -0.1278, 55.9533, -3.1883)
    assert abs(d - 534) < 1.5


def test_haversine_basics():
    assert haversine_km(55.9, -3.3, 55.9, -3.3) == 0.0
    assert haversine_km(51.5, -0.1, 55.9, -3.3) == haversine_km(55.9, -3.3, 51.5, -0.1)
