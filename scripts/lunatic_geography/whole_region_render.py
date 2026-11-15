"""Region-colored, editable SVG cartography without capability answers."""
import xml.etree.ElementTree as ET
from scripts.lunatic_geography.whole_region import REGION_NAMES,COLORS

NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
def terrain(geo,name):
    w,h=geo['view_box'][2:];root=ET.Element('{'+NS+'}svg',{'viewBox':f'0 0 {w} {h}','width':str(w),'height':str(h)})
    def el(tag,attrs=None,text=None,parent=root):
        n=ET.SubElement(parent,'{'+NS+'}'+tag,{k:str(v) for k,v in (attrs or {}).items()})
        n.text=text;return n
    points=lambda p:' '.join(f'{x:.2f},{y:.2f}' for x,y in p)
    el('title',text=name+' · 全区域与处理分区')
    el('desc',text='参考地理范围上的实验地图。三种颜色表示公开处理区域类别，不代表隐藏站型能力；非历史道路、人口或动物范围复原。')
    defs=el('defs');clip=el('clipPath',{'id':'land-region-clip'},parent=defs)
    for ring in geo['features']['land']:el('polygon',{'points':points(ring)},parent=clip)
    el('rect',{'width':w,'height':h,'fill':'#a9c7ca'})
    for ring in geo['features']['context_land']:
        el('polygon',{'points':points(ring),'fill':'#cbd3c4','stroke':'#9cac9b','stroke-width':5})
    for ring in geo['features']['land']:
        el('polygon',{'points':points(ring),'fill':'#eee8d5','stroke':'#859a82','stroke-width':8})
    for r in geo['regions']:
        el('polygon',{'points':points(r['polygon']),'fill':COLORS[r['category']],'fill-opacity':.34,
            'stroke':'#f7f4e9','stroke-width':7,'stroke-opacity':.65,'clip-path':'url(#land-region-clip)'})
    for ring in geo['features']['lakes']:
        el('polygon',{'points':points(ring),'fill':'#a9c7ca','stroke':'#839fa3','stroke-width':4})
    # Sparse physiographic accents follow reference landscape seeds rather
    # than a repeated decoration tile. Region labels remain UI text on top.
    for r in geo['regions']:
        if r['category']=='natural':
            x,y=r['x'],r['y'];el('path',{'d':f'M{x-35} {y+12}l35 -45 35 45m-41 -8 9 -13 10 12',
                'fill':'none','stroke':'#637d61','stroke-width':5,'opacity':.38})
    legend_y=h-190
    el('rect',{'x':80,'y':legend_y,'width':w-160,'height':140,'rx':18,'fill':'#f7f3e5','fill-opacity':.94})
    for i,(category,label) in enumerate(REGION_NAMES.items()):
        x=140+i*(w-360)/3;el('rect',{'x':x,'y':legend_y+35,'width':42,'height':42,'fill':COLORS[category]})
        el('text',{'x':x+65,'y':legend_y+70,'font-size':38,'fill':'#304c42','font-family':'Microsoft YaHei,Noto Sans CJK SC,sans-serif'},label)
    ET.indent(root);return ET.tostring(root,encoding='unicode')

def complete(geo,name):
    root=ET.fromstring(terrain(geo,name));root.find('{'+NS+'}title').text+=' · 完整公开路网'
    def el(tag,attrs,text=None):
        n=ET.SubElement(root,'{'+NS+'}'+tag,{k:str(v) for k,v in attrs.items()});n.text=text;return n
    loc=geo['locations']
    for a,b,weight in geo['edges']:
        p,q=loc[a],loc[b];ferry='ferry' in geo['edge_tags']['|'.join(sorted((a,b)))]
        el('path',{'d':f'M{p["x"]} {p["y"]}L{q["x"]} {q["y"]}','fill':'none',
           'stroke':'#508b9c' if ferry else '#657e62','stroke-width':6,'stroke-dasharray':'24 18' if ferry else 'none'})
    for k,p in loc.items():
        x,y=p['x'],p['y'];category=p['region_category'];kind=p['kind']
        if kind=='station':el('rect',{'x':x-19,'y':y-19,'width':38,'height':38,'rx':4,'fill':COLORS[category],'stroke':'#294c40','stroke-width':4})
        elif kind=='camp':el('path',{'d':f'M{x} {y-28}l27 47h-54Z','fill':'#294c40','stroke':'#fff4de','stroke-width':4})
        else:el('circle',{'cx':x,'cy':y,'r':13 if kind=='survey' else 7,'fill':'#faf4de','stroke':'#62785e','stroke-width':4})
        if kind!='junction':el('text',{'x':x,'y':y-30,'font-size':29,'text-anchor':'middle','fill':'#24483e',
            'font-family':'sans-serif','stroke':'#fff9e8','stroke-width':7,'paint-order':'stroke'},k)
    ET.indent(root);return ET.tostring(root,encoding='unicode')
