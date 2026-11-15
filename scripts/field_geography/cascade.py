"""Four unequal lower-lake shore loops remain connected by shared tufa necks."""
from .common import Landscape,finish
from scripts.hard_geography.drawing import Drawing,smooth
from scripts.hard_geography.review import sampled_curve

def build():
    g=Landscape('cascade',2200,1800,distance_unit=135)
    g.point('C',1850,160,'高岸营地','camp')
    for i,(x,y) in enumerate([(1590,300),(1320,610),(1030,910),(740,1210),(460,1480)]):g.point(f'N{i}',x,y,f'湖阶通口{i+1}')
    for i,(left,right) in enumerate([((1260,300),(1560,600)),((970,610),(1300,920)),((680,910),(1010,1230)),((390,1200),(730,1500))]):
        g.point(f'L{i}',*left,f'第{i+1}湖西岸');g.point(f'R{i}',*right,f'第{i+1}湖东岸')
    s=[g.station(*row) for row in [(1410,300),(1270,460),(1580,450),(1450,605),
       (1130,610),(995,755),(1310,775),(1165,915),
       (850,910),(700,1075),(1020,1065),(865,1220),
       (1120,180),(1790,620),(320,1030),(980,1570)]]
    g.route('高岸入口','C','N0')
    for i in range(3):
        g.route(f'第{i+1}湖西岸步道',f'N{i}',s[4*i],f'L{i}',s[4*i+1],f'N{i+1}')
        g.route(f'第{i+1}湖东岸步道',f'N{i}',s[4*i+2],f'R{i}',s[4*i+3],f'N{i+1}')
    g.route('下湖西岸','N3','L3','N4')
    g.route('下湖东岸','N3','R3','N4')
    for a,b in [('L0',s[12]),('R0',s[13]),('L3',s[14]),('R3',s[15])]:g.route('岸坡站径',a,b)
    for row in [(1210,160,'上湖崖边测点',s[12]),(1710,500,'上湖东岸测点','R0'),
                (870,590,'青潭西岸测点','L1'),(1400,990,'青潭跌水测点','R1'),
                (560,840,'白阶西崖测点','L2'),(1120,1320,'白阶石滩测点','R2'),
                (270,1170,'下湖苔岸测点',s[14]),(800,1640,'末端跌水测点',s[15])]:g.survey(*row)
    lakes=[[(1390,330),(1460,320),(1510,390),(1515,480),(1460,565),(1380,560),(1335,490),(1330,400)],
           [(1110,635),(1190,640),(1230,720),(1220,805),(1170,878),(1100,880),(1050,800),(1050,715)],
           [(830,935),(910,940),(950,1020),(945,1110),(880,1180),(810,1185),(765,1110),(765,1000)],
           [(535,1235),(605,1245),(655,1320),(660,1400),(605,1470),(530,1475),(480,1410),(475,1310)]]
    lakes=[sampled_curve([*p,p[0]],subdivisions=8) for p in lakes]
    g.features={'lakes':lakes,'tufa_necks':[(1320,610),(1030,910),(740,1210)]}
    g.regions=[{'name':'上湖峡谷','x':1700,'y':370},{'name':'青潭','x':1150,'y':760},
               {'name':'白阶','x':855,'y':1060},{'name':'下湖','x':565,'y':1360}]
    g.rationale=['Retain the serial Lower Lakes canyon: four shoreline alternatives separated by shared, unavoidable tufa necks.',
                 'Twelve processing sites lie along shore routes; four occupy distinct cliff or waterfall approaches, with no common two-edge spur pattern.',
                 'Lake polygons are authored together with both shore paths; paths and stations stay outside the water.']
    # Pair shore alternatives, not two upstream/downstream sites on the same
    # unavoidable return corridor. Type letters are shuffled independently.
    return finish(g,26110503,replica_pairs=[(0,2),(1,3),(4,6),(5,7),(8,10),(9,11),(12,13),(14,15)])

def terrain(geo,name):
    d=Drawing(name,2200,1800,'#e6e9d6')
    d.forest([(40,50),(850,30),(1160,270),(950,520),(750,700),(520,850),(320,1190),(80,1390)],703,colour='#b4c2a0',trees=95)
    d.forest([(1740,330),(2130,480),(2190,1660),(1390,1770),(1010,1540),(1210,1340),(1380,1040),(1560,810)],704,colour='#bcc8a7',trees=85)
    for off in (0,55,110):
        d.path(smooth([(1120-off,90),(900-off,340),(690-off,620),(480-off,900),(280-off,1230)]),stroke='#99aa89',width=2,opacity=.48)
        d.path(smooth([(1840+off,480),(1630+off,760),(1420+off,1050),(1240+off,1390),(1010+off,1710)]),stroke='#9aaa89',width=2,opacity=.48)
    for polygon in geo['features']['lakes']:
        d.polygon(polygon,'#82b5b0','#80a79a',3)
    for x,y in [(1425,440),(1140,750),(850,1060),(565,1350)]:
        d.path(f'M{x-35},{y}q35,-13 70,0m-60,25q30,-11 57,0',stroke='#c1d8ca',width=2,opacity=.55)
    for points in [[(1390,560),(1350,590),(1320,610),(1190,640)],
                   [(1100,880),(1060,890),(1030,910),(910,940)],
                   [(810,1185),(770,1205),(740,1210),(605,1245)]]:
        d.path(smooth(points),stroke='#85afa2',width=9)
    for x,y in geo['features']['tufa_necks']:
        for off in (-20,0,20):d.path(f'M{x-35+off},{y-17+off}l60,38',stroke='#eee9cc',width=13)
    return d.finish()
