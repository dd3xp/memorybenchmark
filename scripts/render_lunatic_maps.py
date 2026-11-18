"""Refresh the public cartography for one reviewed Lunatic landscape."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.map_catalog import station_design
from scripts.build_world_atlas import design_fingerprint, local_projection, regional_svg
from scripts.build_world_gpu import compile_asset
from scripts.lunatic_geography import THEMES, geography
from scripts.lunatic_geography.whole_region_render import complete, terrain


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "memorybenchmark/static"


def write_atlas_asset(name, body):
    path = STATIC / name
    path.write_bytes(body)
    path.with_name(path.name + ".gz").write_bytes(gzip.compress(body, 9, mtime=0))


def render(theme):
    map_id = f"{theme}-lunatic"
    path = station_design(map_id)
    design = json.loads(path.read_bytes())
    public = design["public"]
    geo = geography(theme)
    locations = public["locations"]
    if public["edges"] != geo["edges"] or {
        key: (place["x"], place["y"]) for key, place in locations.items()
    } != {key: (place["x"], place["y"]) for key, place in geo["locations"].items()}:
        raise ValueError("Reproject changed geography before reusing its atlas extent")

    title = public["name"]
    terrain_name = f"{public['terrain']}-terrain.svg"
    terrain_path = STATIC / terrain_name
    terrain_bytes = (terrain(geo, title, show_processing_regions=False) + "\n").encode(
        "utf-8"
    )
    terrain_path.write_bytes(terrain_bytes)
    figure = ROOT / "docs/assets/lunatic-maps" / f"{theme}-recall.svg"
    figure.write_bytes(
        (
            complete(
                {**geo, "locations": locations}, title, show_processing_regions=False
            )
            + "\n"
        ).encode("utf-8")
    )

    atlas = json.loads((STATIC / "world-atlas.json").read_bytes())
    region = next(row for row in atlas["regions"] if row["id"] == map_id)
    projected = region["map"]["locations"]
    if (
        region["map"]["edges"] != public["edges"]
        or projected.keys() != locations.keys()
    ):
        raise ValueError("The selected graph does not match the atlas geometry")
    convert, _ = local_projection(region["geographic_bounds"], public["view_box"])
    world_name = region["terrain_asset"].lstrip("/")
    write_atlas_asset(
        world_name,
        regional_svg(terrain_path, convert, region["view_box"], lunatic=True).encode(
            "utf-8"
        ),
    )
    region["source_asset_sha256"] = sha256(terrain_bytes).hexdigest()
    region["design_sha256"] = design_fingerprint(path)
    region["map"]["processing_regions"] = {}
    region["map"]["locations"] = {
        key: {
            **place,
            **{
                field: projected[key][field]
                for field in ("x", "y", "longitude", "latitude")
            },
        }
        for key, place in locations.items()
    }
    write_atlas_asset(
        "world-atlas.json",
        json.dumps(atlas, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )
    gpu_path = STATIC / "world-gpu.json"
    gpu = json.loads(gpu_path.read_bytes())
    gpu["regions"][map_id]["detail"] = compile_asset(
        region["terrain_asset"], region.get("terrain_view_box")
    )
    gpu_path.write_bytes(json.dumps(gpu, separators=(",", ":")).encode("utf-8"))
    print(f"Rendered {map_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", choices=THEMES, required=True)
    render(parser.parse_args().map)


if __name__ == "__main__":
    main()
