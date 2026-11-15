"""Render deterministic vector terrains and complete anonymous public maps."""
import argparse
from html import escape
import json
from math import cos, sin, pi
from pathlib import Path
import xml.etree.ElementTree as ET

from memorybenchmark.prototypes.station_capability import load_design
from scripts.build_easy_maps import DESIGN_PATHS


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'memorybenchmark/static'
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)


def terrain_header(name, height=1600):
    return [f'<svg xmlns="{NS}" viewBox="0 0 2200 {height}" width="2200" height="{height}">',
        f'<title>{name} · 公开地形示意</title><desc>虚构地点和道路所用的地形底图，无隐藏能力或现实坐标。</desc>',
        '<defs><linearGradient id="land" x2="1" y2="1"><stop stop-color="#e9eee0"/><stop offset=".5" stop-color="#d9e3d3"/><stop offset="1" stop-color="#e9e8d6"/></linearGradient>',
        '<linearGradient id="water" x2=".8" y2="1"><stop stop-color="#9fcac0"/><stop offset=".5" stop-color="#68a8a3"/><stop offset="1" stop-color="#47818b"/></linearGradient>',
        '<pattern id="grain" width="61" height="73" patternUnits="userSpaceOnUse"><path d="M7 13h1m28 22h1m14 24h1M19 61h1" stroke="#425e4a" stroke-width="1.5" opacity=".09"/></pattern>',
        '<pattern id="canopy" width="53" height="49" patternUnits="userSpaceOnUse" patternTransform="rotate(-14)"><path d="M8 25q-6-9 4-13t7 13m11 18q-4-9 4-12t7 10" stroke="#4e7458" stroke-width="1" fill="none" opacity=".19"/></pattern></defs>',
        f'<rect width="2200" height="{height}" fill="url(#land)"/>']


def organic(cx, cy, rx, ry, phase=0):
    points = []
    for i in range(49):
        a = 2*pi*i/48
        r = 1 + .06*sin(3*a+phase) + .035*sin(7*a-phase)
        points.append((cx+rx*cos(a)*r, cy+ry*sin(a)*r))
    return 'M' + 'L'.join(f'{x:.1f},{y:.1f}' for x, y in points) + 'Z'


def forest_terrain():
    parts = terrain_header('雾杉溪谷')
    for i, (cx, cy, rx, ry) in enumerate(((410, 450, 510, 620), (1650, 1030, 450, 690), (400, 1440, 400, 350), (1650, 250, 460, 430))):
        path = organic(cx, cy, rx, ry, i)
        parts += [f'<path d="{path}" fill="#a9c2a4" opacity=".34"/>', f'<path d="{path}" fill="url(#canopy)"/>']
        for scale in (.82, .70, .58, .46):
            parts.append(f'<path d="{organic(cx,cy,rx*scale,ry*scale,i)}" fill="none" stroke="#6f9272" stroke-width="1.4" opacity=".24"/>')
    river = 'M1100 1650C1080 1480 1060 1370 1030 1240S965 1150 980 1070S1040 860 1010 790S970 620 1010 520S1100 360 1055 260S970 100 1070-50'
    parts += [f'<path d="{river}" stroke="#c1d2bd" stroke-width="95" fill="none" opacity=".55"/>',
        f'<path d="{river}" stroke="#78aaa0" stroke-width="35" fill="none"/>',
        f'<path d="{river}" stroke="#b6d2c5" stroke-width="13" fill="none" opacity=".7"/>',
        '<path d="M1310 30C1420 180 1270 360 1100 410S1040 470 1010 520" fill="none" stroke="#85b3a4" stroke-width="12"/>',
        '<path d="M440 40C500 210 600 330 790 370S930 470 1010 520" fill="none" stroke="#a0bba3" stroke-width="5" opacity=".6"/>']
    parts += ['<g fill="#456c58" opacity=".15">']
    for i in range(26):
        cx = 190 + ((i*157) % 1750); cy = 150 + ((i*229) % 1340)
        if abs(cx-1020) < 140: continue
        parts.append(f'<path d="{organic(cx,cy,32+(i%3)*8,48+(i%4)*8,i)}"/>')
    parts += ['</g><rect width="2200" height="1600" fill="url(#grain)" pointer-events="none"/>', '</svg>']
    return '\n'.join(parts)


def cascade_terrain():
    parts = terrain_header('石阶湖群', 1800)
    for i, (cx, cy) in enumerate(((440, 340), (1720, 1290))):
        parts.append(f'<path d="{organic(cx,cy,590,850,i)}" fill="#c3cfb3" opacity=".58"/>')
        for scale in (.91, .8, .69, .58, .47):
            parts.append(f'<path d="{organic(cx,cy,590*scale,850*scale,i)}" fill="none" stroke="#8ca080" stroke-width="1.8" opacity=".31"/>')
    centers = [(1430, 450), (1150, 760), (860, 1060), (570, 1360)]
    for i, (cx, cy) in enumerate(centers):
        path = organic(cx, cy, 110, 162, i+.5)
        parts += [f'<path d="{path}" fill="none" stroke="#c0ccb0" stroke-width="24"/>',
                  f'<path d="{path}" fill="url(#water)" stroke="#699c91" stroke-width="2"/>',
                  f'<path d="{organic(cx+13,cy+10,70,119,i+.5)}" fill="#477f87" opacity=".24"/>']
        for j in range(3):
            parts.append(f'<path d="M{cx-40+j*8} {cy-50+j*20}q40-18 78-2" fill="none" stroke="#d0e2d2" stroke-width="2" opacity=".4"/>')
        if i < 3:
            nx, ny = centers[i+1]
            parts.append(f'<path d="M{cx-85} {cy+130}Q{cx-155} {cy+240} {nx+85} {ny-130}" fill="none" stroke="#76aea0" stroke-width="17"/>')
    for x, y in ((1320, 610), (1030, 910), (740, 1210)):
        parts += [f'<path d="M{x-37} {y-21}l55 55m-73-36 55 55m-72-36 55 55" fill="none" stroke="#e9ead4" stroke-width="10"/>',
                  f'<path d="M{x-37} {y-21}l55 55m-73-36 55 55m-72-36 55 55" fill="none" stroke="#b4c5ad" stroke-width="1.5"/>']
    for i, (cx, cy) in enumerate(((1700, 270), (1920, 900), (400, 640), (250, 1530))):
        parts.append(f'<path d="{organic(cx,cy,270,340,i)}" fill="url(#canopy)"/>')
    parts += ['<rect width="2200" height="1800" fill="url(#grain)" pointer-events="none"/>', '</svg>']
    return '\n'.join(parts)


def public_map(design, destination):
    public = design['public']; locations = public['locations']
    root = ET.fromstring((STATIC / (public['terrain']+'-terrain.svg')).read_text(encoding='utf-8'))
    root.find('{'+NS+'}title').text = public['name'] + ' · 完整公开地图'
    group = ET.SubElement(root, '{'+NS+'}g', {'font-family': 'Microsoft YaHei,Noto Sans CJK SC,sans-serif'})
    def add(tag, attrs, text=None):
        item = ET.SubElement(group, '{'+NS+'}'+tag, {k: str(v) for k, v in attrs.items()})
        if text is not None: item.text = str(text)
        return item
    for a, b, weight in public['edges']:
        p, q = locations[a], locations[b]
        add('path', {'d': f'M{p["x"]} {p["y"]}L{q["x"]} {q["y"]}', 'stroke': '#627e71', 'stroke-width': 3, 'fill': 'none'})
        add('text', {'x': (p['x']+q['x'])/2+8, 'y': (p['y']+q['y'])/2-7, 'font-size': 15, 'fill': '#3e6257',
                     'stroke': '#e5eadc', 'stroke-width': 4, 'paint-order': 'stroke'}, weight)
    for key, node in locations.items():
        x, y = node['x'], node['y']; transit = node.get('transit')
        if node['kind'] == 'station': add('rect', {'x': x-12, 'y': y-12, 'width': 24, 'height': 24, 'rx': 4, 'fill': '#f8f8eb', 'stroke': '#315c53', 'stroke-width': 2})
        elif node['kind'] == 'camp': add('path', {'d': f'M{x} {y-18}l18 32h-36Z', 'fill': '#315c53', 'stroke': '#f8f8eb', 'stroke-width': 2})
        else: add('circle', {'cx': x, 'cy': y, 'r': 4 if transit else 11 if node['kind'] == 'survey' else 7, 'fill': '#f8f8eb', 'stroke': '#537768', 'stroke-width': 2})
        if not transit:
            add('text', {'x': x, 'y': y-23, 'font-size': 19, 'text-anchor': 'middle', 'fill': '#294e45', 'font-weight': 600,
                         'stroke': '#e5eadc', 'stroke-width': 5, 'paint-order': 'stroke'}, key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(destination, encoding='utf-8', xml_declaration=True)


def main():
    from scripts.render_field_maps import main as render_current
    render_current()


if __name__ == '__main__':main()
