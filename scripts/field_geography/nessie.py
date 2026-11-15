"""One long loch, branched western glens and a separate eastern ridge circuit."""
from .common import Landscape,finish
from scripts.hard_geography.drawing import Drawing,smooth
from scripts.hard_geography.review import sampled_curve

def build():
    g=Landscape('nessie',3200,2400,distance_unit=150)
    rows=[('n0',2100,280,'北口岸路'),('w1',1790,450,'西北湖湾'),('w2',1550,740,'西岸杉坡'),
          ('w3',1330,1040,'西岸峡口'),('w4',1130,1320,'西南坡口'),('w5',900,1610,'南湾西路'),
          ('s0',900,2010,'南口西岸'),('S0',1030,2160,'南口绕岸'),
          ('e5',1260,2050,'南湾东路'),('e4',1570,1750,'东南湖岬'),('e3',1860,1430,'东岸山路'),
          ('e2',2090,1120,'东岸岭口'),('e1',2310,810,'东北湖湾'),('e0',2480,460,'北口东岸'),
          ('v0',600,1570,'下支谷口'),('v1',550,1200,'西谷林岔'),('v2',720,850,'西谷上岔'),
          ('v3',1060,570,'支谷鞍口'),('v4',1390,340,'西岭北口'),
          ('h0',2700,700,'东岭北口'),('h1',2600,1150,'东岭高岔'),('h2',2320,1610,'东岭南岔'),('h3',1900,2030,'东南坡路')]
    for row in rows:g.point(*row)
    g.point('C',2720,280,'北湾巡测营地','camp')
    s=[g.station(*row) for row in [(1930,365),(1670,590),(1435,890),(1210,1180),(1000,1470),(900,1840),
       (1140,2140),(1420,1900),(1715,1580),(1990,1270),(2190,965),(2400,630),
       (650,1410),(610,1020),(900,700),(1230,445),(1300,655),
       (2690,940),(2460,1380),(2100,1850),(2400,1160),(1830,1900),(2400,290),(2840,590),
       (1470,190),(820,390),(320,1040),(450,1700),(640,2060),(1190,2310),(2170,2210),(2890,1310)]]
    g.route('西岸长路','n0',s[0],'w1',s[1],'w2',s[2],'w3',s[3],'w4',s[4],'w5',s[5],'s0','S0')
    g.route('东岸长路','S0',s[6],'e5',s[7],'e4',s[8],'e3',s[9],'e2',s[10],'e1',s[11],'e0','n0')
    g.route('西侧支谷','w5','v0',s[12],'v1',s[13],'v2',s[14],'v3',s[15],'v4','w1')
    g.route('峡口入谷','w3','v1')
    g.route('上谷联坡','w2',s[16],'v3')
    g.route('东岭长环','e0','h0',s[17],'h1',s[18],'h2',s[19],'h3','e5')
    g.route('岭口联路','e2',s[20],'h1')
    g.route('东南下坡','e4',s[21],'h3')
    g.route('北口营路','n0',s[22],'C','e0')
    g.route('营地岭路','C',s[23],'h0')
    for a,b in [('v4',s[24]),('v3',s[25]),('v1',s[26]),('v0',s[27]),('s0',s[28]),('S0',s[29]),('h3',s[30]),('h1',s[31])]:g.route('支谷或坡侧站径',a,b)
    for row in [(2000,155,'北湾岸地测点','n0'),(2600,500,'北口东岸测点','e0'),
                (1600,425,'西北湖岬测点','w1'),(2400,820,'东北坡地测点','e1','h0'),
                (1120,875,'西峡坡地测点','w3'),(2090,1530,'东岭岸坡测点','e3','h2'),
                (810,1230,'西谷林地测点','v1','w3'),(2300,2250,'南湾东坡测点',s[30]),
                (430,750,'上谷林缘测点',s[26]),(510,1890,'下谷湿地测点',s[27]),
                (680,2260,'南岸沉积测点',s[28]),(2760,1600,'高岭林地测点',s[31])]:g.survey(*row)
    lake=[(2140,420),(2260,450),(2280,570),(2120,830),(1880,1110),(1650,1390),
          (1400,1650),(1220,1860),(1090,1880),(1040,1780),(1170,1530),(1390,1260),
          (1630,1000),(1840,730),(2010,490)]
    g.features={'lakes':[sampled_curve([*lake,lake[0]],subdivisions=8)]}
    g.regions=[{'name':'西侧支谷','x':720,'y':1490},{'name':'西岸峡地','x':1280,'y':1150},
               {'name':'东岭长环','x':2750,'y':1760},{'name':'南口','x':940,'y':2220}]
    g.rationale=['Preserve a single elongated loch. Land routes pass around its two ends; no artificial cross-lake bridge or ferry shortcut.',
                 'The western glens form uneven branching alternatives while the eastern ridge is a longer, separately connected circuit, rather than two equal ladder rails.',
                 'Camp, survey targets and mixed through/spur stations reach inland glens and high ground, not only the immediate shoreline.']
    return finish(g,26110511,normal=True)

def terrain(geo,name):
    d=Drawing(name,3200,2400,'#e2e7d9')
    d.forest([(80,240),(920,80),(1540,210),(1660,600),(1400,930),(980,1290),(790,1840),(200,2070)],811,colour='#b4c0a0',trees=150)
    d.forest([(2430,340),(2990,420),(3140,1160),(3060,2210),(2290,2330),(1920,2040),(2280,1510),(2460,970)],812,colour='#b8c5a7',trees=120)
    for shift in (0,90,180):
        d.path(smooth([(400+shift,250),(670+shift,570),(510+shift,1050),(670+shift,1450),(520+shift,1810)]),stroke='#94a280',width=3,opacity=.35)
        d.path(smooth([(2680+shift,430),(2810+shift,980),(2510+shift,1560),(2180+shift,2120)]),stroke='#8d9d7e',width=3,opacity=.4)
    for p in geo['features']['lakes']:d.polygon(p,'#77a8aa','#6a9697',4)
    d.path(smooth([(2130,610),(1870,990),(1630,1280),(1370,1580),(1170,1790)]),stroke='#bad0c8',width=4,opacity=.48)
    d.text(1660,1280,'长湖',size=42,fill='#e1e6d6',angle=-52)
    return d.finish()
