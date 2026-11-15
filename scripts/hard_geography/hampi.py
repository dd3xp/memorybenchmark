"""Hampi's southern river-bank city and agricultural hinterland.

Rocky masses divide a sinuous riverside settlement belt from an irregular
royal/craft quarter. Inner passes compete with longer western/eastern bypasses.
No invented historical ferry/bridge chronology is required: all routes stay on
one bank. The south-eastern tank has a completely separate perimeter circuit.
"""
from .common import Landscape


def build():
    g=Landscape('hampi',4600,4000,distance_unit=95)
    points=[
        ('h01',320,1040,'西岸坡口'),('h02',890,1090,'西岸市路'),('h03',1460,1000,'河岸坊口'),
        ('h04',2120,1090,'东市长街'),('h05',2690,840,'岸地院路'),('h06',3130,1310,'东岸弯路'),
        ('h07',3830,1430,'东岸村口'),('h08',4320,1230,'下游岸路'),('h09',430,1600,'西岩外口'),
        ('h10',1240,1520,'西岩隘口'),('h11',1730,1520,'中岩西隘'),('h12',2670,1450,'中岩东隘'),
        ('h13',3020,1740,'东岩北隘'),('h14',3990,1980,'东崖外路'),('h15',360,2320,'西外田路'),
        ('h16',1220,2180,'西岩南口'),('h17',1660,2140,'城西入路'),('h18',2110,2220,'北坊街口'),
        ('h19',2690,2170,'双岩谷口'),('h20',2930,2460,'东岩南口'),('h21',3830,2510,'东田岔口'),
        ('h22',4270,2300,'下游外路'),('h23',660,2780,'西郊商路'),('h24',1110,2640,'作坊街口'),
        ('h25',1530,2630,'西院门路'),('h26',1730,2440,'北西坊路'),('h27',2180,2460,'北东坊路'),
        ('h28',2440,2780,'东院门路'),('h29',2240,3120,'南东坊路'),('h30',1750,3120,'南西坊路'),
        ('h31',1570,2910,'西下坊路'),('h32',2010,2770,'内院街口'),('h33',1130,3180,'西南村路'),
        ('h34',2730,3190,'南渠田路'),('h35',3230,2850,'蓄水地西路'),('h36',3900,2950,'蓄水地东路'),
        ('h37',4380,2820,'东郊商路'),('h38',560,3420,'西南田口'),('h39',1770,3540,'南部原路'),
        ('h40',2510,3540,'南村渠口'),('h41',3150,3520,'蓄水地南西路'),('h42',3960,3540,'蓄水地南东路'),
        ('h43',4370,3460,'东南田口'),('h44',850,2380,'作坊外路'),('h45',1390,1870,'西隘下坡'),
        ('h46',2880,1040,'东岸市尾'),('h47',3500,1350,'东岩北麓'),('h48',3250,2450,'东岩南麓'),
        ('h49',3900,1300,'下游岸台'),('h50',1660,3330,'南工坊路'),('h51',3030,3740,'南渠下路'),
        ('h52',4270,3740,'东南远田'),
    ]
    for key,x,y,name in points:g.point(key,x,y,name)
    g.route('沿岸市路','h01',(610,1030),'h02','h03',(1770,1010),'h04',(2420,990),'h05','h46','h06')
    g.route('下游岸路','h06','h47','h07','h49','h08')
    g.route('西岩外绕','h01',(100,1300),'h09',(320,1940),'h15',(470,2530),'h23','h38')
    g.route('西岩内隘','h02',(1110,1270),'h10','h45','h16','h24','h33')
    g.route('西隘横路','h10',(1470,1430),'h11')
    g.route('中岩西廊','h03',(1630,1240),'h11',(1670,1820),'h17','h25')
    g.route('中岩北廊','h04',(2490,1160),'h12','h05')
    g.route('中岩东廊','h12',(2780,1760),'h19')
    g.route('东岩北廊','h06',(3100,1500),'h13',(3190,1450),'h47')
    g.route('双岩谷路','h13',(2890,1950),'h19')
    g.route('东崖外绕','h07',(3950,1670),'h14','h22','h37','h43','h52')
    g.route('岩南横路','h16','h17','h18','h19','h20','h48','h21','h22')
    g.route('东田岸路','h14',(3910,2260),'h21',(3990,2720),'h36','h37')
    g.route('东郊斜路','h21',(4130,2640),'h37')
    # The urban quarter is compact and internally connected, unlike the
    # dispersed hill-town loops of Orcia or Angkor's long engineered axes.
    g.route('北坊连路','h17','h26','h18','h27','h19')
    g.route('院外街路','h25','h26','h27','h28','h29','h30','h31','h25')
    g.route('内院西路','h26',(1830,2620),'h32','h31')
    g.route('内院东路','h27',(2230,2620),'h32','h28')
    g.route('内院南路','h30',(1880,2930),'h32')
    g.route('西作坊街','h25','h24','h44','h23')
    g.route('岩下作坊路','h44','h16')
    g.route('西南村路','h23',(840,3030),'h33','h38')
    g.route('南坊田路','h33','h50','h30')
    g.route('西南远田路','h38',(1060,3530),'h39','h50')
    g.route('南渠村路','h29','h34','h40','h39')
    g.route('东坊田路','h28',(2800,2800),'h35','h20')
    g.route('蓄水地北路','h35',(3570,2860),'h36')
    g.route('蓄水地西路','h35',(3100,3160),'h41')
    g.route('蓄水地东路','h36',(3940,3220),'h42')
    g.route('蓄水地南路','h41','h42','h43')
    g.route('南渠远路','h34','h41','h51','h52','h43')
    g.route('南村田径','h40','h51')
    g.point('C',1200,2860,'作坊巡测营地','camp')
    g.route('营地商路','h24','C','h33')
    g.route('营地坊路','C','h25','h31')
    for row in [
        (240,1260,'西岸砾滩测点','h01','h09'),(1270,840,'河湾岸地测点','h02','h03'),
        (2360,730,'中岸台地测点','h04','h05'),(3440,1080,'东湾坡地测点','h06','h47'),
        (4210,1430,'下游岸台测点','h07','h08'),(1550,1720,'岩隘测点','h45','h17'),
        (2810,2080,'双岩谷测点','h19'),(4140,2400,'东田测点','h22','h21'),
        (480,2770,'西郊田畴测点','h23'),(940,2420,'作坊地测点','h44','h24'),
        (2050,3150,'南坊测点','h30','h29'),(2400,2680,'院东测点','h27','h28'),
        (490,3580,'西南旱田测点','h38'),(2120,3650,'南部原地测点','h39','h40'),
        (3410,2960,'蓄水岸地测点','h35','h36'),(4100,3860,'东南远田测点','h52')]:g.survey(*row)
    for row in [
        (420,870,'h01'),(750,950,'h02'),(1110,1090,'h02','h03'),(1510,820,'h03'),
        (1940,940,'h04'),(2270,900,'h04'),(2590,660,'h05'),(2880,720,'h46'),
        (3090,1140,'h06'),(3370,1210,'h47'),(3630,1430,'h47','h07'),(4140,1110,'h08','h49'),
        (240,1830,'h09'),(280,2570,'h15'),(780,2590,'h44'),(1160,1890,'h45','h10'),
        (1470,2310,'h17','h24'),(780,3210,'h33'),(370,3190,'h38'),(1430,3420,'h50'),
        (1430,2970,'h31','C'),(1600,2490,'h25','h26'),(1870,2340,'h26'),(2130,2560,'h27','h32'),
        (2340,2340,'h27'),(2510,2560,'h28'),(2630,2870,'h28','h34'),(2330,2960,'h29'),
        (1940,3070,'h30','h32'),(1640,3000,'h31'),(1860,2780,'h32'),(2070,2860,'h32','h29'),
        (2770,1290,'h12'),(2820,1630,'h13'),(3320,1460,'h13','h47'),(4170,1680,'h14'),
        (4070,2150,'h22'),(3600,2530,'h48','h21'),(2920,2740,'h35','h20'),(3230,3070,'h35'),
        (3840,3190,'h36','h42'),(4150,2820,'h37'),(4440,3110,'h37','h43'),(4410,3630,'h52','h43'),
        (3630,3650,'h42','h51'),(3240,3810,'h51'),(2800,3430,'h40','h41'),(2370,3390,'h40')]:g.station(*row)
    g.regions=[{'name':n,'x':x,'y':y} for n,x,y in [
        ('上游岩岸',900,560),('河湾市地',2030,900),('东岸岩麓',3820,1730),('西郊作坊',700,3060),
        ('城坊院地',2040,2900),('南部田畴',2010,3850),('蓄水村地',3650,3460)]]
    g.features={
        'major_water':[{'name':'岩岸大河','width':95,'points':[(-100,720),(480,560),(1050,750),(1500,540),(2030,690),(2530,420),(3120,550),(3400,920),(3890,1060),(4550,870),(4700,1250)]}],
        'rocks':[
            [(500,1570),(730,1480),(1000,1600),(1090,1830),(970,2090),(690,2150),(490,1950)],
            [(1940,1410),(2220,1350),(2470,1540),(2490,1850),(2320,2070),(2020,1990),(1850,1760)],
            [(3230,1590),(3520,1530),(3750,1760),(3710,2140),(3480,2380),(3160,2230),(3070,1910)]],
        'lakes':[[(3330,3100),(3590,3060),(3770,3170),(3700,3350),(3430,3400),(3310,3300)]],
        'urban_precinct':[(1530,2630),(1730,2440),(2180,2460),(2440,2780),(2240,3120),(1750,3120),(1570,2910)],
        'settlements':[(890,1090,210,100,-10),(1460,1000,180,80,8),(2690,840,220,140,18),(3830,1430,120,85,12),
                       (1110,2640,180,130,-15),(2010,2770,390,250,8),(1130,3180,130,90,-15),(2510,3540,150,85,0),(4380,2820,125,100,16)],
        'river_crossing_count':0,
    }
    g.rationale=[
        'A bending northern river bounds a continuous south-bank scenario, rather than bisecting it like Orcia.',
        'Three explicitly drawn rock masses leave two short inner corridors and longer outer bypasses; roads do not pass through the rocks.',
        'A compact, densely connected urban/craft quarter contrasts with sparse river terraces and open agricultural hinterland.',
        'The south-eastern irregular tank has north/south perimeter alternatives; no large orthogonal reservoir/causeway network is copied from Angkor.'
    ]
    return g.finish(251102)


def terrain(geography,name):
    from math import hypot
    from random import Random
    from .drawing import Drawing,organic,smooth
    d=Drawing(name,4600,4000,'#e9dcc3')
    # A rocky northern bank is scenery; the playable network stays south.
    d.path('M-50 80L4650 0V650C4220 900 3960 800 3550 540S3060 170 2590 210S1980 480 1530 300S670 210-50 420Z',fill='#d6c3a6',opacity=.9)
    for i,(cx,cy,rx,ry,a) in enumerate([(480,200,550,260,.2),(1670,190,460,180,-.1),(3120,180,570,210,.1),(4260,390,480,300,-.4)]):
        d.path(organic(cx,cy,rx,ry,i,a),fill='#b89b7e',opacity=.45)
    # Angular terrace fields spread out beyond the compact city.
    for i,p in enumerate([
        [(100,2250),(320,2180),(480,2360),(430,2610),(140,2670)],
        [(490,2940),(790,2800),(930,2960),(710,3260)],
        [(650,3490),(1120,3370),(1240,3690),(730,3820)],
        [(1390,3490),(1650,3370),(1850,3560),(1700,3810),(1350,3790)],
        [(2150,3290),(2510,3210),(2670,3440),(2320,3540)],
        [(2770,3450),(3070,3290),(3230,3480),(3050,3680)],
        [(2860,2650),(3170,2580),(3300,2810),(3020,2930)],
        [(3910,2570),(4200,2440),(4340,2680),(4150,2910)],
        [(4070,3020),(4420,2920),(4510,3260),(4200,3340)],
        [(3890,3610),(4210,3500),(4470,3700),(4310,3930),(4010,3870)],
    ]):d.polygon(p,['#bac29b','#c7caa5','#b2bf96'][i%3],'#9da77e',3,.65)
    for index,rock in enumerate(geography['features']['rocks']):
        d.polygon([(x+25,y+36) for x,y in rock],'#ad9278',opacity=.2)
        d.polygon(rock,'#c0a087','#9d826d',4,.83)
        clip='M'+'L'.join(f'{x},{y}' for x,y in rock)+'Z'
        d.parts.append(f'<defs><clipPath id="rock-{index}"><path d="{clip}"/></clipPath></defs><g clip-path="url(#rock-{index})">')
        rng=Random(681+index);xs=[x for x,y in rock];ys=[y for x,y in rock]
        cx=sum(xs)/len(xs);cy=sum(ys)/len(ys)
        for j in range(17):
            x=rng.uniform(min(xs)+80,max(xs)-80);y=rng.uniform(min(ys)+100,max(ys)-100)
            rx=rng.randint(55,125);ry=rng.randint(45,95)
            d.path(organic(x,y,rx,ry,j,rng.uniform(-.5,.5)),fill=['#b18c74','#c2a58a','#b7977e'][j%3],stroke='#a1856f',width=3,opacity=.72)
            d.path(f'M{x-rx*.5:.1f} {y:.1f}q{rx*.55:.1f} {-ry*.6:.1f} {rx:.1f} {-ry*.3:.1f}',stroke='#e1c9a8',width=6,opacity=.58)
        d.parts.append('</g>')
    for water in geography['features']['major_water']:d.river(water['points'],water['width'],colour='#739fa3')
    for p in geography['features']['lakes']:
        d.polygon([(x+(x-3540)*.07,y+(y-3250)*.07) for x,y in p],'#bac7aa')
        d.polygon(p,'#82aba7','#6f9892',5)
    d.path(smooth([(3990,1450),(4180,2020),(4120,2530),(3920,2870),(3700,3100)]),stroke='#9db8a0',width=12,opacity=.7)
    for i,row in enumerate(geography['features']['settlements']):d.settlement(*row,800+i,buildings=55 if i==5 else 25)
    precinct=geography['features']['urban_precinct']
    d.polygon(precinct,'#d8c3a6',opacity=.22)
    # Separate short masonry segments leave every authored street entrance open.
    for (x,y),(u,v) in zip(precinct,precinct[1:]+precinct[:1]):
        length=hypot(u-x,v-y);f=min(.24,65/length)
        d.path(f'M{x+(u-x)*f:.1f},{y+(v-y)*f:.1f}L{u-(u-x)*f:.1f},{v-(v-y)*f:.1f}',stroke='#ad967b',width=16,opacity=.65)
    d.text(1950,490,'岩岸大河',size=38,fill='#5d8c8d',angle=8)
    d.text(3530,3260,'蓄水地',size=33,fill='#557f7e')
    return d.finish()
