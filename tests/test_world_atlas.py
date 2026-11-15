"""World projection is a reusable human display, never a scientific mutation."""

from hashlib import sha256
from math import atan, degrees, exp, isclose, pi
import unittest
import tempfile
from pathlib import Path
import json
import xml.etree.ElementTree as ET

from memorybenchmark.map_catalog import MAPS, station_design
from scripts.build_world_atlas import project, design_fingerprint

STATIC = Path(__file__).resolve().parents[1] / "memorybenchmark/static"


def atlas():
    return json.loads((STATIC / "world-atlas.json").read_text(encoding="utf-8"))


class WorldAtlasTests(unittest.TestCase):
    def test_display_fingerprint_matches_both_checkout_line_endings(self):
        with tempfile.TemporaryDirectory() as folder:
            lf = Path(folder) / "lf.json"
            crlf = Path(folder) / "crlf.json"
            lf.write_bytes(b'{\n  "tasks": 36\n}\n')
            crlf.write_bytes(lf.read_bytes().replace(b"\n", b"\r\n"))
            self.assertNotEqual(
                sha256(lf.read_bytes()).digest(), sha256(crlf.read_bytes()).digest()
            )
            self.assertEqual(design_fingerprint(lf), design_fingerprint(crlf))

    def test_all_twelve_regions_share_coordinates_and_preserve_their_game_graph(self):
        world = atlas()
        self.assertEqual(world["design_sha256_encoding"], "utf-8-lf")
        assert {r["id"] for r in world["regions"]} == set(MAPS)
        assert (
            world["projection"] == "EPSG:3857"
            and world["scientific_state_changed"] is False
        )
        assert sum(len(r["map"]["locations"]) for r in world["regions"]) == 1473
        for region in world["regions"]:
            design = json.loads(
                station_design(region["id"]).read_text(encoding="utf-8")
            )
            assert (
                region["design_sha256"]
                == sha256(
                    station_design(region["id"]).read_bytes().replace(b"\r\n", b"\n")
                ).hexdigest()
            )
            assert region["map"]["edges"] == design["public"]["edges"]
            assert set(region["map"]["locations"]) == set(design["public"]["locations"])
            assert region["task_count"] == len(design["tasks"])
            for n in region["map"]["locations"].values():
                x, y = project(n["longitude"], n["latitude"])
                assert abs(x - n["x"]) < 0.0002 and abs(y - n["y"]) < 0.0005
            for a, b, _ in region["map"]["edges"]:
                points = region["map"]["edge_paths"]["|".join(sorted((a, b)))]
                for node in (a, b):
                    n = region["map"]["locations"][node]
                    assert [n["x"], n["y"]] in (points[0], points[-1])

    def test_world_detail_assets_reuse_existing_atlas_and_exclude_private_answers(self):
        value = atlas()
        assert value["reference"]["source"] == "Natural Earth 5.1.2"
        for region in value["regions"]:
            source = STATIC / region["source_asset"].lstrip("/")
            assert (
                sha256(source.read_bytes()).hexdigest() == region["source_asset_sha256"]
            )
            detail = STATIC / region["terrain_asset"].lstrip("/")
            root = ET.parse(detail).getroot()
            assert root.get("data-world-projection") == "EPSG:3857"
            assert len(list(root.iter())) > 5
            assert all(
                isclose(a, b, abs_tol=0.001)
                for a, b in zip(
                    map(float, root.get("viewBox").split()),
                    region.get("terrain_view_box", region["view_box"]),
                )
            )
        serial = json.dumps(value)
        assert (
            "private_station_capabilities" not in serial
            and "private_worlds" not in serial
        )

    def test_world_geography_has_known_global_control_points(self):
        assert project(0, 0) == [180000, 180000]
        x, y = project(104, 13.4)
        assert 283999 < x < 284001 and y < 180000
        assert (
            abs(degrees(2 * atan(exp((180 - y / 1000) * pi / 180)) - pi / 2) - 13.4)
            < 1e-7
        )

    def test_study_island_survives_both_global_levels_without_local_detail(self):
        import re
        from shapely.geometry import Polygon, Point

        ns = {"s": "http://www.w3.org/2000/svg"}
        paths = []
        for filename in ("world-overview.svg", "world-coast.svg"):
            root = ET.parse(STATIC / filename).getroot()
            coast = root.find('.//s:path[@data-feature="kgari-coastline"]', ns)
            assert coast is not None
            numbers = list(map(float, re.findall(r"[-+]?\d*\.?\d+", coast.get("d"))))
            island = Polygon(list(zip(numbers[::2], numbers[1::2])))
            assert island.covers(Point(*project(153.08, -25.45)))
            assert (
                island.bounds[3] - island.bounds[1] > 900
            )  # Whole island, not game crop.
            paths.append(coast.get("d"))
        assert paths[0] == paths[1]

    def test_context_has_real_surroundings_and_no_opaque_rectangular_background(self):
        world = atlas()
        assert world["layers"]["palette"] == {"land": "#eee8d5", "water": "#a9c7ca"}
        small = [r for r in world["regions"] if not r["id"].endswith("lunatic")]
        assert len(small) == 9 and all(r.get("context") for r in small)
        for region in world["regions"]:
            root = ET.parse(STATIC / region["terrain_asset"].lstrip("/")).getroot()
            assert not any(e.tag.endswith("rect") for e in list(root))
        for region in small:
            context = region["context"]
            a, b, w, h = context["view_box"]
            x, y, rw, rh = region["view_box"]
            assert a < x and b < y and a + w > x + rw and b + h > y + rh
            assert w > rw * 1.6 and h > rh * 1.6 and context["features"] > 20
            root = ET.parse(STATIC / context["asset"].lstrip("/")).getroot()
            assert not any(e.tag.endswith("rect") for e in list(root))

    def test_precompressed_geography_is_byte_exact_and_allowlisted(self):
        import gzip
        from memorybenchmark.web_assets import WEB_ASSETS

        world = atlas()
        assets = [
            world["world_asset"],
            world["layers"]["coast"]["asset"],
            world["layers"]["physical"]["asset"],
            "/world-atlas.json",
        ]
        assets += [r["terrain_asset"] for r in world["regions"]]
        assets += [r["context"]["asset"] for r in world["regions"] if r.get("context")]
        for asset in assets:
            assert asset + ".gz" in WEB_ASSETS
            assert (
                gzip.decompress((STATIC / (asset.lstrip("/") + ".gz")).read_bytes())
                == (STATIC / asset.lstrip("/")).read_bytes()
            )
