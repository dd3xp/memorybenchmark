"""Single allowlist for the three current web surfaces and their assets."""

WEB_ASSETS = {
    "/experiments/new": "watch.html",
    "/new-experiment.js": "new-experiment.js",
    "/new-experiment.css": "new-experiment.css",
    "/": "watch.html",
    "/watch": "watch.html",
    "/experiments": "watch.html",
    "/play": "field.html",
    "/easy20": "field.html",
    "/maps": "catalog.html",
}
for _name in (
    "site.css",
    "ui-state.js",
    "watch.css",
    "watch.js",
    "field.css",
    "field.js",
    "atlas-view.js",
    "catalog.js",
    "catalog.css",
    "select.js",
    "select.css",
    "cottage-icons.svg",
    "botanical-sprig.svg",
    "atlas-chinese.woff2",
    "atlas-serif.woff2",
    "atlas-sans.woff2",
    "font-license.txt",
    "long-lake-normal-terrain.svg",
    "forest-valley-terrain.svg",
    "cascade-lakes-terrain.svg",
    "volcanic-cone-terrain.svg",
    "fjord-peninsulas-terrain.svg",
    "steppe-corridors-terrain.svg",
    "andean-passes-terrain.svg",
    "sand-coast-terrain.svg",
    "boar-woodland-terrain.svg",
    "hill-country-terrain.svg",
    "rock-river-terrain.svg",
    "reservoir-plain-terrain.svg",
):
    WEB_ASSETS["/" + _name] = _name

CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".txt": "text/plain",
}

# Geographic atlas/play layers are distinct from frozen experiment backgrounds.
for _terrain in (
    "volcanic-cone",
    "forest-valley",
    "cascade-lakes",
    "long-lake-normal",
    "sand-coast",
    "boar-woodland",
    "hill-country",
    "rock-river",
    "reservoir-plain",
):
    _name = _terrain + "-geographic.svg"
    WEB_ASSETS["/" + _name] = _name

# Shared real-world atlas assets are exclusively human presentation.
for _name in (
    "world-atlas.js",
    "world-atlas.json",
    "world-overview.svg",
    "world-coast.svg",
    "world-physical.svg",
):
    WEB_ASSETS["/" + _name] = _name
for _terrain in (
    "volcanic-cone",
    "forest-valley",
    "cascade-lakes",
    "long-lake-normal",
    "sand-coast",
    "boar-woodland",
    "hill-country",
    "rock-river",
    "reservoir-plain",
    "fjord-peninsulas",
    "steppe-corridors",
    "andean-passes",
):
    WEB_ASSETS["/" + _terrain + "-world.svg"] = _terrain + "-world.svg"
CONTENT_TYPES[".json"] = "application/json"
for _terrain in (
    "volcanic-cone",
    "forest-valley",
    "cascade-lakes",
    "long-lake-normal",
    "sand-coast",
    "boar-woodland",
    "hill-country",
    "rock-river",
    "reservoir-plain",
):
    WEB_ASSETS["/" + _terrain + "-context.svg"] = _terrain + "-context.svg"
for _url, _name in list(WEB_ASSETS.items()):
    if _name in (
        "world-atlas.json",
        "world-overview.svg",
        "world-coast.svg",
        "world-physical.svg",
    ) or _name.endswith(("-world.svg", "-context.svg")):
        WEB_ASSETS[_url + ".gz"] = _name + ".gz"
CONTENT_TYPES[".gz"] = "application/gzip"
for _name in (
    "atlas-gpu.js",
    "maplibre-gl-csp.js",
    "maplibre-gl-csp-worker.js",
    "maplibre-gl.css",
    "maplibre-license.txt",
    "world-gpu.json",
):
    WEB_ASSETS["/" + _name] = _name
CONTENT_TYPES[".geojson"] = "application/geo+json"
# Only generated, content-addressed display geography is eligible for caching.
from pathlib import Path as _Path
import json as _json
import re as _re

_gpu_manifest = _Path(__file__).with_name("static") / "world-gpu.json"
if _gpu_manifest.is_file():
    _gpu = _json.loads(_gpu_manifest.read_text(encoding="utf-8"))
    _records = [_gpu["overview"], _gpu["coast"], _gpu["physical"]] + [
        v for r in _gpu["regions"].values() for v in r.values()
    ]
    for _record in _records:
        _url = _record["url"]
        if not _re.fullmatch(r"/atlas-geo-[0-9a-f]{16}\.geojson", _url):
            raise ValueError("Invalid display geography filename")
        WEB_ASSETS[_url] = _url[1:]
