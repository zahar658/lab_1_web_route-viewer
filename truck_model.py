"""Educational spatial truck model, standard library. No calibrated vehicle data."""
import math
import bisect
from array import array

DEFAULTS = dict(mass=12000, cargo=10000, average=60, vmin=20, vmax=120, initial=40, final=40,
                dv=5, step=250, power=250, torque=1800, rpm_min=700, rpm_peak=1300, rpm_max=2300, torque_low=.7, torque_high=.65,
                final_drive=3.5, radius=.5, efficiency=.92, rolling=.007, cd=.65, area=8,
                air=1.225, rotation=1.05, accel=.5, brake=1.5, adhesion=.6, driven=.55,
                bsfc=210, rpm_best=1300, load_best=.75, rpm_penalty=.25, load_penalty=.6,
                idle=2, aux=2, density=.835, gears=[12,9.2,7.1,5.5,4.2,3.2,2.5,1.9,1.45,1.1,.85,.65])
LIMITS = dict(mass=(500,100000),cargo=(0,150000),average=(1,150),vmin=(1,100),vmax=(2,150),initial=(1,150),final=(1,150),dv=(2,20),step=(25,2000),power=(10,2000),torque=(50,15000),torque_low=(.1,1),torque_high=(.1,1),rpm_min=(300,3000),rpm_peak=(400,4000),rpm_max=(500,6000),final_drive=(1,10),radius=(.2,1.5),efficiency=(.5,1),rolling=(.001,.1),cd=(.1,2),area=(1,20),air=(.5,2),rotation=(1,1.5),accel=(.05,3),brake=(.1,8),adhesion=(.05,1.5),driven=(.1,1),bsfc=(150,500),rpm_best=(400,4000),load_best=(.1,1),rpm_penalty=(0,5),load_penalty=(0,5),idle=(0,20),aux=(0,50),density=(.7,1))

def parameters(given):
    p=DEFAULTS.copy()
    if not isinstance(given,dict): raise ValueError('Некорректные параметры грузовика.')
    p.update({k:v for k,v in given.items() if k in p})
    for k,(lo,hi) in LIMITS.items():
        v=p[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:
            raise ValueError(f'Параметр {k}: допустимо от {lo} до {hi}.')
    if not p['vmin']<p['vmax'] or not all(p['vmin']<=p[k]<=p['vmax'] for k in ('initial','final')):
        raise ValueError('Начальная и конечная скорости должны быть внутри диапазона min–max.')
    if not p['rpm_min']<p['rpm_peak']<p['rpm_max'] or not p['rpm_min']<=p['rpm_best']<=p['rpm_max']:
        raise ValueError('Проверьте диапазон оборотов, обороты пика момента и минимального расхода.')
    gears=p['gears']
    if not isinstance(gears,list) or not 1<=len(gears)<=16 or any(isinstance(g,bool) or not isinstance(g,(int,float)) or not math.isfinite(g) or not .1<=g<=30 for g in gears):
        raise ValueError('Передачи: от 1 до 16 чисел в диапазоне 0,1–30.')
    if any(a<=b for a,b in zip(gears,gears[1:])):raise ValueError('Передаточные числа должны строго убывать.')
    return p

def road_grid(raw,step):
    if not isinstance(raw,list) or not 2<=len(raw)<=200000:raise ValueError('Нужно от 2 до 200 000 точек с высотами.')
    xs=[];hs=[]
    for row in raw:
        if not isinstance(row,list) or len(row)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in row):raise ValueError('Для расчёта нужны расстояние и высота каждой точки без пропусков.')
        x,h=row
        if x<0 or abs(h)>15000 or (xs and x<xs[-1]):raise ValueError('Некорректные расстояния или высоты.')
        if xs and x==xs[-1]:
            if abs(h-hs[-1])>.01:raise ValueError('Разные высоты при одинаковом расстоянии. Выберите сглаженный профиль.')
            continue
        xs.append(x);hs.append(h)
    if len(xs)<2 or xs[-1]-xs[0]<=0:raise ValueError('Маршрут имеет нулевую длину.')
    offset=xs[0];xs=[x-offset for x in xs]
    # Preserve every original height vertex; subdivide long edges only.
    grid=[(0,hs[0])]
    for i in range(1,len(xs)):
        n=math.ceil((xs[i]-xs[i-1])/step)
        if len(grid)+n>20000:raise ValueError('Расчётная сетка превышает 20 000 участков. Увеличьте максимальный шаг или используйте более короткий маршрут.')
        for j in range(1,n+1):
            f=j/n;grid.append((xs[i-1]+f*(xs[i]-xs[i-1]),hs[i-1]+f*(hs[i]-hs[i-1])))
    return grid

def capacity(rpm,p):
    if not p['rpm_min']<=rpm<=p['rpm_max']:return 0
    if rpm<=p['rpm_peak']:
        fraction=p['torque_low']+(1-p['torque_low'])*(rpm-p['rpm_min'])/(p['rpm_peak']-p['rpm_min'])
    else:fraction=1-(1-p['torque_high'])*(rpm-p['rpm_peak'])/(p['rpm_max']-p['rpm_peak'])
    return min(p['power'],p['torque']*fraction*rpm*2*math.pi/60000)

def transition(a,b,dx,dh,p):
    """a,b in m/s; constant acceleration over inclined segment."""
    ds=math.hypot(dx,dh);acc=(b*b-a*a)/(2*ds)
    if acc>p['accel']+1e-9 or acc< -p['brake']-1e-9:return None
    m=p['mass']+p['cargo'];c=dx/ds;sin=dh/ds
    base=m*9.81*(p['rolling']*c+sin)+m*p['rotation']*acc
    dt=2*ds/(a+b);best=None
    for gear,ratio in enumerate(p['gears'],1):
        k=ratio*p['final_drive']*60/(2*math.pi*p['radius'])
        # Simpson quadrature in time. Forces checked at endpoints as well.
        rates=[];powers=[];caps=[]
        for v in (a,(a+b)/2,b):
            rpm=v*k;cap=capacity(rpm,p)
            force=base+.5*p['air']*p['cd']*p['area']*v*v
            if cap<=0 or max(force,0)>p['adhesion']*p['driven']*m*9.81*c or max(-force,0)>p['adhesion']*m*9.81*c:break
            power=max(force,0)*v/(1000*p['efficiency'])+p['aux']
            if power>cap+1e-8:break
            load=power/cap
            bsfc=p['bsfc']*(1+p['rpm_penalty']*((rpm-p['rpm_best'])/p['rpm_best'])**2+p['load_penalty']*(load-p['load_best'])**2)
            rate=max(p['idle'],bsfc*power/(1000*p['density'])) # litres/hour; idle floor
            if dh<0 and force*v<= -p['aux']*1000*p['efficiency']:
                power=0.;rate=0. # fuel cut; auxiliary energy supplied by wheels
            rates.append(rate);powers.append(power);caps.append(cap)
        if len(rates)!=3:continue
        fuel=(rates[0]+4*rates[1]+rates[2])/6*dt/3600
        candidate=(fuel,dt,gear,sum(powers)/3,min(caps),max(powers),acc)
        if best is None or fuel<best[0]:best=candidate
    return best

def optimize(body):
    p=parameters(body.get('params',{}));grid=road_grid(body.get('points'),p['step'])
    total=grid[-1][0];budget=total/(p['average']/3.6)
    speeds=sorted(set([p['vmin']+i*p['dv'] for i in range(int((p['vmax']-p['vmin'])/p['dv'])+1)]+[p['vmax'],p['initial'],p['final']]))
    if len(speeds)>45:raise ValueError('Слишком много скоростей сетки. Увеличьте шаг скорости.')
    n=len(speeds)
    if (len(grid)-1)*n*n>5000000:raise ValueError('Слишком большая расчётная сетка. Увеличьте шаг скорости или выберите более короткий маршрут.')
    start=speeds.index(p['initial']);end=speeds.index(p['final']);vs=[v/3.6 for v in speeds]
    edges=[]
    # Compact edge storage per destination: predecessor, fuel, time.
    for (x,h),(xx,hh) in zip(grid,grid[1:]):
        layer=[[] for _ in vs]
        for j,b in enumerate(vs):
            for i,a in enumerate(vs):
                t=transition(a,b,xx-x,hh-h,p)
                if t is not None:layer[j].append((i,t[0],t[1]))
        edges.append(layer)
    def solve(weight=None):
        costs=[math.inf]*n;costs[start]=0;back=[]
        for layer in edges:
            new=[math.inf]*n;parent=array('h',[-1])*n
            for j,candidates in enumerate(layer):
                for i,f,t in candidates:
                    value=costs[i]+(t if weight is None else f+weight*t)
                    if value<new[j]:new[j]=value;parent[j]=i
            back.append(parent);costs=new
        if not math.isfinite(costs[end]):return None
        path=[end]
        for parent in reversed(back):path.append(parent[path[-1]])
        path.reverse();fuel=seconds=0
        for k,layer in enumerate(edges):
            edge=next(e for e in layer[path[k+1]] if e[0]==path[k]);fuel+=edge[1];seconds+=edge[2]
        return (fuel,seconds,path)
    fastest=solve()
    if fastest is None:return dict(feasible=False,message='На выбранной сетке нет проезда с заданными мощностью, скоростями и передачами. Уменьшите шаг скорости, проверьте минимальную скорость и рельеф. Это не доказательство физической непроходимости.')
    if fastest[1]>budget+1e-6:return dict(feasible=False,message='Заданная средняя скорость недостижима на выбранной сетке.',fastest_average=total/fastest[1]*3.6,fastest_time_s=fastest[1],budget_s=budget)
    best=fastest;free=solve(0);passes=2
    if free[1]<=budget+1e-6:best=free
    else:
        low=0.;high=.001
        for _ in range(24):
            trial=solve(high);passes+=1
            if trial[1]<=budget+1e-6:
                if trial[0]<best[0]:best=trial
                break
            low=high;high*=2
        for _ in range(18):
            mid=(low+high)/2;trial=solve(mid);passes+=1
            if trial[1]<=budget+1e-6:
                high=mid
                if trial[0]<best[0]:best=trial
            else:low=mid
    # Constant speed benchmark, same endpoints only when initial=final=target.
    baseline=None
    if p['initial']==p['final']==p['average']:
        bf=bt=0
        for (x,h),(xx,hh) in zip(grid,grid[1:]):
            t=transition(p['average']/3.6,p['average']/3.6,xx-x,hh-h,p)
            if t is None:break
            bf+=t[0];bt+=t[1]
        else:baseline=dict(fuel_l=bf,time_s=bt)
    if baseline and baseline['time_s']<=budget+1e-6 and baseline['fuel_l']<best[0]:
        ix=speeds.index(p['average']);best=(baseline['fuel_l'],baseline['time_s'],[ix]*len(grid))
    nodes=[];time=fuel=0
    for k,(x,h) in enumerate(grid):
        node=dict(distance=x,height=h,speed=speeds[best[2][k]],time=time,fuel=fuel)
        if k<len(grid)-1:
            xx,hh=grid[k+1];t=transition(vs[best[2][k]],vs[best[2][k+1]],xx-x,hh-h,p)
            node.update(rate=t[0]/t[1]*3600,gear=t[2],power=t[3],available=t[4],peak_power=t[5],accel=t[6],duration=t[1])
            fuel+=t[0];time+=t[1]
        else:node.update(rate=0,gear=0,power=0,available=0,peak_power=0,accel=0,duration=0)
        nodes.append(node)
    return dict(feasible=True,nodes=nodes,fuel_l=fuel,time_s=time,average_kmh=total/time*3.6,
                litres_100km=fuel/(total/100000),budget_s=budget,fastest_average=total/fastest[1]*3.6,
                segments=len(edges),speed_states=n,passes=passes,baseline=baseline,params=p,
                method='DP fuel + time penalty; best feasible candidate, not guaranteed global constrained optimum')
