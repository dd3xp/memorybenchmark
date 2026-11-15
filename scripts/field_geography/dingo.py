"""K'gari-inspired rainforest hub, separate inland lakes and an eastern coast road."""
from .common import Landscape,finish
from scripts.hard_geography.drawing import Drawing,smooth
from scripts.hard_geography.review import sampled_curve

def build():
    g=Landscape('dingo',3000,2400,distance_unit=150)
    rows=[('c0',2430,220,'北沙岸'),('c1',2500,650,'北岸路口'),('c2',2430,1110,'中岸路口'),
          ('c3',2480,1640,'南岸路口'),('c4',2380,2140,'南沙岸'),
          ('i0',1630,910,'北林路口'),('i1',1710,520,'北岭林口'),('i2',1980,1250,'东林路口'),('i3',1770,1680,'南林路口'),
          ('w0',840,1330,'西溪林口'),('w1',530,1600,'西溪下口'),('w2',400,1930,'西侧湿地'),
          ('a0',1260,380,'北湖东脊'),('a1',820,270,'北湖西脊'),('a2',550,570,'北湖西坡'),
          ('a3',730,920,'北湖南坡'),('a4',1100,930,'北湖林口'),
          ('b0',2020,300,'东湖上脊'),('b1',2280,450,'东湖沙脊'),('b2',2240,920,'东湖南路'),('b3',1860,960,'东湖林岔'),
          ('d0',1320,1570,'南湖北岸'),('d1',730,1730,'南湖西林'),('d2',900,2100,'南湖南岸'),('d3',1370,2140,'南湖东岸')]
    for row in rows:g.point(*row)
    g.point('C',1370,1240,'雨林巡测营地','camp')
    s=[g.station(*row) for row in [(2460,430),(2460,875),(2455,1390),(2430,1880),
       (2180,290),(2330,560),(2240,1110),(2150,1200),(1510,1080),(1680,700),(1490,445),
       (1020,300),(670,410),(610,760),(920,930),(1360,920),(1080,1290),(700,1460),(530,1820),
       (1050,1540),(760,1970),(1150,2120),(1380,1840),(1650,1530),(2070,1660),(2090,2010),
       (350,520),(690,120),(1740,240),(1960,1000),(500,2160),(1630,2190)]]
    g.route('海岸长路','c0',s[0],'c1',s[1],'c2',s[2],'c3',s[3],'c4')
    g.route('营地北林路','C',s[8],'i0',s[9],'i1',s[10],'a0')
    g.route('营地东林路','C','i2',s[7],'c2')
    g.route('营地南林路','C',s[23],'i3',s[24],'c3')
    g.route('西溪林道','C',s[16],'w0',s[17],'w1',s[18],'w2')
    g.route('北湖西环','a0',s[11],'a1',s[12],'a2',s[13],'a3',s[14],'a4')
    g.route('北湖东坡','a0',(1320,650),'a4')
    g.route('北湖南林','a3','w0')
    g.route('北湖营路','a4',s[15],'i0')
    g.route('北沙脊路','i1','b0',s[4],'c0')
    g.route('东湖沙岸','b0','b1',s[5],'c1')
    g.route('东湖下路','i0','b3','b2',s[6],'c2')
    g.route('东湖林路','b3','i2')
    g.route('营地南湖路','C','d0',s[19],'d1','w1')
    g.route('南湖西岸','d1',s[20],'d2',s[21],'d3',s[22],'d0')
    g.route('南湖东林','d0','i3')
    g.route('南部沙脊','i3',s[25],'c4')
    for a,b in [('a2',s[26]),('a1',s[27]),('i1',s[28]),('b3',s[29]),('w2',s[30]),('d3',s[31])]:g.route('林缘或沙脊站径',a,b)
    for row in [(520,300,'北湖西坡测点',s[26]),(2540,250,'北部海岸测点',s[0]),
                (450,1080,'雨林西缘测点','a3','w0'),(2080,1030,'东湖林地测点',s[29]),
                (970,1170,'溪畔雨林测点','w0'),(2350,820,'东湖沙岸测点','b2','c1'),
                (2560,1320,'海岸沙地测点','c2','c3'),(2220,2220,'南部海岸测点','c4'),
                (340,2040,'西侧湿地测点',s[30]),(980,2260,'南湖沉积测点','d2',s[21]),
                (1720,1940,'南岭沙脊测点',s[31]),(1520,250,'内陆高脊测点',s[28])]:g.survey(*row)
    polygons=[[(920,390),(1050,400),(1150,470),(1140,610),(1040,740),(870,760),(740,680),(730,540),(800,440)],
              [(2000,425),(2100,450),(2170,550),(2150,720),(2080,850),(1960,845),(1870,740),(1860,580),(1920,470)],
              [(1060,1660),(1160,1680),(1250,1760),(1260,1850),(1160,1960),(1040,1970),(930,1900),(910,1780),(970,1700)]]
    g.features={'lakes':[sampled_curve([*p,p[0]],subdivisions=8) for p in polygons],
                'water_barriers':[[(2700,-80),(2690,300),(2640,600),(2700,1000),(2650,1500),(2730,2480),(3100,2480),(3100,-80)]]}
    g.regions=[{'name':'北部湖林','x':950,'y':570},{'name':'内陆雨林','x':1320,'y':1400},
               {'name':'东岸沙脊','x':2510,'y':1510},{'name':'南湖','x':1090,'y':1820}]
    g.rationale=['Replace the old parallel-rail map with a central rainforest camp linked radially to a long eastern coast road and three separated lake circuits.',
                 'Northern lake and sand-ridge routes reconnect differently from the southern lake and western creek paths; no repeated district block.',
                 'Lake and sea polygons are defined before final placement checks. Every processing station and survey point stays on land.']
    return finish(g,26110512,normal=True)

def terrain(geo,name):
    d=Drawing(name,3000,2400,'#eae1c2')
    d.forest([(120,120),(1110,100),(1440,470),(1780,810),(2050,1170),(1950,1600),(1450,1940),(700,2230),(170,1990)],912,colour='#acbd96',trees=180)
    d.forest([(1330,190),(1700,250),(1870,620),(1800,1040),(1510,1170),(1250,810)],913,colour='#a4b58d',trees=65)
    for points in [[(2230,100),(2390,470),(2260,1010),(2360,1540),(2240,2170)],
                   [(2330,100),(2480,480),(2350,1000),(2460,1580),(2340,2250)],
                   [(2140,1510),(2030,1750),(2180,2060),(2110,2350)]]:
        d.path(smooth(points),stroke='#c0ae80',width=3,opacity=.55)
    for i,p in enumerate(geo['features']['lakes']):
        d.polygon(p,['#86b6af','#75aaa7','#8cb8ae'][i],'#f1e5be',22)
        d.polygon(p,'none','#7ca294',2)
    for p in geo['features']['water_barriers']:
        d.polygon(p,'#87b8b3','#f2e6bf',40)
    d.path(smooth([(400,1930),(550,1670),(810,1450),(1030,1320),(1240,1300)]),stroke='#93b2a1',width=8,opacity=.7)
    d.text(2810,1280,'海域',size=40,fill='#e6edda',angle=90)
    return d.finish()
