"""Export a self-contained public geography SVG and evaluator task schedule."""
from hashlib import sha256
import argparse,json
from pathlib import Path
import xml.etree.ElementTree as ET

from memorybenchmark.prototypes.station_capability import load_design
from memorybenchmark.prototypes.station_experience import experience_schedule
from memorybenchmark.prototypes.station_session import NESSIE_EASY_DESIGN


NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
def element(parent,tag,attrs=None,text=None):
    item=ET.SubElement(parent,'{'+NS+'}'+tag,{k:str(v) for k,v in (attrs or {}).items()})
    if text is not None:item.text=str(text)
    return item


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    design=load_design(NESSIE_EASY_DESIGN);public=design['public'];places=public['locations']
    terrain=NESSIE_EASY_DESIGN.parent.parent/'static/nessie-terrain.svg'
    root=ET.fromstring(terrain.read_text(encoding='utf-8'))
    root.find('{'+NS+'}title').text='尼斯湖水怪 · 完整公开地图'
    root.find('{'+NS+'}desc').text='全部 61 个地点、61 条道路与距离。圆点为测绘点，方框为基站，三角为营地。不含隐藏能力配对。'
    layer=element(root,'g',{'font-family':'Microsoft YaHei,Noto Sans CJK SC,sans-serif'})
    for a,b,w in public['edges']:
        p,q=places[a],places[b]
        element(layer,'path',{'d':f'M{p["x"]} {p["y"]}L{q["x"]} {q["y"]}','fill':'none','stroke':'#7d9384','stroke-width':2,'stroke-dasharray':'6 5'})
        element(layer,'text',{'x':(p['x']+q['x'])/2+8,'y':(p['y']+q['y'])/2-7,'font-size':16,'fill':'#526d61','paint-order':'stroke','stroke':'#e2e9dc','stroke-width':5},w)
    for id_,p in places.items():
        g=element(layer,'g',{'transform':f'translate({p["x"]} {p["y"]})'})
        element(g,'title',text=f'{id_} {p["name"]}')
        if p['kind']=='station':
            element(g,'rect',{'x':-12,'y':-12,'width':24,'height':24,'rx':3,'fill':'#f5f8e9','stroke':'#436a67','stroke-width':2})
        elif p['kind']=='camp':
            element(g,'path',{'d':'M0-18 18 14H-18Z','fill':'#246776','stroke':'white','stroke-width':2})
        else:
            element(g,'circle',{'r':4 if p.get('transit') else 13 if p['kind']=='survey' else 7,'fill':'#eef5e8','stroke':'#658377','stroke-width':1.8})
        if not p.get('transit'):
            element(g,'text',{'x':0,'y':-23,'text-anchor':'middle','font-size':20 if p['kind'] in ('station','survey','camp') else 16,'font-weight':600,'fill':'#2b5557','paint-order':'stroke','stroke':'#e2e9dc','stroke-width':5},id_)
            if p['kind'] in ('survey','camp'):
                element(g,'text',{'x':0,'y':36,'text-anchor':'middle','font-size':18,'fill':'#385d58','paint-order':'stroke','stroke':'#e2e9dc','stroke-width':5},p['name'])
    element(root,'metadata',text=json.dumps({'kind':'public_geography_not_agent_trace','design_id':design['design_id'],
        'design_sha256':sha256(NESSIE_EASY_DESIGN.read_bytes()).hexdigest(),'nodes':len(places),'roads':len(public['edges']),
        'hidden_capabilities_included':False},ensure_ascii=False))
    ET.indent(root)
    ET.ElementTree(root).write(args.output/'complete-map.svg',encoding='utf-8',xml_declaration=True)
    (args.output/'task-dependencies.json').write_text(json.dumps(experience_schedule(design),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'nodes':len(places),'roads':len(public['edges']),'hidden_capabilities_included':False}))


if __name__=='__main__':main()
