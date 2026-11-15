"""A complete small volcanic monument: rim circuit, Boca breach and lava apron."""
from scripts.field_geography.common import Landscape,finish
from scripts.hard_geography.drawing import Drawing,organic,smooth

def build():
    g=Landscape('capulin',2200,1700,distance_unit=150)
    for row in [('q0',980,300,'西北缘'),('q1',1300,150,'北缘'),('q2',1700,250,'东北缘'),
                ('q3',1900,520,'东缘'),('q4',1740,900,'东南缘'),('q5',1370,1080,'南缘'),
                ('q6',980,940,'西南缺口'),('q7',830,600,'西缘'),('b0',300,1200,'西熔岩口'),
                ('b1',600,1280,'下熔岩岔口'),('b2',940,1300,'南坡路口'),('b3',1200,1460,'入口东岔'),
                ('b4',470,850,'熔岩上口'),('b5',340,540,'西坡台地')]:g.point(*row)
    g.point('C',900,1530,'坡脚营地','camp')
    s=[g.station(*p) for p in [(1120,225),(1500,200),(1820,365),(1820,715),(1560,990),(1180,1020),
        (890,790),(905,435),(440,1240),(770,1290),(1080,1380),(705,1050),
        (420,1030),(405,695),(640,410),(225,960)]]
    g.route('环缘步道','q0',s[0],'q1',s[1],'q2',s[2],'q3',s[3],'q4',s[4],'q5',s[5],'q6',s[6],'q7',s[7],'q0')
    g.route('熔岩坡脚路','b0',s[8],'b1',s[9],'b2',s[10],'b3','C','b2')
    g.route('缺口下坡路','q6',s[11],'b1')
    g.route('熔岩沟路','b0',s[12],'b4',s[13],'b5',s[14],'q0')
    g.route('坡顶横径','b4','q7')
    g.route('南坡联径','b2','q5')
    g.route('西侧熔岩支路','b4',s[15])
    for row in [(1330,320,'北缘地层','q1'),(1690,570,'东缘地层','q3'),(1510,1260,'南坡剖面','q5'),
                (1080,1180,'缺口沉积','q6','b2'),(260,1410,'下熔岩测点','b0'),
                (210,710,'西坡土壤','b5'),(640,660,'熔岩沟测点','b4','q7'),(1920,1080,'东坡测点','q4')]:g.survey(*row)
    g.features={'rocks':[[(1130,405),(1370,345),(1590,425),(1650,655),(1490,840),(1200,800),(1070,620)]]}
    g.regions=[{'name':'火山环缘','x':1480,'y':100},{'name':'熔岩坡地','x':475,'y':1510},{'name':'缺口坡道','x':630,'y':910}]
    g.rationale=['One bounded volcanic monument, not a crop from a much larger scenic region.',
        'A rim circuit surrounds an inaccessible crater interior; its western breach connects to a separate irregular lava-apron network.',
        'Through-stations on rim and apron, one service spur, and unequal slope links make this graph distinct from forest banks and serial lakes.']
    return finish(g,26110531)

def terrain(geo,name):
    d=Drawing(name,2200,1700,'#e0ddc6')
    for rx,ry,col in [(690,610,'#b8b391'),(610,530,'#c6b994'),(535,445,'#b39f7e'),(440,350,'#a58c71')]:
        d.path(organic(1370,600,rx,ry,.3),fill=col,opacity=.65)
    d.polygon(geo['features']['rocks'][0],'#827466','#6f6b60',3,.9)
    for pts in [[(220,1120),(400,800),(510,680),(670,730)],[(260,1320),(530,1170),(640,870),(850,800)],
                [(480,1470),(740,1360),(920,1150)],[(1450,1190),(1670,1300),(1930,1440)]]:
        d.path(smooth(pts),stroke='#8e8971',width=12,opacity=.28)
    d.text(1360,580,'火山口',size=55,fill='#e0d4ba')
    d.text(1310,695,'陡坡区',size=28,fill='#ded1b5')
    return d.finish()
