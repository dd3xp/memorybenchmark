"""Two wooded valleys converge below an irregular ridge-and-coppice road system."""
from .common import Landscape,finish,draw_bridges
from scripts.hard_geography.drawing import Drawing,smooth

def build():
    g=Landscape('boar',3100,2400,distance_unit=150)
    rows=[('a0',500,220,'西北林口'),('a1',340,660,'西坡林岔'),('a2',420,1120,'西谷林岔'),
          ('a3',700,1500,'西谷下岔'),('a4',940,1790,'林南坡口'),
          ('r0',1250,230,'北岭林口'),('r1',1570,410,'北岭鞍口'),('r2',1800,700,'中岭北岔'),
          ('r3',1640,1050,'中岭林岔'),('r4',1510,1430,'中岭南岔'),('r5',1630,1770,'双溪夹地'),
          ('x0',1200,650,'西岭上岔'),('x1',1310,1000,'西岭中岔'),
          ('e0',2650,240,'东北林口'),('e1',2710,720,'东坡林岔'),('e2',2560,1150,'东谷林岔'),
          ('e3',2470,1570,'东谷下岔'),('e4',2260,1940,'东南坡口'),('e5',2100,2220,'东南林缘'),('far',2820,1300,'外岭林道'),
          ('wn',720,580,'上西桥西'),('wm',1000,580,'上西桥东'),('ws',900,1370,'下西桥西'),('wt',1250,1370,'下西桥东'),
          ('en',2140,650,'上东桥西'),('em',2490,650,'上东桥东'),('es',1940,1590,'下东桥西'),('et',2260,1590,'下东桥东'),
          ('sn',1480,2200,'合流桥西'),('sm',1920,2200,'合流桥东')]
    for row in rows:g.point(*row)
    g.point('C',1060,2110,'林缘巡测营地','camp')
    s=[g.station(*row) for row in [(410,430),(375,895),(540,1320),(790,1640),(1230,2160),(920,1950),
       (1100,600),(1210,405),(1400,320),(1690,570),(1450,675),(1240,825),(1480,1030),(1390,1220),
       (1580,1240),(1570,1610),(1700,1910),(2030,690),(1800,1680),
       (2670,470),(2640,930),(2520,1370),(2380,1760),(2180,2080),(2010,2220),(2790,1030),
       (680,100),(180,1020),(730,1780),(1480,120),(1950,380),(2940,1540)]]
    g.route('西林弯路','a0',s[0],'a1',s[1],'a2',s[2],'a3',s[3],'a4',s[5],'C',s[4],'sn')
    g.route('西上桥径','a0','wn','a1')
    g.route('西下桥径','a2','ws','a3')
    g.route('西桥入岭','wm',s[6],'x0')
    g.route('西下桥入岭','wt','r4')
    g.route('中岭主路','r0',s[8],'r1',s[9],'r2','r3',s[14],'r4',s[15],'r5',s[16])
    g.route('西岭绕路','r0',s[7],'x0',s[11],'x1',s[13],'r4')
    g.route('上岭联路','x0',s[10],'r2')
    g.route('中岭联路','x1',s[12],'r3')
    g.route('中岭上东桥','r2',s[17],'en')
    g.route('夹地下东桥','r5',s[18],'es')
    g.route('东林长路','e0',s[19],'e1',s[20],'e2',s[21],'e3',s[22],'e4',s[23],'e5',s[24],'sm')
    g.route('东北桥径','e0','em','e2')
    g.route('东南桥径','e3','et','e4')
    g.route('东外岭绕路','e1',s[25],'far','e3')
    g.point('cop',210,1470,'西部林班空地')
    g.route('西林班外环','a1',(130,500),(80,800),s[27],'cop','a3')
    for name,a,b in [('上西溪桥','wn','wm'),('下西溪桥','ws','wt'),('上东溪桥','en','em'),('下东溪桥','es','et'),('合流下桥','sn','sm')]:g.route(name,a,b,tag='bridge')
    for a,b in [('a0',s[26]),('a2',s[27]),('a4',s[28]),('r0',s[29]),('r1',s[30]),('far',s[31])]:g.route('林班站径',a,b)
    for row in [(300,200,'西北林缘测点','a0'),(1760,180,'北岭林地测点',s[29],s[30]),
                (200,680,'西坡林地测点','a1'),(2200,320,'东北溪谷测点','en'),
                (600,1190,'西谷土坡测点','a2','ws'),(2870,710,'东坡林缘测点','e1'),
                (1400,900,'中岭植被测点','x1','r3'),(1700,2000,'双溪合流测点',s[16]),
                (600,2200,'南部林缘测点','C'),(2260,2320,'东南林地测点','e5'),
                (2940,1770,'外岭动物测点',s[31]),(1510,1540,'夹地坡面测点','r4')]:g.survey(*row)
    g.features={'major_water':[
        {'name':'西溪','width':26,'points':[(900,-80),(860,420),(1050,800),(1020,1150),(1230,1510),(1420,1800),(1690,2040),(1800,2500)]},
        {'name':'东溪','width':22,'points':[(2420,-80),(2310,420),(2320,820),(2170,1150),(2160,1460),(1930,1800),(1690,2040)]}],
        'bridges':[['wn','wm'],['ws','wt'],['en','em'],['es','et'],['sn','sm']]}
    g.regions=[{'name':'西林班环地','x':300,'y':1360},{'name':'中岭林班','x':1480,'y':810},
               {'name':'东部林谷','x':2600,'y':1830},{'name':'双溪夹地','x':1710,'y':1760}]
    g.rationale=['Replace the old 3x4 lattice with unequal forest compartments separated by two converging valleys.',
                 'Five bridges have different roles: upper and lower crossings on each tributary, plus a downstream crossing between the outer forest edges.',
                 'The central wooded peninsula terminates at the confluence; it cannot magically connect across the streams. Ridge bypasses, valley lanes and outer coppice paths remain distinct.',
                 'Mixed through-stations, small forest spurs and remote survey approaches follow the authored tracks, rather than a repeated station attachment rule.']
    return finish(g,26110513,normal=True)

def terrain(geo,name):
    d=Drawing(name,3100,2400,'#e2e6d5')
    d.forest([(40,100),(710,60),(790,380),(950,730),(860,1150),(1120,1620),(1200,2040),(710,2330),(130,2120)],1013,colour='#aabd99',trees=150)
    d.forest([(1040,60),(2130,90),(2220,580),(2030,1190),(1980,1650),(1710,1990),(1410,1590),(1190,1140),(1050,680)],1014,colour='#b4c19e',trees=145)
    d.forest([(2530,100),(3020,130),(3050,2220),(2250,2350),(2070,2000),(2360,1550),(2430,1010)],1015,colour='#a8b996',trees=120)
    from scripts.hard_geography.drawing import organic
    for i,(x,y,rx,ry) in enumerate([(230,1450,150,100),(1490,830,180,100),(2780,1350,100,170),(2000,2160,110,70)]):
        d.path(organic(x,y,rx,ry,i+.8),fill='#d7dabc',opacity=.75)
    for points in [[(1120,150),(1370,480),(1430,910),(1650,1270),(1580,1630)],
                   [(1240,100),(1490,430),(1550,870),(1790,1220),(1720,1580)],
                   [(230,220),(150,720),(280,1190),(570,1600),(800,1820)],
                   [(2830,210),(2920,710),(2830,1200),(2850,1640),(2490,2070)]]:
        d.path(smooth(points),stroke='#899b79',width=3,opacity=.35)
    for water in geo['features']['major_water']:d.river(water['points'],water['width'])
    draw_bridges(d,geo)
    d.text(1000,920,'西溪',size=27,fill='#638f83',angle=85)
    d.text(2280,1030,'东溪',size=27,fill='#638f83',angle=96)
    return d.finish()
