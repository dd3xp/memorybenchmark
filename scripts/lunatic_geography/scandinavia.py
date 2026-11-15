"""Fjord peninsulas and an inland divide: no cross-fjord teleports or ferries."""
from scripts.lunatic_geography.common import Landscape,finish
from scripts.hard_geography.drawing import Drawing,smooth,organic

def build():
    g=Landscape('scandinavia',6000,4300,distance_unit=170)
    # The four coastal regions have different local paths and meet the inland
    # network beyond three unequal fjord heads. Coordinates are all authored.
    rows=[('n0',350,410),('n1',1250,350),('n2',2250,470),('n3',3300,420),('n4',4020,650),
          ('m0',400,1550),('m1',1400,1450),('m2',2350,1700),('m3',3250,1550),('m4',4050,1530),
          ('s0',450,2770),('s1',1450,2870),('s2',2500,2750),('s3',3400,2830),('s4',4200,2580),
          ('b0',550,3780),('b1',1600,3860),('b2',2600,3720),('b3',3550,3650),('b4',4200,3510),
          ('i0',4750,400),('i1',4520,1120),('i2',4740,1920),('i3',4570,2950),('i4',4780,3860),
          ('e0',5530,600),('e1',5400,1600),('e2',5600,2670),('e3',5400,3700),
          ('nu',2250,180),('ml',2050,1990),('su',2200,2490),('bl',2400,4050),
          ('nm',3650,1080),('ms',3580,2230),('sb',2880,3280)]
    for k,x,y in rows:g.point(k,x,y,'岭谷路口·'+k)
    g.point('C',5020,2340,'内陆谷营地','camp')
    sites=[(780,380),(1750,410),(2780,445),(3650,520),(690,1730),(970,1490),
        (1860,1570),(2790,1620),(3650,1540),(910,2820),(1980,2810),(2980,2790),
        (3800,2700),(1070,3820),(2110,3790),(3070,3680),(3850,3580),
        (4300,880),(4630,1510),(4420,2250),(4400,3240),(4530,3720),
        (5140,480),(5460,1110),(5480,2130),(5500,3200),(5100,3830),
        (300,180),(1400,120),(3100,160),(560,1260),(1500,1820),(3100,1840),
        (450,3120),(1320,2580),(3280,3060),(530,4060),(1680,3570),(3720,3990),
        (4850,850),(5000,1740),(5320,2860),(5100,3440),(2030,290),
        (1730,1880),(2320,2580),(2080,3990),(5740,4000)]
    s=[g.station(*p) for p in sites]
    g.route('北半岛古道','n0',s[0],'n1',s[1],'n2',s[2],'n3',s[3],'n4')
    g.route('北岭短环','n1','nu','n3');g.route('北岸联径','nu',s[43],'n2')
    g.route('中半岛谷路','m0',s[5],'m1',s[6],'m2',s[7],'m3',s[8],'m4')
    g.route('中湾坡环','m0',s[4],'m1');g.route('中岭斜路','m1',s[44],'ml','m3')
    g.route('南半岛牧路','s0',s[9],'s1',s[10],'s2',s[11],'s3',s[12],'s4')
    g.route('南岭高路','s1','su',s[45],'s2')
    g.route('南海岸路','b0',s[13],'b1',s[14],'b2',s[15],'b3',s[16],'b4')
    g.route('南湾外环','b1',s[46],'bl','b3')
    g.route('峡首陆路','n4',s[17],'i1','m4',s[19],'s4',s[20],'b4')
    g.route('北峡首谷','n3','nm','m4');g.route('中峡首谷','m3','ms','s4')
    g.route('南峡首谷','s2','sb','b2')
    g.route('内陆分水岭','i0','i1',s[18],'i2','C','i3',s[21],'i4')
    g.route('东谷外路','i0',s[22],'e0',s[23],'e1',s[24],'e2',s[25],'e3',s[26],'i4')
    g.route('北山口联路','n4',s[39],'i0');g.route('中山口联路','m4',s[40],'e1')
    g.route('东谷南联路','C',s[41],'e2');g.route('南岭联路','i3',s[42],'e3')
    for a,i in [('n0',27),('n1',28),('n3',29),('m0',30),('m1',31),('m3',32),('s0',33),('s1',34),
                ('s3',35),('b0',36),('b1',37),('b3',38),('e3',47)]:g.route('谷端支路',a,s[i])
    surveys=[(730,630,'n0'),(1820,650,'n2'),(3500,220,'n3'),(340,1880,'m0'),
        (1680,1280,'m1'),(2760,1960,'m3'),(720,2550,'s0'),(1760,3120,'s1'),
        (3650,2440,'s4'),(760,3560,'b0'),(2800,4220,'b2'),(3990,3920,'b4'),
        (4640,170,'i0'),(5700,1390,'e1'),(4790,2630,'C'),(5730,3470,'e3')]
    names=['北岸草坡','北岭湖台','峡顶鞍部','西湾岩滩','中湾牧场','内湾高坡','西南崖台','南岭草甸',
           '东峡支谷','南岸浅湾','外海坡地','南岭林缘','北谷上游','东谷林台','中谷湿地','东南台地']
    for (x,y,a),name in zip(surveys,names):g.survey(x,y,name,a)
    fjords=[[(0,790),(850,810),(1700,920),(2750,860),(3450,1000),(3450,1180),(2700,1110),(1650,1170),(650,1010),(0,1030)],
            [(0,2160),(900,2100),(1820,2240),(2880,2150),(3080,2310),(2840,2410),(1750,2390),(800,2320),(0,2390)],
            [(0,3290),(700,3210),(1450,3360),(2080,3240),(2340,3370),(2090,3500),(1400,3500),(600,3420),(0,3500)]]
    g.features={'water_barriers':fjords}
    g.regions=[{'name':'北岸半岛','x':1900,'y':760},{'name':'中湾牧谷','x':1950,'y':1330},
        {'name':'南岸岭地','x':2350,'y':3050},{'name':'内陆长谷','x':5120,'y':1150}]
    g.rationale=['Three unequal fjords prevent direct north-south coastal travel; all cross-region paths go around their heads on land.',
        'Four distinct peninsula path systems feed an asymmetric inland valley and ridge bypass; no repeated nine-cell district layout.',
        'Regional motifs are inspired by medieval Scandinavia; routes and distances are experimental abstractions, not historical reconstruction.']
    return finish(g,26110541)

def terrain(geo,name):
    d=Drawing(name,6000,4300,'#d6dfd5')
    for x,y,rx,ry in [(3700,700,550,450),(3800,2000,490,500),(4050,3140,500,540),(5050,2150,290,1700)]:
        for f in (1,.8,.6):d.path(organic(x,y,rx*f,ry*f,.5),fill='#b8c4b6',stroke='#9fab9d',width=3,opacity=.38)
    for polygon in geo['features']['water_barriers']:d.polygon(polygon,'#7da9b1','#9dbac1',12)
    for x,y in [(1050,620),(2450,1610),(1550,2780),(2850,3750),(4760,1700)]:d.settlement(x,y,200,100,-12,x+y,buildings=12)
    d.text(1950,960,'北峡湾',size=44,fill='#587f8d');d.text(1750,2250,'中峡湾',size=44,fill='#587f8d')
    d.text(1430,3400,'南峡湾',size=44,fill='#587f8d')
    return d.finish()
