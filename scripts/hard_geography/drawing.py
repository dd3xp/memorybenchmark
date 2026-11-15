"""Editable SVG cartography shared only at the drawing-primitive level."""
from html import escape
from math import cos,sin,pi
from random import Random


def smooth(points):
    """Centripetal-looking cubic interpolation through authored control points."""
    p=[points[0],*points,points[-1]];parts=[f'M{points[0][0]:.2f},{points[0][1]:.2f}']
    for i in range(1,len(p)-2):
        a,b,c,d=p[i-1:i+3]
        u=(b[0]+(c[0]-a[0])/6,b[1]+(c[1]-a[1])/6)
        v=(c[0]-(d[0]-b[0])/6,c[1]-(d[1]-b[1])/6)
        parts.append(f'C{u[0]:.2f},{u[1]:.2f} {v[0]:.2f},{v[1]:.2f} {c[0]:.2f},{c[1]:.2f}')
    return ' '.join(parts)


def organic(cx,cy,rx,ry,phase=0,angle=0):
    result=[]
    for i in range(65):
        a=2*pi*i/64;r=1+.09*sin(3*a+phase)+.04*sin(5*a-phase)
        x=rx*cos(a)*r;y=ry*sin(a)*r
        result.append((cx+x*cos(angle)-y*sin(angle),cy+x*sin(angle)+y*cos(angle)))
    return 'M'+'L'.join(f'{x:.1f},{y:.1f}' for x,y in result)+'Z'


class Drawing:
    def __init__(self,name,width,height,base):
        self.width=width;self.height=height
        self.parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
                    f'<title>{escape(name)} · 地形示意</title><desc>地区景观原型上的独立手绘路网，非历史道路复原；无处理能力答案。</desc>',
                    '<defs><pattern id="paper" width="83" height="71" patternUnits="userSpaceOnUse"><path d="M9 15h1m27 26h1m23-31h1m-8 51h1" stroke="#485946" opacity=".075" stroke-width="2"/></pattern>',
                    '<linearGradient id="water" x1="0" y1="0" x2=".4" y2="1"><stop stop-color="#8fbcb6"/><stop offset="1" stop-color="#6b9e9d"/></linearGradient>',
                    '<pattern id="paddy" width="70" height="62" patternUnits="userSpaceOnUse"><path d="M0 0H70V62H0Z" fill="none" stroke="#9bad85" stroke-width="2" opacity=".32"/></pattern></defs>',
                    f'<rect width="{width}" height="{height}" fill="{base}"/>']

    def path(self,d,fill='none',stroke='none',width=1,opacity=1,**attrs):
        extra=' '.join(f'{k.replace("_","-")}="{v}"' for k,v in attrs.items())
        self.parts.append(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}" stroke-linejoin="round" stroke-linecap="round" {extra}/>')

    def polygon(self,points,fill,stroke='none',width=1,opacity=1):
        self.path('M'+'L'.join(f'{x},{y}' for x,y in points)+'Z',fill,stroke,width,opacity)

    def river(self,points,width,*,colour='#7ba8a3'):
        d=smooth(points);self.path(d,stroke='#c9d4b9',width=width+45,opacity=.75)
        self.path(d,stroke=colour,width=width);self.path(d,stroke='#b9d7c7',width=width*.23,opacity=.65)

    def forest(self,points,seed,colour='#a5b28b',trees=110):
        self.polygon(points,colour,opacity=.7)
        rng=Random(seed);xs=[x for x,y in points];ys=[y for x,y in points]
        def inside(x,y):
            contained=False
            for i,(a,b) in enumerate(points):
                c,d=points[i-1]
                if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:contained=not contained
            return contained
        placed=0
        for _ in range(trees*8):
            x=rng.uniform(min(xs),max(xs));y=rng.uniform(min(ys),max(ys))
            if not inside(x,y):continue
            r=rng.uniform(15,30);self.path(organic(x,y,r,r*1.3,rng.random()),fill='#637e59',opacity=.1)
            placed+=1
            if placed>=trees:break

    def settlement(self,x,y,rx,ry,angle,seed,*,buildings=22):
        self.path(organic(x,y,rx,ry,seed*.3,angle*pi/180),fill='#d7c6a9',opacity=.52)
        rng=Random(seed)
        for _ in range(buildings):
            a=rng.random()*2*pi;r=rng.random()**.5
            px=x+cos(a)*rx*r;py=y+sin(a)*ry*r;w=rng.randint(18,35);h=rng.randint(13,25)
            self.parts.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{w}" height="{h}" transform="rotate({angle} {px:.1f} {py:.1f})" fill="#b6a28b" stroke="#8c8d78" stroke-width="1.5" opacity=".62"/>')

    def text(self,x,y,value,*,size=38,fill='#657862',opacity=.7,angle=0):
        self.parts.append(f'<text x="{x}" y="{y}" font-family="Microsoft YaHei,Noto Sans CJK SC,sans-serif" font-size="{size}" fill="{fill}" opacity="{opacity}" text-anchor="middle" transform="rotate({angle} {x} {y})">{escape(value)}</text>')

    def finish(self):
        return '\n'.join([*self.parts,'</svg>'])
