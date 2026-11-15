"""Steppe crossroads, northern uplands and southern basin corridors."""
from scripts.lunatic_geography.common import Landscape,finish
from scripts.hard_geography.drawing import Drawing,organic,smooth

def build():
    g=Landscape('mongolia',6200,4400,distance_unit=170)
    points=[('w0',400,1700),('w1',1050,1200),('w2',1400,2060),('w3',900,2830),
        ('nw',1450,500),('n0',2360,380),('n1',3340,620),('n2',4510,470),('ne',5580,960),
        ('c0',2100,1460),('c1',3150,1600),('c2',4210,1380),('c3',5080,2070),
        ('p0',1730,2830),('p1',3040,2800),('p2',4160,2740),('p3',5530,2910),
        ('s0',1800,3850),('s1',3330,3970),('s2',4900,3890),('se',5810,3730),
        ('o0',2650,3370),('o1',4200,3550),('u0',3800,960),('u1',1570,960),
        ('a0',700,3520),('a1',5800,1980),('a2',5250,480),('a3',3930,2180)]
    for k,x,y in points:g.point(k,x,y,'草原路口·'+k)
    g.point('C',2670,2180,'驿路营地','camp')
    coords=[(710,1430),(1210,1620),(1130,2440),(630,2230),(1900,435),(2850,500),
        (3910,545),(5050,720),(5510,1410),(1500,1280),(2600,1530),(3680,1490),
        (4640,1725),(2370,1890),(3490,1880),(4670,2390),(3480,2760),(4860,2825),
        (1330,2830),(2020,3320),(2550,3910),(4110,3930),(5380,3810),
        (2220,3090),(2990,3100),(3760,3180),(4550,3710),(3010,3660),
        (1930,2400),(3390,2430),(4680,1090),(5360,3180),
        (430,1210),(980,790),(2100,170),(3450,280),(4680,220),(5910,750),
        (5880,2280),(5880,3010),(5970,4130),(4520,4190),(3230,4240),(1480,4130),
        (380,3780),(330,2870),(2030,1080),(3830,3540)]
    s=[g.station(*p) for p in coords]
    g.route('西山口古道','w0',s[0],'w1',s[1],'w2',s[2],'w3',s[3],'w0')
    g.route('北岭商道','w1','u1','nw',s[4],'n0',s[5],'n1',s[6],'n2',s[7],'ne')
    g.route('东北驿道','n2','a2','ne',s[8],'a1','c3')
    g.route('中原横道','w1',s[9],'c0',s[10],'c1',s[11],'c2',s[12],'c3')
    g.route('营地西辐路','w2',s[28],'C',s[13],'c0')
    g.route('营地北辐路','C',s[14],'c1','n1')
    g.route('营地东辐路','C','a3',s[15],'c3')
    g.route('南牧场横路','w3',s[18],'p0','p1',s[16],'p2',s[17],'p3')
    g.route('营地南辐路','C',s[29],'p1');g.route('东部连接路','c3','p3')
    g.route('西南长绕路','w3','a0','s0',s[20],'s1',s[21],'s2',s[22],'se','p3')
    g.route('西盆地走廊','p0',s[19],'s0')
    g.route('盆地北缘路','p0',s[23],'o0',s[24],'p1')
    g.route('盆地东缘路','p1',s[25],'o1',s[26],'s2')
    g.route('南盆地斜路','o0',s[27],'s1')
    g.route('东山口','p2',s[47],'o1');g.route('东北高路','c2',s[30],'n2')
    g.route('北岭内道','c1','u0','n2');g.route('北岭西径','u1',s[46],'c0')
    g.route('东盆地岔路','p3',s[31],'s2')
    for a,i in [('w0',32),('nw',33),('n0',34),('n1',35),('n2',36),('ne',37),('a1',38),
        ('p3',39),('se',40),('s2',41),('s1',42),('s0',43),('a0',44),('w3',45)]:g.route('牧地短径',a,s[i])
    surveys=[(250,1840,'w0'),(1450,1740,'w2'),(1290,290,'nw'),(2500,710,'n0'),
        (3340,1040,'n1'),(4340,790,'n2'),(5840,1210,'ne'),(2940,1250,'c1'),
        (4360,1810,'c2'),(5260,2350,'c3'),(1550,3190,'p0'),(3020,2480,'C'),
        (3990,3010,'p2'),(3830,4200,'s1'),(4760,3480,'s2'),(1000,3690,'a0')]
    names=['西山前台','西坡草沟','北原古道','北岭草甸','内岭坡面','东北浅谷','东原驿口','中部台地',
           '东岭盆沿','东部牧地','西南泉地','中原草坡','南牧高地','南沙沉积','东南浅盆','西南砾地']
    for (x,y,a),name in zip(surveys,names):g.survey(x,y,name,a)
    # Isolated saline depressions and a mountain mass are physical obstacles;
    # corridors above are designed around them, not painted beneath roads.
    g.features={'lakes':[[(3470,3330),(3650,3290),(3760,3440),(3630,3610),(3420,3540)]],
        'rocks':[[(440,500),(590,290),(860,340),(1020,550),(870,680),(640,690)]]}
    g.regions=[{'name':'北岭牧地','x':2650,'y':950},{'name':'中央驿原','x':3550,'y':2110},
        {'name':'南部盆地','x':3650,'y':3760},{'name':'西山前地','x':650,'y':3150}]
    g.rationale=['An oblique steppe crossroads with four unequal radial links, a northern ridge itinerary and two southern basin corridors.',
        'Peripheral pastures form an uneven outer route; local loops and sparse oasis links replace a rectangular district grid.',
        'Only landscape and settlement themes refer to medieval Mongolia; no claim to reconstruct imperial roads or supply stations.']
    return finish(g,26110542)

def terrain(geo,name):
    d=Drawing(name,6200,4400,'#dfdfb9')
    d.polygon([(0,3000),(1300,3180),(2370,2990),(3450,3160),(4400,3020),(6200,3240),(6200,4400),(0,4400)],'#d6c394',opacity=.8)
    for x,y,rx,ry in [(620,460,550,350),(1690,640,350,230),(3400,720,530,230),(4600,570,420,250)]:
        for f in (1,.75,.5):d.path(organic(x,y,rx*f,ry*f,.8),fill='#aeb397',stroke='#8b987f',width=3,opacity=.4)
    for p in geo['features']['rocks']:d.polygon(p,'#8e927b',opacity=.7)
    for p in geo['features']['lakes']:d.polygon(p,'#8eb3ae','#bdc6ac',12)
    for x,y in [(3150,1600),(2100,1460),(4210,1380),(2650,3370),(4900,3890)]:d.settlement(x+90,y-80,180,110,7,x+y,buildings=10)
    for pts in [[(400,3960),(1250,3750),(1730,3650)],[(4000,4080),(4820,4140),(5580,3920)],[(3850,3360),(4220,3290),(4710,3340)]]:
        d.path(smooth(pts),stroke='#b19e78',width=9,opacity=.5)
    return d.finish()
