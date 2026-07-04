"""Shared UK probe locations, spread across regions/terrain, with nearest METAR station.

Deliberately small (10 sites) for probing. A production collector would scale to ~50.
"""

LOCATIONS = [
    # name, lat, lon, region, nearest METAR ICAO
    ("London", 51.5072, -0.1276, "London", "EGLL"),
    ("Birmingham", 52.4862, -1.8904, "Midlands", "EGBB"),
    ("Manchester", 53.4808, -2.2426, "North West", "EGCC"),
    ("Newcastle", 54.9783, -1.6178, "North East", "EGNT"),
    ("Edinburgh", 55.9533, -3.1883, "Scotland", "EGPH"),
    ("Fort William", 56.8198, -5.1052, "Scottish Highlands", "EGPO"),  # nearest-ish: Stornoway; sparse METAR coverage in Highlands
    ("Belfast", 54.5973, -5.9301, "Northern Ireland", "EGAA"),
    ("Cardiff", 51.4816, -3.1791, "Wales", "EGFF"),
    ("Norwich", 52.6309, 1.2974, "East Anglia", "EGSH"),
    ("Exeter", 50.7260, -3.5275, "South West", "EGTE"),
]

USER_AGENT = (
    "weather-pred-quality/0.1 (research probe; https://github.com/ddervs; ddervs@googlemail.com)"
)
