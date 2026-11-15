"""Historical v1 reproducibility builders. Current map CLI dispatches to v2."""
import json
from pathlib import Path

from memorybenchmark.materials import easy_material_preset
from scripts.easy_map_common import assemble


ROOT = Path(__file__).resolve().parents[1]


def build_forest():
    kinds, selection = easy_material_preset('forest')
    core = {
        'C': ('溪口营地', 1000, 1510),
        'W0': ('西岸入口', 760, 1330), 'W1': ('苔杉岔口', 720, 1070),
        'W2': ('蕨坡岔口', 690, 790), 'W3': ('古木岔口', 760, 520), 'W4': ('上溪西岔', 890, 260),
        'E0': ('东岸入口', 1280, 1330), 'E1': ('浅湾岔口', 1240, 1070),
        'E2': ('碎石岔口', 1280, 790), 'E3': ('林冠岔口', 1260, 520), 'E4': ('上溪东岔', 1220, 260),
        'B1': ('下溪桥', 980, 1070), 'B3': ('中溪桥', 1010, 520), 'B4': ('上溪桥', 1055, 260),
    }
    roads = [('C', 'W0', 1), ('C', 'E0', 2)]
    roads += [(f'W{i}', f'W{i+1}', 2) for i in range(4)]
    roads += [(f'E{i}', f'E{i+1}', w) for i, w in enumerate((2, 3, 2, 2))]
    roads += [(f'W{i}', b, 1) for i, b in ((1, 'B1'), (3, 'B3'), (4, 'B4'))]
    roads += [(b, f'E{i}', 1) for i, b in ((1, 'B1'), (3, 'B3'), (4, 'B4'))]
    surveys = {
        'P': ('苔杉测点', 'W1', 820, 980), 'Q': ('浅湾测点', 'E1', 1140, 1160),
        'R': ('蕨坡测点', 'W2', 790, 720), 'S': ('碎石测点', 'E2', 1170, 860),
        'U': ('古木测点', 'W3', 860, 440), 'V': ('林冠测点', 'E3', 1150, 600),
        'X': ('上溪石滩', 'W4', 970, 180), 'Y': ('林缘测点', 'E4', 1320, 170),
    }
    stations = {
        'A1': ('W1', 410, 1100, 2), 'A2': ('E3', 1560, 510, 2),
        'B1': ('E1', 1570, 1120, 3), 'B2': ('W3', 400, 530, 3),
        'C1': ('W0', 420, 1390, 2), 'C2': ('E4', 1560, 220, 2),
        'D1': ('E0', 1610, 1400, 3), 'D2': ('W4', 570, 220, 3),
        'E1': ('W2', 370, 830, 2), 'E2': ('E2', 1580, 830, 2),
        'F1': ('E1', 1530, 1000, 3), 'F2': ('W3', 470, 400, 3),
        'G1': ('W2', 430, 700, 2), 'G2': ('E4', 1500, 350, 2),
        'H1': ('E2', 1640, 690, 3), 'H2': ('W4', 650, 110, 3),
    }
    # Road junctions and stations must have globally distinct IDs.
    rename = {'B1': 'J1', 'B3': 'J3', 'B4': 'J4', 'E1': 'R1', 'E2': 'R2', 'E3': 'R3', 'E4': 'R4', 'E0': 'R0'}
    core = {rename.get(k, k): v for k, v in core.items()}
    roads = [(rename.get(a, a), rename.get(b, b), w) for a, b, w in roads]
    surveys = {k: (name, rename.get(fork, fork), x, y) for k, (name, fork, x, y) in surveys.items()}
    stations = {k: (rename.get(fork, fork), x, y, w) for k, (fork, x, y, w) in stations.items()}
    return assemble(version='easy-02-v1.0', name='雾杉溪谷', terrain='forest-valley',
        core=core, roads=roads, surveys=surveys, stations=stations, kinds=kinds, selection=selection,
        fixture={'A': 'soil', 'B': 'redwood_community', 'C': 'bearing', 'D': 'vegetation',
                 'E': 'profile', 'F': 'salmon_habitat', 'G': 'drainage', 'H': 'elevation'},
        regions=[{'name': '下溪', 'x': 900, 'y': 1400}, {'name': '蕨坡', 'x': 440, 'y': 940}, {'name': '古木林', 'x': 1180, 'y': 380}],
        provenance={'inspiration': 'Muir Woods National Monument: lower Redwood Creek valley and bridge-linked loops.',
            'scope': 'A schematic cropped valley, fictional sites, roads, distances and station assignments; not a navigation map.',
            'sources': ['https://www.nps.gov/muwo/planyourvisit/hike.htm', 'https://www.nps.gov/im/sfan/muwo.htm'],
            'private_boundary': 'Real names and source URLs remain outside all agent observations.'})


def build_cascade():
    kinds, selection = easy_material_preset('cascade')
    core = {'C': ('高岸营地', 1850, 160)}
    necks = [(1590, 300), (1320, 610), (1030, 910), (740, 1210), (460, 1480)]
    for i, (x, y) in enumerate(necks): core[f'N{i}'] = (f'第 {i+1} 湖口', x, y)
    for i, (left, right) in enumerate((((1260, 300), (1560, 600)), ((970, 610), (1300, 920)),
                                      ((680, 910), (1010, 1230)), ((390, 1200), (730, 1500)))):
        core[f'L{i}'] = (f'第 {i+1} 湖西岸', *left)
        core[f'R{i}'] = (f'第 {i+1} 湖东岸', *right)
    roads = [('C', 'N0', 1)]
    for i in range(4):
        roads += [(f'N{i}', f'L{i}', 2), (f'L{i}', f'N{i+1}', 2),
                  (f'N{i}', f'R{i}', 1 if i % 2 == 0 else 2), (f'R{i}', f'N{i+1}', 3)]
    surveys = {
        'P': ('上湖浅滩', 'L0', 1160, 230), 'Q': ('上湖石岸', 'R0', 1670, 690),
        'R': ('青潭测点', 'L1', 860, 540), 'S': ('青潭跌水', 'R1', 1400, 1010),
        'U': ('白阶测点', 'L2', 570, 840), 'V': ('白阶石滩', 'R2', 1120, 1320),
        'X': ('下湖苔岸', 'L3', 270, 1130), 'Y': ('末端跌水', 'R3', 840, 1580),
    }
    stations = {
        'A1': ('L0', 960, 140, 2), 'A2': ('R2', 1340, 1190, 2),
        'B1': ('R0', 1900, 510, 3), 'B2': ('L2', 360, 760, 2),
        'C1': ('L1', 650, 440, 2), 'C2': ('R2', 1290, 1110, 2),
        'D1': ('R1', 1610, 850, 3), 'D2': ('L2', 270, 1060, 2),
        'E1': ('L0', 940, 300, 2), 'E2': ('R2', 1290, 1390, 2),
        'F1': ('R0', 1860, 700, 3), 'F2': ('L2', 390, 950, 3),
        'G1': ('L1', 650, 650, 2), 'G2': ('R3', 1010, 1690, 2),
        'H1': ('R1', 1600, 1040, 3), 'H2': ('L3', 130, 1170, 3),
    }
    return assemble(version='easy-03-v1.0', name='石阶湖群', terrain='cascade-lakes',
        core=core, roads=roads, surveys=surveys, stations=stations, kinds=kinds, selection=selection,
        fixture={'A': 'water_quality', 'B': 'tufa_deposit', 'C': 'bathymetry', 'D': 'shore',
                 'E': 'elevation', 'F': 'sediment', 'G': 'lithology', 'H': 'waterfall_section'},
        regions=[{'name': '上湖', 'x': 1600, 'y': 350}, {'name': '青潭', 'x': 1310, 'y': 670},
                 {'name': '白阶', 'x': 1040, 'y': 970}, {'name': '下湖', 'x': 730, 'y': 1290}], bounds=(0, 0, 2200, 1800),
        provenance={'inspiration': 'Plitvice Lakes National Park: cropped Lower Lakes canyon and lake-to-lake tufa transitions.',
            'scope': 'Four schematic lake basins with two shore paths per basin and shared necks. Fictional roads and stations, not a copy of a visitor route.',
            'sources': ['https://np-plitvicka-jezera.hr/en/plan-your-visit/istrazite-jezera/activities/lake-tour-programmes/',
                        'https://np-plitvicka-jezera.hr/en/natural-and-cultural-heritage/natural-heritage/tufa/'],
            'private_boundary': 'Real names and source URLs remain outside all agent observations.'})


BUILDERS = {'forest': build_forest, 'cascade': build_cascade}
DESIGN_PATHS = {'forest': ROOT/'memorybenchmark/data/history/forest_easy20.json',
                'cascade': ROOT/'memorybenchmark/data/history/difficulty-v1/cascade_easy20.json'}


if __name__ == '__main__':
    from scripts.build_field_maps import build,FILES
    for name in ('forest','cascade'):
        path=ROOT/'memorybenchmark/data'/(FILES[name]+'.json')
        path.write_text(json.dumps(build(name),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(path)
