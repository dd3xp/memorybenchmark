"""Angkor: reservoir embankments, a moated city and dispersed canal settlements.

The geometry deliberately follows engineered axes and water-body perimeters.
It is authored regional cartography, not a claim that each represented road and
crossing was contemporaneous or surveyed at its drawn position in 1200–1250.
"""
from .common import Landscape


def rect(x,y,u,v):return [(x,y),(u,y),(u,v),(x,v)]


def moat(x,y,u,v,thickness):
    t=thickness
    return [rect(x,y,u,y+t),rect(x,v-t,u,v),rect(x,y+t,x+t,v-t),rect(u-t,y+t,u,v-t)]


def build():
    g=Landscape('angkor',6800,4600,distance_unit=125)
    points=[
        ('a01',260,720,'西北村路'),('a02',1150,690,'北田村口'),('a03',2260,640,'北池农路'),
        ('a04',2920,840,'北林院路'),('a05',3500,1060,'城北外路'),('a06',4320,560,'东北林路'),
        ('a07',4860,430,'东池北田'),('a08',5760,400,'东北村路'),('a09',6560,430,'东北远田'),
        ('a10',2640,2000,'城西外路'),('a11',4380,2000,'城东外路'),('a12',3500,2860,'城南外路'),
        ('a13',2700,2860,'城西南田路'),('a14',4380,2860,'城东南田路'),
        ('a15',2600,1060,'西北堤岔'),('a16',4380,1060,'东北堤岔'),
        ('wNW',220,1190,'西池西北堤角'),('wN',1350,1190,'西池北堤'),('wNE',2510,1190,'西池东北堤角'),
        ('wE',2510,1710,'西池东堤'),('wSE',2510,2260,'西池东南堤角'),('wS',1350,2260,'西池南堤'),
        ('wSW',220,2260,'西池西南堤角'),('wW',220,1710,'西池西堤'),
        ('eNW',4490,590,'东池西北堤角'),('eN',5540,590,'东池北堤'),('eNE',6560,590,'东池东北堤角'),
        ('eE',6560,1100,'东池东堤'),('eSE',6560,1610,'东池东南堤角'),('eS',5540,1610,'东池南堤'),
        ('eSW',4490,1610,'东池西南堤角'),('eW',4490,1100,'东池西堤'),
        ('cN',3500,1500,'北门内路'),('cE',3950,2000,'东门内路'),('cS',3500,2480,'南门内路'),
        ('cW',3050,2000,'西门内路'),('cNW',3080,1600,'城内西北路'),('cNE',3910,1600,'城内东北路'),
        ('cSE',3910,2420,'城内东南路'),('cSW',3080,2420,'城内西南路'),('cC',3500,2000,'城内轴路'),
        ('cR',3710,1780,'东北院路'),('cP',3270,2200,'西南坊路'),
        ('s01',340,2820,'西池下田'),('s02',1340,2890,'西渠村口'),('s03',2210,2800,'西南城畴'),
        ('s04',2400,3450,'南苑西路'),('s05',2850,3500,'南苑西堤口'),('s06',4100,3500,'南苑东堤口'),
        ('s07',4390,3380,'东渠村路'),('s08',5140,2930,'东部渠岔'),('s09',5900,2370,'东原田路'),
        ('s10',6460,2840,'东原村口'),('s11',6450,3560,'东南渠路'),('s12',5700,3910,'东南稻田'),
        ('s13',4630,4100,'南渠连路'),('s14',4080,4190,'南苑东南田'),('s15',2750,4190,'南苑西南田'),
        ('s16',1780,3910,'西南田路'),('s17',650,3920,'西南远田'),('s18',410,3350,'西渠下村'),
        ('s19',1300,3470,'西渠中村'),('s20',5380,3470,'东南村畴'),('s21',5050,2170,'东池下村'),
        ('s22',5950,1750,'东池外田'),('s23',6140,4330,'东南远村'),('s24',3650,4400,'南苑下村'),
        ('tNW',2850,2930,'南苑西北堤角'),('tNE',4100,2930,'南苑东北堤角'),
        ('tSE',4100,4080,'南苑东南堤角'),('tSW',2850,4080,'南苑西南堤角'),
        ('tW',3200,3500,'南苑西内路'),('tC',3470,3500,'南苑内路'),('tE',3760,3500,'南苑东内路'),
        ('tN',3470,3270,'南苑北院路'),('tS',3470,3720,'南苑南院路'),
    ]
    for key,x,y,name in points:g.point(key,x,y,name)
    g.route('北部村路','a01','a02',(1740,740),'a03','a04','a05')
    g.route('北林院道','a04',(3610,680),'a06','a07','a08','a09')
    g.route('北田堤道','a03','a15','a05')
    g.route('西池堤道','wNW','wN','wNE','wE','wSE','wS','wSW','wW','wNW')
    g.route('西北入池路','a01','wNW')
    g.route('北田入池路','a02','wN')
    g.route('北池岔路','a03','wNE','a15')
    g.route('西池城路','wE','a10')
    g.route('西池南路','wSE','s03')
    g.route('城外北堤','a15','a05',(4050,1060),'a16')
    g.route('城外东堤','a16',(4380,1540),'a11','a14')
    g.route('城外南堤','a14','a12','a13')
    g.route('城外西堤','a13',(2640,2490),'a10',(2640,1430),'a15')
    for a,b in [('a05','cN'),('a10','cW'),('a11','cE'),('a12','cS')]:g.route('城门堤道',a,b,tag='causeway')
    g.route('城内南北轴','cN','cC','cS')
    g.route('城内东西轴','cW','cC','cE')
    g.route('城内坊路','cN','cNW','cW','cSW','cS','cSE','cE','cNE','cN')
    g.route('东北院路','cNE','cR','cC')
    g.route('西南坊路','cW','cP','cS')
    g.route('东池堤道','eNW','eN','eNE','eE','eSE','eS','eSW','eW','eNW')
    g.route('东北入池路','a06','eNW','a07')
    g.route('北田入东池','a08','eN')
    g.route('东北外堤','a09','eNE')
    g.route('东池城路','eW','a16')
    g.route('东池西南路','eSW','a11')
    g.route('东池南村路','eS','s22','eSE')
    g.route('东城渠路','a11','s21',(5520,2270),'s09','s10')
    g.route('东原斜田路','s22','s09',(6190,2950),'s11','s10')
    g.route('东渠下路','s21','s08','s20','s12','s23','s11')
    g.route('城南东渠路','a14','s07','s13','s14')
    g.route('东渠横村路','s07',(4830,3450),'s20')
    g.route('东村连路','s08',(4770,3150),'s07')
    g.route('南部堤路','s13',(5170,4100),'s12')
    g.route('西池下路','wSW','s01','s18','s17')
    g.route('西渠田路','wS','s02','s19','s16','s17')
    g.route('西南横田路','s01','s02','s03','a13')
    g.route('西渠中村路','s18','s19','s04','s03','a13','a12')
    g.route('西南斜田路','s04',(2120,3690),'s16','s15','s24','s14')
    g.route('南苑西田路','s04','s05')
    g.route('南苑外堤','tNW','tNE','s06','tSE','tSW','s05','tNW')
    g.route('南苑城路','a13','tNW','a12','tNE','a14')
    g.route('南苑南村路','tSW','s15')
    g.route('南苑东南路','tSE','s14')
    g.route('南苑东村路','s06','s07')
    g.route('南渠斜村路','s24','s13')
    g.route('南苑西堤道','s05','tW',tag='causeway')
    g.route('南苑东堤道','s06','tE',tag='causeway')
    g.route('南苑内轴','tW','tC','tE')
    g.route('南苑院路','tN','tW','tS','tE','tN','tC','tS')
    g.point('C',4720,2580,'东渠巡测营地','camp')
    g.route('营地渠路','a14','C','s21')
    g.route('营地村路','C','s08')
    for row in [
        (250,450,'西北林地测点','a01'),(1640,790,'北部田地测点','a02','a03'),
        (510,2160,'西池下岸测点','wSW','wS'),(2200,2350,'西池东南测点','wSE','s03'),
        (3000,900,'北林院地测点','a04','a15'),(3440,2230,'城内坊地测点','cC','cS'),
        (4360,820,'东北林地测点','a16','a06'),(5830,680,'东池北岸测点','eN'),
        (6660,1900,'东池远田测点','eSE','s10'),(4750,2020,'东城渠地测点','a11','s21'),
        (6050,2610,'东原村畴测点','s09','s10'),(5190,3190,'东渠村地测点','s08','s20'),
        (3550,3650,'南苑院地测点','tC','tS'),(2100,3380,'西南聚落测点','s03','s04'),
        (840,4190,'西南远田测点','s17','s16'),(5580,4380,'东南远村测点','s12','s23')]:g.survey(*row)
    for row in [
        (140,1460,'wNW','wW'),(180,2030,'wSW'),(760,1110,'wNW','wN'),(1790,1090,'wN','wNE'),
        (2430,1480,'wE'),(2420,1970,'wE','wSE'),(720,2390,'wSW','wS'),(1910,2410,'wS','wSE'),
        (840,500,'a02'),(1910,470,'a03'),(2910,600,'a04'),(3980,430,'a06'),
        (4920,610,'eNW','eN'),(6130,510,'eN','eNE'),(6630,960,'eE'),(6620,1510,'eSE'),
        (6040,1630,'eS','eSE'),(4760,1700,'eSW'),
        (3160,1690,'cNW','cW'),(3780,1500,'cNE'),(4000,1790,'cNE','cE'),(3810,2330,'cSE'),
        (3240,2430,'cSW','cS'),(3050,2260,'cW','cSW'),(3360,1820,'cC','cN'),(3650,2130,'cC','cE'),
        (2500,2590,'a10','a13'),(4270,2520,'a11','a14'),(3220,1110,'a05','a15'),(4520,1830,'a11'),
        (3230,3350,'tW','tN'),(3650,3670,'tS','tE'),(2670,3780,'s05','tSW'),(4250,3830,'s06','tSE'),
        (180,3020,'s01','s18'),(970,2770,'s02'),(1760,3090,'s02','s03'),(1030,3700,'s17','s16'),
        (1970,3720,'s16'),(2430,4300,'s15','s16'),(4820,2290,'s21','C'),(5580,2030,'s21','s09'),
        (6320,2190,'s09','s22'),(6650,3140,'s10','s11'),(5920,3350,'s20','s11'),(5410,3700,'s20','s12'),
        (4980,4380,'s13','s12'),(3770,4510,'s24')]:g.station(*row)
    reservoirs=[rect(350,1350,2350,2100),rect(4650,750,6400,1450)]
    city_moat=moat(2800,1300,4200,2700,120)
    temple_moat=moat(3000,3050,3950,3950,120)
    g.regions=[{'name':n,'x':x,'y':y} for n,x,y in [
        ('北部林村',2150,330),('西池堤畴',1420,1030),('东池堤畴',5500,1800),('城内轴坊',3510,2340),
        ('西渠聚落',980,3210),('东渠聚落',5360,2710),('南苑村地',3540,4200),('南部远田',1900,4380),('东南稻田',6100,4020)]]
    g.features={'major_water':[],'lakes':reservoirs,'water_barriers':city_moat+temple_moat,
                'enclosures':[[2800,1300,4200,2700,120],[3000,3050,3950,3950,120]],
                'causeways':[['a05','cN'],['a10','cW'],['a11','cE'],['a12','cS'],['s05','tW'],['s06','tE']],
                'channels':[[ (1410,2260),(1400,2890),(1360,3470),(1840,3910),(1800,4680)],
                            [(5110,1690),(5110,2170),(5200,2930),(5440,3470),(5760,3910),(6200,4330)],
                            [(4380,570),(4440,1060),(4440,2000),(4440,2860),(4450,3380),(4690,4100)]],
                'settlements':[(1150,690,170,100,5),(2920,840,135,90,-7),(5760,400,140,80,6),
                               (3500,2000,320,280,0),(1340,2890,240,135,9),(2210,2800,150,100,-10),
                               (5140,2930,250,120,-8),(6460,2840,145,95,5),(1780,3910,180,100,4),
                               (3650,4400,170,80,4),(5700,3910,180,130,-10)],
                'river_crossing_count':0,'moat_causeway_count':6}
    g.rationale=[
        'Two long rectangular barays interrupt regional movement and create north-versus-south embankment choices.',
        'A moated square city has four fixed causeway entrances and an internal axial/perimeter network, with an independent exterior bypass.',
        'A separate southern enclosure uses a smaller two-entrance circuit, rather than repeating the same district module.',
        'Long canal-side settlement routes extend far south and east of the monuments; the camp is an eastern rural post, not a central hub.'
    ]
    return g.finish(251103,minimum_replica_distance=1250)


def terrain(geography,name):
    from .drawing import Drawing,smooth
    d=Drawing(name,6800,4600,'#e4e8ca')
    d.forest([(150,70),(1680,90),(2460,230),(2990,380),(3310,710),(3060,1090),(2630,1080),(2380,750),(1450,530),(550,840),(170,610)],91,'#adbf96',trees=260)
    d.forest([(3560,40),(4620,30),(4850,240),(4500,480),(4180,780),(3840,670),(3520,450)],92,'#a7bd94',trees=130)
    # Parcel orientation follows long embankments/irrigation reaches; unequal
    # rural blocks surround the monuments instead of nine repeated settlements.
    for i,p in enumerate([
        [(150,2450),(720,2460),(730,2730),(220,2750)],[(760,2460),(1240,2450),(1220,2760),(800,2730)],
        [(1470,2500),(2000,2490),(2050,2710),(1490,2740)],[(470,2940),(1000,2980),(930,3270),(470,3240)],
        [(1500,3020),(1930,3030),(1930,3370),(1500,3340)],[(680,3500),(1110,3480),(1240,3780),(740,3770)],
        [(1370,3570),(1740,3610),(1590,3860),(1220,3810)],[(1850,3450),(2280,3470),(2310,3750),(1890,3780)],
        [(1000,4060),(1500,4050),(1540,4410),(1080,4450)],[(2010,3980),(2520,3970),(2550,4390),(2080,4410)],
        [(4550,1780),(5000,1800),(4990,2070),(4580,2060)],[(5220,1830),(5710,1810),(5790,2130),(5250,2140)],
        [(6080,1830),(6510,1810),(6510,2150),(6110,2150)],[(5420,2470),(5870,2470),(5900,2790),(5500,2790)],
        [(5800,2930),(6280,2950),(6310,3270),(5840,3250)],[(4740,3580),(5220,3550),(5300,3870),(4800,3900)],
        [(5510,3550),(5910,3550),(5990,3820),(5610,3800)],[(6070,3680),(6520,3650),(6550,4030),(6150,4060)],
        [(4750,4160),(5280,4170),(5370,4460),(4820,4480)],[(5450,4190),(5870,4160),(6050,4460),(5550,4480)],
    ]):
        d.polygon(p,['#c8d1a3','#b9c89b','#d2d7ac','#c1cda1'][i%4],'#9bac84',4,.72)
        x1,y1=p[0];x2,y2=p[1];x3,y3=p[2];x4,y4=p[3]
        for f in (.33,.66):
            d.path(f'M{x1+(x2-x1)*f:.1f},{y1+(y2-y1)*f:.1f}L{x4+(x3-x4)*f:.1f},{y4+(y3-y4)*f:.1f}',stroke='#9aaf87',width=3,opacity=.55)
    for p in geography['features']['lakes']:
        x,y=p[0];u,v=p[2]
        d.polygon(rect(x-48,y-48,u+48,v+48),'#bec89f','#9ea987',7)
        d.polygon(p,'#8ab6ad','#6e9992',6)
        d.path(f'M{x+80},{y+80}H{u-80}M{x+80},{y+115}H{u-150}',stroke='#bfd6bd',width=5,opacity=.5)
    for x,y,u,v,t in geography['features']['enclosures']:
        d.polygon(rect(x-36,y-36,u+36,v+36),'#c9d1aa','#a8b28c',5)
        for p in moat(x,y,u,v,t):d.polygon(p,'#91b7a8','#7c9e90',3)
        d.polygon(rect(x+t+20,y+t+20,u-t-20,v-t-20),'#d9dfbb','#a7b08d',9)
    for points in geography['features']['channels']:
        d.path(smooth(points),stroke='#aec6a2',width=32,opacity=.65)
        d.path(smooth(points),stroke='#89afa0',width=13,opacity=.9)
    for i,row in enumerate(geography['features']['settlements']):d.settlement(*row,1200+i,buildings=75 if i==3 else 28)
    # Small central architectural footprints orient the eye without revealing a
    # station type or processing relation. Causeways remain visibly open.
    for x,y,size in [(3500,1940,72),(3470,3500,110)]:
        d.polygon(rect(x-size,y-size,x+size,y+size),'#b7b293','#8b957b',5)
        for s in (.64,.3):d.polygon(rect(x-size*s,y-size*s,x+size*s,y+size*s),'#c4bea1','#8e977b',4)
    loc=geography['locations']
    for a,b in geography['features']['causeways']:
        p,q=loc[a],loc[b];line=f'M{p["x"]},{p["y"]}L{q["x"]},{q["y"]}'
        d.path(line,stroke='#939b7c',width=47);d.path(line,stroke='#e2dfbc',width=33)
    d.text(1350,1740,'西大池',size=62,fill='#618a83',opacity=.7)
    d.text(5530,1140,'东大池',size=57,fill='#618a83',opacity=.7)
    return d.finish()
