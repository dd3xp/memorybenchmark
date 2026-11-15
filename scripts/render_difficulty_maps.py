"""Native vector terrains matching authored geography, no capability answers."""
from pathlib import Path
from scripts.render_easy_maps import terrain_header, organic
from memorybenchmark.prototypes.station_capability import load_design

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'memorybenchmark/static'


def rainbow():
    p=terrain_header('赭岭彩丘')
    p.append('<rect width="2200" height="1600" fill="#e9d8ba"/>')
    colors=['#cda485','#bb8268','#d3ae80','#af735f','#dbbe8e','#c58f70','#9b715e']
    for i,(cx,cy,rx,ry) in enumerate(((350,600,460,730),(950,230,590,350),(1690,570,450,690),(1210,1230,570,400))):
        p.append(f'<path d="{organic(cx,cy,rx,ry,i)}" fill="#c69678" opacity=".3"/>')
        for j in range(12):
            k=1-j*.065
            p.append(f'<path d="{organic(cx+j*7,cy-j*6,rx*k,ry*k,i)}" fill="{colors[(j+i)%len(colors)]}" opacity=".5" stroke="#9c735f" stroke-opacity=".22" stroke-width="1.5"/>')
    for path in ('M1100 1600Q900 1220 1000 1060T930 700T1080 400',
                 'M1040 1080Q1450 1000 1640 790','M940 770Q650 900 400 980'):
        p += [f'<path d="{path}" fill="none" stroke="#ead7b7" stroke-width="54" opacity=".75"/>',
              f'<path d="{path}" fill="none" stroke="#b79675" stroke-width="2" opacity=".5"/>']
    p += ['<rect width="2200" height="1600" fill="url(#grain)"/>','</svg>']
    return '\n'.join(p)


def main():
    from scripts.render_field_maps import main as render_current
    render_current()


if __name__=='__main__':main()
