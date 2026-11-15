"""Retain the coloured-hill loop and inner gullies; redesign the service sites."""
from .common import Landscape,finish

def build():
    g=Landscape('rainbow',2200,1600,distance_unit=135)
    points=[('r0',480,1240,'西南沟口'),('r1',420,870,'西沟岔口'),
            ('r2',570,480,'西岭坡口'),('r3',920,240,'北岭鞍部'),
            ('r4',1440,300,'东北岭口'),('r5',1740,620,'东岭坡口'),
            ('r6',1770,1010,'东沟岔口'),('r7',1550,1330,'东南沟口'),
            ('r8',960,1110,'中沟南岔'),('r9',860,720,'中沟西岔'),
            ('r10',1200,520,'内岭坡口'),('r11',1390,910,'中沟东岔')]
    for row in points:g.point(*row)
    g.point('C',1100,1490,'沟口营地','camp')
    s=[g.station(*row) for row in [(450,1050),(465,680),(735,365),(1170,270),
       (1600,450),(1755,815),(1660,1180),(1320,1430),(1030,620),(1300,725),
       (790,100),(1500,130),(270,1300),(240,835),(1950,1040),(1740,1460)]]
    g.route('西沟主路','r0',s[0],'r1',s[1],'r2',s[2],'r3',s[3],'r4')
    g.route('东岭环路','r4',s[4],'r5',s[5],'r6',s[6],'r7',s[7],'C','r0')
    g.route('西内沟','r0','r8','r9','r2')
    g.route('中岭联路','r9',s[8],'r10',s[9],'r11','r6')
    g.route('内岭短路','r10','r4')
    g.route('中沟联路','r11','r8')
    for node,station in [('r3',s[10]),('r4',s[11]),('r0',s[12]),('r1',s[13]),('r6',s[14]),('r7',s[15])]:
        g.route('坡侧站径',node,station)
    for row in [(620,1310,'沟口层理测点','r0'),(1480,1220,'东南沟壁测点','r7','r11'),
                (300,720,'西沟剖面测点','r1'),(1930,875,'东沟测点','r6'),
                (625,385,'西坡测点','r2'),(1810,475,'东岭测点','r5'),
                (1010,115,'北鞍测点','r3'),(1430,465,'内岭测点','r4','r10')]:g.survey(*row)
    g.regions=[{'name':'西岭','x':430,'y':380},{'name':'彩沟','x':1000,'y':1020},{'name':'东岭','x':1810,'y':750}]
    g.features={}
    g.rationale=['Retain the original outer hill circuit and interior gully links; no new real-world area is claimed.',
                 'Ten processing sites lie on through-routes; six sit at distinct short slope spurs, rather than sixteen identical two-edge branches.',
                 'Two survey sites connect alternative routes; the camp remains at the southern gully mouth.']
    return finish(g,26110501)

def terrain(geo,name):
    # The existing coloured contours are distinctive and are retained.
    from scripts.render_difficulty_maps import rainbow
    return rainbow().replace('<rect width="2200" height="1600" fill="url(#grain)"/>','')
