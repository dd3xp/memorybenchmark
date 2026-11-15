"""Author map-specific material sets; configured games remain self-contained."""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path


CATALOG_PATH = Path(__file__).parent / "data" / "material_catalog.json"
SELECTION_PROTOCOL = "easy-materials-6-common-2-special-1"


@lru_cache(maxsize=1)
def _catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load_material_catalog():
    return deepcopy(_catalog())


def validate_material_selection(selection, kinds, *, difficulty):
    """Validate the embedded selection without loading a mutable live catalog.

    Historical snapshots and third-party map configurations can replay using
    their own selected material IDs/names after the authoring catalog evolves.
    This metadata does not define station capability groups.
    """
    if isinstance(selection, dict) and selection.get('protocol') == 'four-exposure-materials-v1':
        expected = {'Easy': (8, 0, 0), 'Normal': (8, 4, 0),
                    'Hard': (8, 0, 4), 'Lunatic': (8, 4, 4)}.get(difficulty)
        groups = [selection.get(k, []) for k in ('geographic', 'animal', 'human')]
        if (expected is None or any(not isinstance(v, list) for v in groups)
                or tuple(map(len, groups)) != expected):
            raise ValueError('Invalid four-exposure material categories for difficulty')
        chosen = sum(groups, [])
        if (any(not isinstance(k, str) or not k for k in chosen)
                or len(set(chosen)) != sum(expected) or set(chosen) != set(kinds)):
            raise ValueError('Selected materials must exactly match the public catalog')
        return
    if isinstance(selection, dict) and selection.get('protocol') in ('difficulty-materials-v2','lunatic-materials-1'):
        expected_difficulty='Lunatic' if selection['protocol']=='lunatic-materials-1' else 'Hard'
        categories = [selection.get(k, []) for k in ('geographic', 'animal', 'human')]
        if (difficulty != expected_difficulty or any(not isinstance(v, list) for v in categories)
                or list(map(len, categories)) != [8, 4, 4]):
            raise ValueError(expected_difficulty+' requires eight geographic, four animal and four human materials')
        chosen = sum(categories, [])
        if any(not isinstance(k, str) or not k for k in chosen) or len(set(chosen)) != 16 or set(chosen) != set(kinds):
            raise ValueError('The sixteen selected Hard materials must match the public catalog')
        return
    if isinstance(selection, dict) and selection.get("protocol") == "difficulty-materials-v1":
        geographic, animal = selection.get("geographic", []), selection.get("animal", [])
        expected = 8 if difficulty == "Easy" else 12 if difficulty == "Normal" else None
        chosen = geographic + animal
        if expected is None or len(geographic) != 8 or len(animal) != expected - 8 or len(set(chosen)) != expected or set(chosen) != set(kinds):
            raise ValueError("Difficulty material counts or categories are inconsistent")
        if any(not isinstance(k, str) or not k for k in chosen):
            raise ValueError("Material IDs must be nonempty strings")
        return
    if not isinstance(selection, dict) or selection.get("protocol") != SELECTION_PROTOCOL:
        raise ValueError("Unknown material selection protocol")
    if difficulty != "Easy":
        raise ValueError("The six-common/two-special material protocol requires Easy difficulty")
    common, special = selection.get("common"), selection.get("special")
    if not isinstance(common, list) or not isinstance(special, list) or len(common) != 6 or len(special) != 2:
        raise ValueError("Each Easy map requires six common and two special materials")
    chosen = common + special
    if any(not isinstance(kind, str) or not kind for kind in chosen) or len(set(chosen)) != 8:
        raise ValueError("The eight selected material IDs must be distinct")
    if set(chosen) != set(kinds):
        raise ValueError("Selected materials must exactly match this map's public kinds")
    if not isinstance(selection.get("theme"), str) or not selection["theme"]:
        raise ValueError("Map-specific materials require a theme")


def select_easy_materials(theme, common, special):
    """Select once when authoring a map, with no runtime sampling."""
    catalog = _catalog()
    if theme not in catalog["themes"]:
        raise ValueError("Unknown material theme")
    themed = catalog["themes"][theme]["materials"]
    if any(kind not in catalog["common"] for kind in common):
        raise ValueError("Common materials must come from the common catalog")
    if any(kind not in themed for kind in special):
        raise ValueError("Special materials must belong to this map's theme")
    chosen = list(common) + list(special)
    kinds = {kind: (catalog["common"].get(kind) or themed[kind])["name"] for kind in chosen}
    selection = {
        "protocol": SELECTION_PROTOCOL,
        "catalog_version": catalog["version"],
        "catalog_sha256": sha256(json.dumps(catalog, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")).encode("utf-8")).hexdigest(),
        "theme": theme, "common": list(common), "special": list(special),
    }
    validate_material_selection(selection, kinds, difficulty="Easy")
    return kinds, selection


def easy_material_preset(theme):
    catalog = _catalog()
    if theme not in catalog["easy_presets"]:
        raise ValueError("Unknown Easy material preset")
    preset = catalog["easy_presets"][theme]
    return select_easy_materials(theme, preset["common"], preset["special"])


def field_material_preset(theme):
    """Versioned geography/animal catalog; historical Easy authoring is frozen."""
    path = CATALOG_PATH.with_name('material_catalog_v3.json')
    catalog = json.loads(path.read_text(encoding='utf-8'))
    preset = catalog['presets'][theme]
    geographic, animal = preset['geographic'], preset.get('animal', [])
    kinds = {k: catalog['materials'][k]['name'] for k in geographic + animal}
    selection = {'protocol': 'difficulty-materials-v1', 'catalog_version': catalog['version'],
        'catalog_sha256': sha256(path.read_bytes()).hexdigest(), 'theme': theme,
        'geographic': geographic, 'animal': animal}
    validate_material_selection(selection, kinds, difficulty='Normal' if animal else 'Easy')
    return kinds, selection
