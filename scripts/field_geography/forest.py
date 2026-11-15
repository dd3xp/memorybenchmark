"""Muir-inspired creek walk, unequal bank paths and an elevated western loop."""
from .common import Landscape,finish,draw_bridges
from scripts.hard_geography.drawing import Drawing,smooth

def build():
    g=Landscape('forest',2200,1600,distance_unit=135)
    points=[('w0',820,1370,'西岸下口'),('w1',720,1130,'西岸杉林'),
            ('w2',640,850,'蕨坡路口'),('w3',650,540,'古木路口'),('w4',820,300,'上溪坡口'),
            ('nw',940,320,'上溪桥西'),('ne',1210,320,'上溪桥东'),
            ('mw',930,770,'中溪桥西'),('me',1240,770,'中溪桥东'),
            ('sw',980,1200,'下溪桥西'),('se',1250,1200,'下溪桥东'),
            ('e0',1430,1330,'东岸下口'),('e1',1410,1010,'浅湾路口'),
            ('e2',1420,540,'林冠路口'),('e3',1350,260,'上溪东口'),
            ('h0',380,1080,'西坡下口'),('h1',350,750,'山坡栈道'),('h2',430,420,'西坡上口')]
    for row in points:g.point(*row)
    g.point('C',1510,1470,'溪口营地','camp')
    s=[g.station(*row) for row in [(770,1250),(680,985),(640,700),(730,410),
       (365,925),(385,565),(1420,1190),(1340,885),(1385,390),(1600,1350),
       (220,1090),(260,350),(670,185),(1510,155),(1640,520),(1650,1000)]]
    g.route('西岸步道','w0',s[0],'w1',s[1],'w2',s[2],'w3',s[3],'w4','nw')
    g.route('西坡长环','w1','h0',s[4],'h1',s[5],'h2','w4')
    g.route('蕨坡联径','w2','h1')
    g.route('东岸平径','ne','e3',s[8],'e2','me',s[7],'e1',s[6],'e0')
    g.route('下溪入口','e0',s[9],'C')
    g.route('上溪桥','nw','ne',tag='bridge')
    g.route('中溪桥','mw','me',tag='bridge')
    g.route('下溪桥','sw','se',tag='bridge')
    g.route('中桥坡路','w2','mw')
    g.route('下桥西路','w1','sw','w0')
    g.route('下桥东路','e1','se','e0')
    for node,station in [('h0',s[10]),('h2',s[11]),('w4',s[12]),('e3',s[13]),('e2',s[14]),('e1',s[15])]:g.route('林内站径',node,station)
    for row in [(910,1350,'下溪西滩','w0'),(1310,1300,'下溪东滩','se','e0'),
                (835,880,'蕨坡测点','w2','mw'),(1320,650,'林冠测点','me','e2'),
                (270,200,'山坡古木测点',s[11]),(1600,730,'东坡林缘','e2'),
                (1000,165,'上溪西滩','nw'),(1270,105,'上溪东滩','e3')]:g.survey(*row)
    g.regions=[{'name':'山坡长环','x':340,'y':660},{'name':'古木溪谷','x':1040,'y':1050},{'name':'东岸缓径','x':1670,'y':830}]
    g.features={'major_water':[{'name':'杉溪','width':34,'points':[(1130,-80),(1060,310),(1100,620),(1010,950),(1150,1300),(1100,1690)]}],
                'bridges':[['nw','ne'],['mw','me'],['sw','se']]}
    g.rationale=['Keep the redwood creek and three bank crossings, with an unequal western hillside loop and shorter eastern valley paths.',
                 'The main creek path, slope alternative and bridge approaches have different roles; service stations are mixed through-sites and forest spurs.',
                 'The camp is at the lower eastern entrance, rather than joining the two banks as a fourth identical ladder rung.']
    return finish(g,26110502)

def terrain(geo,name):
    d=Drawing(name,2200,1600,'#e3e9d9')
    d.forest([(50,70),(470,30),(870,110),(930,440),(780,710),(820,1070),(620,1480),(110,1510),(40,1110)],602,colour='#aec1a3',trees=140)
    d.forest([(1290,40),(1930,90),(2120,450),(2030,880),(2100,1440),(1740,1550),(1480,1260),(1350,960),(1410,510)],603,colour='#b7c8aa',trees=110)
    for points in [[(100,1230),(180,860),(250,580),(430,220),(700,120)],
                   [(180,1350),(260,980),(360,690),(550,310),(810,240)],
                   [(300,1470),(410,1170),(510,890),(620,650),(830,480)],
                   [(1550,130),(1710,470),(1640,800),(1810,1150),(1770,1460)]]:
        d.path(smooth(points),stroke='#8da080',width=2,opacity=.42)
    for water in geo['features']['major_water']:d.river(water['points'],water['width'])
    draw_bridges(d,geo)
    d.text(1115,610,'杉溪',size=27,fill='#678f84',angle=80)
    return d.finish()
