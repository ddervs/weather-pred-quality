"""Small geo helpers: geohash decode (Met Office stations are keyed by geohash) and haversine.

Hand-rolled on purpose (same minimal-deps stance as skipping `scores`/MAPIE): both
algorithms are frozen closed forms with nothing upstream to track, the PyPI geohash
packages are largely unmaintained, and spherical haversine is within ~0.3 % of a
WGS84 geodesic — irrelevant for ranking nearest gauges. Only the registry builder
uses these. Reference-vector tests: tests/test_geo.py.
"""

import math

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash_decode(geohash: str) -> tuple[float, float]:
    """Decode a geohash to its cell-centre (lat, lon)."""
    lat_lo, lat_hi = -90.0, 90.0
    lon_lo, lon_hi = -180.0, 180.0
    is_lon = True
    for char in geohash:
        bits = _BASE32.index(char)
        for shift in range(4, -1, -1):
            bit = (bits >> shift) & 1
            if is_lon:
                mid = (lon_lo + lon_hi) / 2
                if bit:
                    lon_lo = mid
                else:
                    lon_hi = mid
            else:
                mid = (lat_lo + lat_hi) / 2
                if bit:
                    lat_lo = mid
                else:
                    lat_hi = mid
            is_lon = not is_lon
    return (lat_lo + lat_hi) / 2, (lon_lo + lon_hi) / 2


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
