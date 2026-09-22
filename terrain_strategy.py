"""Forward terrain strategy with nonincreasing climb power. Not a fuel optimizer."""
import math
import truck_model as truck

DEFAULTS=dict(lookahead=500,response=8,crest_power=20,cruise=70,dt=.5,grade_threshold=.002)
LIMITS=dict(cruise=(1,150),lookahead=(50,5000),response=(1,60),crest_power=(0,100),dt=(.25,5),grade_threshold=(0,.05))

def settings(given):
    p=truck.parameters(given)
    for k,default in DEFAULTS.items():
        value=given.get(k,default);lo,hi=LIMITS[k]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:raise ValueError(f'{k}: допустимо {lo}–{hi}.')
        p[k]=value
    return p

def hills(grid,threshold):
    result=[];start=None
    for i in range(len(grid)-1):
        grade=(grid[i+1][1]-grid[i][1])/(grid[i+1][0]-grid[i][0])
        if grade>threshold and start is None:start=i
        if grade<=threshold and start is not None:result.append((grid[start][0],grid[i][0]));start=None
    if start is not None:result.append((grid[start][0],grid[-1][0]))
    return result

def simulate(body):
    p=settings(body.get('params',{}));grid=truck.road_grid(body.get('points'),p['step'])
    xs=[a[0] for a in grid];total=xs[-1];budget=total/(p['average']/3.6)
    climbs=hills(grid,p['grade_threshold']);m=p['mass']+p['cargo'];me=m*p['rotation']
    x=0.;v=p['initial']/3.6;power=0.;time=fuel=0.;nodes=[];i=0;hill_i=0;entry=None;gear_prev=None
    vmax=p['vmax']/3.6;vmin=p['vmin']/3.6;crests=[];cuts=0;down_time=0.;down_fuel=0.
    def fail(message):
        return dict(feasible=False,message=message,strategy='terrain',distance_km=x/1000,speed_kmh=v*3.6)
    while x<total-1e-6:
        if len(nodes)>=200000:return fail('Превышен лимит 200 000 шагов. Увеличьте шаг времени или сократите маршрут.')
        while i<len(grid)-2 and x>=grid[i+1][0]-1e-7:i+=1
        left,h0=grid[i];right,h1=grid[i+1];dx=right-left;grade=(h1-h0)/dx;c=1/math.sqrt(1+grade*grade);sin=grade*c
        while hill_i<len(climbs) and x>=climbs[hill_i][1]-1e-6:
            crests.append(dict(distance=climbs[hill_i][1],speed=v*3.6,target=None))
            hill_i+=1;entry=None
        hill=climbs[hill_i] if hill_i<len(climbs) else None
        uphill=hill is not None and hill[0]-1e-6<=x<hill[1]-1e-6
        downhill=grade< -p['grade_threshold']
        
        resistance=m*9.81*(p['rolling']*c+sin)+.5*p['air']*p['cd']*p['area']*v*v
        # Before a climb aim for vmax. During it consume stored kinetic energy gradually.
        target=min(vmax,max(p['cruise'],p['final'])/3.6);phase='равномерное движение'
        desired_acc=0.
        if uphill:
            phase='подъём'
        elif hill and 0<=hill[0]-x<=p['lookahead']:target=vmax;phase='разгон перед подъёмом';desired_acc=p['accel']
        else:desired_acc=(target-v)/p['response']
        if downhill and phase!='разгон перед подъёмом':phase='спуск: накат или поддержание скорости'
        # Endpoint speed has priority; braking horizon prevents an arbitrary finish speed.
        remaining=(total-x)/c;end_v=p['final']/3.6
        final_brake=max(0.,(v*v-end_v*end_v)/(2*p['brake']))
        if remaining<=max(final_brake+v*p['dt']*2,v*p['response']):
            desired_acc=(end_v*end_v-v*v)/(2*max(remaining,1));phase='подход к финишу'
        desired_acc=max(-p['brake'],min(p['accel'],desired_acc))
        force_request=resistance+me*desired_acc
        required=max(0.,force_request*v/(1000*p['efficiency'])+p['aux'])
        # Coast whenever gravity can maintain the selected speed; otherwise use traction.
        request=required
        # Fuel cut on descent; auxiliary demand is supplied by the wheels.
        gears=[]
        for gear,ratio in enumerate(p['gears'],1):
            rpm=v*ratio*p['final_drive']*60/(2*math.pi*p['radius']);cap=truck.capacity(rpm,p)
            if cap>0:gears.append((gear,rpm,cap))
        if not gears:return fail(f'На {x/1000:.3f} км нет подходящей передачи при {v*3.6:.1f} км/ч.')
        cap_max=max(g[2] for g in gears)
        # Maximal usable entry power, then a distance-based decreasing envelope.
        # Never restore power inside this same climb after a physical cap reduced it.
        drive_cap=min(p['adhesion']*p['driven']*m*9.81*c,
                      max(0.,resistance+me*min(p['accel'],max(0.,(vmax-v)/p['dt']))))
        usable=min(cap_max,drive_cap*v/(1000*p['efficiency'])+p['aux'])
        if uphill:
            if entry is None:entry=usable;climb_previous=usable
            fraction=max(0.,min(1.,(x-hill[0])/(hill[1]-hill[0])))
            request=min(usable,climb_previous,entry*(1-(1-p['crest_power']/100)*fraction))
        elif phase=='разгон перед подъёмом':request=usable
        else:request=min(request,usable)
        if phase=='подход к финишу':request=min(request,required)
        power=request
        # Constant command per short integration step; pedal changes have no slew limit.
        step=p['dt'];chosen=None
        for _ in range(30):
            next_power=power
            average_power=power
            viable=[g for g in gears if g[2]>=power-1e-7]
            def rate(g,power_value):
                load=power_value/g[2]
                b=p['bsfc']*(1+p['rpm_penalty']*((g[1]-p['rpm_best'])/p['rpm_best'])**2+p['load_penalty']*(load-p['load_best'])**2)
                return max(p['idle'],b*power_value/(1000*p['density']))
            # Retain the gear when possible; otherwise choose a feasible fuel-efficient one.
            chosen=next((g for g in viable if g[0]==gear_prev),min(viable,key=lambda g:rate(g,average_power)))
            traction=(average_power-p['aux'])*1000*p['efficiency']/max(v,.1)
            if traction>p['adhesion']*p['driven']*m*9.81*c+1e-6:return fail(f'На {x/1000:.3f} км превышено сцепление ведущих колёс.')
            acc=(traction-resistance)/me
            # Passive engine/auxiliary drag when fuel is cut; braking dissipates excess energy.
            if downhill:limit=min(p['accel'],(vmax-v)/max(step,.001))
            else:limit=min(p['accel'],(vmax-v)/max(step,.001))
            if phase=='подход к финишу':limit=min(limit,desired_acc)
            brake_force=max(0.,me*(acc-limit));acc=min(acc,limit)
            if acc< -p['brake']-1e-7 or brake_force>p['adhesion']*m*9.81*c+1e-7:return fail(f'На {x/1000:.3f} км требуется чрезмерное торможение.')
            if acc>p['accel']+1e-7:return fail(f'На {x/1000:.3f} км превышено допустимое ускорение.')
            next_v=v+acc*step
            if next_v<vmin-.3/3.6:return fail(f'На {x/1000:.3f} км скорость {next_v*3.6:.2f} км/ч ниже минимума {p["vmin"]:.2f} км/ч. Уклон {grade*100:.2f}%, мощность {power:.1f} кВт. Не хватает тяги при выбранной политике снижения мощности.')
            ds=(v+next_v)/2*step;advance=ds*c
            if advance>right-x+1e-7:
                step*=max(.000001,(right-x)/advance);continue
            end_caps=[(g,truck.capacity(next_v*p['gears'][g[0]-1]*p['final_drive']*60/(2*math.pi*p['radius']),p)) for g in gears]
            valid_end=[g for g,cap in end_caps if cap>0 and min(g[2],cap)>=power-1e-7]
            if not valid_end:
                caps=[min(g[2],cap) for g,cap in end_caps if cap>0]
                if caps and max(caps)<power:
                    power=max(0.,max(caps)*(1-1e-6));continue
                step*=.5
                if step<1e-5:return fail(f'На {x/1000:.3f} км нет передачи для перехода {v*3.6:.2f} → {next_v*3.6:.2f} км/ч при {power:.1f} кВт. Проверьте обороты и передаточные числа.')
                continue
            break
        if advance>right-x+1e-4: return fail('Не удалось точно пройти границу участка. Уменьшите шаг времени.')
        valid_end=[g for g in gears if g[2]>=power-1e-7 and truck.capacity(next_v*p['gears'][g[0]-1]*p['final_drive']*60/(2*math.pi*p['radius']),p)>=next_power-1e-7 and truck.capacity(next_v*p['gears'][g[0]-1]*p['final_drive']*60/(2*math.pi*p['radius']),p)>0]
        if not valid_end:return fail(f'На {x/1000:.3f} км переход выходит за рабочий диапазон передачи. Уменьшите шаг времени.')
        chosen=next((g for g in valid_end if g[0]==gear_prev),min(valid_end,key=lambda g:rate(g,average_power)))
        # Cut-off is physical only when wheels can cover auxiliary demand without positive engine power.
        cutoff=downhill and power<=1e-8 and next_power<=1e-8
        if cutoff:r0=r1=0.;cuts+=1
        else:
            rpm_end=next_v*p['gears'][chosen[0]-1]*p['final_drive']*60/(2*math.pi*p['radius'])
            end_gear=(chosen[0],rpm_end,truck.capacity(rpm_end,p))
            r0=rate(chosen,power);r1=rate(end_gear,next_power)
        spent=(r0+r1)/2*step/3600
        node=dict(distance=x,height=h0+grade*(x-left),speed=v*3.6,time=time,fuel=fuel,rate=(r0+r1)/2,rate_start=r0,rate_end=r1,
                  gear=chosen[0],power=average_power,power_start=power,power_end=next_power,available=min(chosen[2],truck.capacity(next_v*p['gears'][chosen[0]-1]*p['final_drive']*60/(2*math.pi*p['radius']),p)),peak_power=max(power,next_power),
                  accel=acc,duration=step,phase=phase,target_speed=target*3.6,cutoff=cutoff,brake_force=brake_force)
        nodes.append(node)
        if downhill:down_time+=step;down_fuel+=spent
        if uphill:climb_previous=next_power
        x=min(right,x+advance);v=next_v;power=next_power;gear_prev=chosen[0];time+=step;fuel+=spent
    if hill_i<len(climbs) and abs(climbs[hill_i][1]-total)<1e-5:crests.append(dict(distance=total,speed=v*3.6,target=None))
    nodes.append(dict(distance=total,height=grid[-1][1],speed=v*3.6,time=time,fuel=fuel,rate=0,rate_start=0,rate_end=0,gear=0,power=0,power_start=0,power_end=0,available=0,peak_power=0,accel=0,duration=0,phase='финиш',target_speed=p['final'],cutoff=False,brake_force=0))
    if abs(v*3.6-p['final'])>1:return fail(f'На финише получено {v*3.6:.1f} км/ч вместо {p["final"]:.1f}. Скорость на вершине и условие финиша могут конфликтовать.')
    if time>budget+1e-6:return dict(feasible=False,strategy='terrain',message=f'Стратегия не выдержала среднюю скорость: {total/time*3.6:.2f} км/ч вместо {p["average"]:.2f}. Уменьшите требование или используйте экономичный поиск.',actual_average=total/time*3.6)
    return dict(feasible=True,strategy='terrain',nodes=nodes,params=p,fuel_l=fuel,time_s=time,average_kmh=total/time*3.6,litres_100km=fuel/(total/100000),budget_s=budget,
                segments=len(nodes)-1,speed_states=0,passes=1,baseline=None,crests=crests,cutoff_steps=cuts,downhill_time_s=down_time,downhill_fuel_l=down_fuel,
                method='Terrain controller with nonincreasing climb power; heuristic, not an optimizer')


def optimize(body):
    """Bounded coordinate search over the user's monotone-power policy.

    All candidates use identical physics, integration precision and constraints.
    Initial manual policy is always included, so a feasible result cannot worsen it.
    """
    params=settings(body.get('params',{}))
    best=None;manual=None;seen=set();trials=[]
    def evaluate(candidate):
        nonlocal best
        key=tuple(candidate[k] for k in ('cruise','lookahead','crest_power'))
        if key in seen:return
        seen.add(key)
        result=simulate(dict(points=body.get('points'),params=candidate))
        trials.append(dict(cruise=key[0],lookahead=key[1],crest_power=key[2],
                           feasible=result['feasible'],fuel_l=result.get('fuel_l'),
                           message=result.get('message'),distance_km=result.get('distance_km')))
        if result['feasible'] and (best is None or result['fuel_l']<best['fuel_l']):best=result
        return result
    manual=evaluate(params)
    # Find a feasible seed, including gentle power taper for difficult climbs.
    for crest in (20.,60.,100.):
        evaluate(dict(params,crest_power=crest,cruise=min(params['vmax'],max(params['average'],params['cruise']))))
    # Coordinate descent retains the best feasible result after each axis.
    for axis,values in (
        ('cruise',[params['average'],(params['average']+params['vmax'])/2,params['vmax']]),
        ('lookahead',[50.,250.,1000.,2000.]),
        ('crest_power',[0.,20.,40.,60.,80.,100.]),
        ('cruise',[params['average'],(params['average']+params['vmax'])/2,params['vmax']]),
    ):
        anchor=dict(best['params'] if best else params)
        for value in values:
            if axis=='cruise':value=min(params['vmax'],max(params['vmin'],value))
            evaluate(dict(anchor,**{axis:value}))
    if best is None:
        groups={}
        for t in trials:
            msg=t['message'] or 'Неизвестная причина'
            category=('Минимальная скорость' if 'ниже минимума' in msg else
                      'Передачи и мощность' if 'передач' in msg else
                      'Средняя скорость' if 'среднюю скорость' in msg else
                      'Финишная скорость' if 'финише' in msg else
                      'Торможение' if 'торможение' in msg else 'Расчётные ограничения')
            groups.setdefault(category,[]).append(t)
        lines=[f'Допустимый расчёт не найден: проверено {len(trials)} вариантов.']
        for category,items in groups.items():
            example=max(items,key=lambda t:t.get('distance_km') or 0)
            lines.append(f'{category}: {len(items)} вариантов. Пример: {example["message"]}')
        lines.append('Это ограниченный поиск, а не доказательство непроходимости маршрута. Проверьте указанные ограничения и профиль высот. Изменять их только ради успешного расчёта не следует.')
        return dict(feasible=False,strategy='terrain',message='\n\n'.join(lines),search=trials)
    best['passes']=len(trials)
    best['search']=trials
    best['baseline']=dict(fuel_l=manual['fuel_l'],time_s=manual['time_s']) if manual and manual['feasible'] else None
    best['optimized']=True
    best['method']='Bounded coordinate search of terrain policy; best tested feasible fuel, not global optimum'
    return best
