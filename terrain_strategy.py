"""Forward terrain strategy with nonincreasing climb power. Not a fuel optimizer."""
import math
import vehicle_physics as truck
DEFAULTS = dict(momentum=1.0, lookahead=500, response=8, crest_power=20, cruise=70, dt=0.5, grade_threshold=0.002)
LIMITS = dict(momentum=(0, 1), cruise=(1, 150), lookahead=(50, 5000), response=(1, 60), crest_power=(0, 100), dt=(0.25, 5), grade_threshold=(0, 0.05))

def settings(given):
    p = truck.parameters(given)
    for k, default in DEFAULTS.items():
        value = default if k in ('response', 'grade_threshold') else given.get(k, default)
        lo, hi = LIMITS[k]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (not math.isfinite(value)) or (not lo <= value <= hi):
            raise ValueError(f'{k}: допустимо {lo}–{hi}.')
        p[k] = value
    return p

def hills(grid, threshold):
    result = []
    start = None
    for i in range(len(grid) - 1):
        grade = (grid[i + 1][1] - grid[i][1]) / (grid[i + 1][0] - grid[i][0])
        if grade > threshold and start is None:
            start = i
        if grade <= threshold and start is not None:
            result.append((grid[start][0], grid[i][0]))
            start = None
    if start is not None:
        result.append((grid[start][0], grid[-1][0]))
    return result

def simulate(body):
    p = settings(body.get('params', {}))
    grid = truck.road_grid(body.get('points'), p['step'])
    xs = [a[0] for a in grid]
    total = xs[-1]
    budget = total / (p['average'] / 3.6)
    heights = dict(grid)
    climbs = hills(grid, p['grade_threshold'])
    m = p['mass'] + p['cargo']
    me = m * p['rotation']
    x = 0.0
    v = p['initial'] / 3.6
    power = 0.0
    time = fuel = 0.0
    nodes = []
    i = 0
    hill_i = 0
    entry = None
    gear_prev = None
    vmax = p['vmax'] / 3.6
    vmin = p['vmin'] / 3.6
    crests = []
    cuts = 0
    down_time = 0.0
    down_fuel = 0.0

    def fail(message):
        return dict(feasible=False, message=message, strategy='terrain', distance_km=x / 1000, speed_kmh=v * 3.6)
    while x < total - 1e-06:
        if len(nodes) >= 200000:
            return fail('Превышен лимит 200 000 шагов. Увеличьте шаг времени или сократите маршрут.')
        while i < len(grid) - 2 and x >= grid[i + 1][0] - 1e-07:
            i += 1
        left, h0 = grid[i]
        right, h1 = grid[i + 1]
        dx = right - left
        grade = (h1 - h0) / dx
        c = 1 / math.sqrt(1 + grade * grade)
        sin = grade * c
        while hill_i < len(climbs) and x >= climbs[hill_i][1] - 1e-06:
            crests.append(dict(distance=climbs[hill_i][1], speed=v * 3.6, target=p['vmin']))
            hill_i += 1
            entry = None
        hill = climbs[hill_i] if hill_i < len(climbs) else None
        uphill = hill is not None and hill[0] - 1e-06 <= x < hill[1] - 1e-06
        downhill = grade < -p['grade_threshold']
        resistance = m * 9.81 * (p['rolling'] * c + sin) + 0.5 * p['air'] * p['cd'] * p['area'] * v * v
        target = min(vmax, max(p['vmin'], p['cruise']) / 3.6)
        phase = 'равномерное движение'
        hill_target = target
        if hill:
            rise = max(0.0, heights[hill[1]] - heights[hill[0]])
            hill_target = min(vmax, math.sqrt(target * target + 2 * 9.81 * rise * p['momentum'] / p['rotation']))
        desired_acc = 0.0
        if uphill:
            phase = 'подъём'
        elif hill and 0 <= hill[0] - x <= p['lookahead']:
            target = hill_target
            phase = 'разгон перед подъёмом'
            desired_acc = min(p['accel'], (target - v) / p['response'])
        else:
            desired_acc = (target - v) / p['response']
        if downhill and phase != 'разгон перед подъёмом':
            phase = 'спуск: накат или поддержание скорости'
        remaining = (total - x) / c
        end_v = p['final'] / 3.6
        final_brake = max(0.0, (v * v - end_v * end_v) / (2 * p['brake']))
        if remaining <= max(final_brake + v * p['dt'] * 2, v * p['response']):
            desired_acc = (end_v * end_v - v * v) / (2 * max(remaining, 1))
            phase = 'подход к финишу'
        desired_acc = max(-p['brake'], min(p['accel'], desired_acc))
        force_request = resistance + me * desired_acc
        required = max(0.0, force_request * v / (1000 * p['efficiency']) + p['aux'])
        request = required
        gears = []
        for gear, ratio in enumerate(p['gears'], 1):
            rpm = v * ratio * p['final_drive'] * 60 / (2 * math.pi * p['radius'])
            cap = truck.capacity(rpm, p)
            if cap > 0:
                gears.append((gear, rpm, cap))
        if not gears:
            return fail(f'На {x / 1000:.3f} км нет подходящей передачи при {v * 3.6:.1f} км/ч.')
        cap_max = max((g[2] for g in gears))
        drive_cap = min(p['adhesion'] * p['driven'] * m * 9.81 * c, max(0.0, resistance + me * min(p['accel'], max(0.0, (vmax - v) / p['dt']))))
        usable = min(cap_max, drive_cap * v / (1000 * p['efficiency']) + p['aux'])
        if uphill:
            if entry is None:
                requested_acc = max(0.0, (hill_target - v) / p['response'])
                entry = min(usable, max(0.0, resistance + me * requested_acc) * v / (1000 * p['efficiency']) + p['aux'])
                climb_previous = entry
            fraction = max(0.0, min(1.0, (x - hill[0]) / (hill[1] - hill[0])))
            request = min(usable, climb_previous, entry * (1 - (1 - p['crest_power'] / 100) * fraction))
        elif phase == 'разгон перед подъёмом':
            request = min(usable, required)
        else:
            request = min(request, usable)
        if phase == 'подход к финишу':
            request = min(request, required)
        power = request
        step = p['dt']
        chosen = None
        for _ in range(30):
            next_power = power
            average_power = power
            viable = [g for g in gears if g[2] >= power - 1e-07]

            def rate(g, power_value):
                load = power_value / g[2]
                b = p['bsfc'] * (1 + p['rpm_penalty'] * ((g[1] - p['rpm_best']) / p['rpm_best']) ** 2 + p['load_penalty'] * (load - p['load_best']) ** 2)
                return max(p['idle'], b * power_value / (1000 * p['density']))
            chosen = next((g for g in viable if g[0] == gear_prev), min(viable, key=lambda g: rate(g, average_power)))
            traction = (average_power - p['aux']) * 1000 * p['efficiency'] / max(v, 0.1)
            if traction > p['adhesion'] * p['driven'] * m * 9.81 * c + 1e-06:
                return fail(f'На {x / 1000:.3f} км превышено сцепление ведущих колёс.')
            acc = (traction - resistance) / me
            if downhill:
                limit = min(p['accel'], (vmax - v) / max(step, 0.001))
            else:
                limit = min(p['accel'], (vmax - v) / max(step, 0.001))
            if phase == 'подход к финишу':
                limit = min(limit, desired_acc)
            brake_force = max(0.0, me * (acc - limit))
            acc = min(acc, limit)
            if acc < -p['brake'] - 1e-07 or brake_force > p['adhesion'] * m * 9.81 * c + 1e-07:
                return fail(f'На {x / 1000:.3f} км требуется чрезмерное торможение.')
            if acc > p['accel'] + 1e-07:
                return fail(f'На {x / 1000:.3f} км превышено допустимое ускорение.')
            next_v = v + acc * step
            if next_v < vmin - 1e-9:
                return fail(f"На {x / 1000:.3f} км скорость {next_v * 3.6:.2f} км/ч ниже минимума {p['vmin']:.2f} км/ч. Уклон {grade * 100:.2f}%, мощность {power:.1f} кВт. Не хватает тяги при выбранной политике снижения мощности.")
            ds = (v + next_v) / 2 * step
            advance = ds * c
            if advance > right - x + 1e-07:
                step *= max(1e-06, (right - x) / advance)
                continue
            end_caps = [(g, truck.capacity(next_v * p['gears'][g[0] - 1] * p['final_drive'] * 60 / (2 * math.pi * p['radius']), p)) for g in gears]
            valid_end = [g for g, cap in end_caps if cap > 0 and min(g[2], cap) >= power - 1e-07]
            if not valid_end:
                caps = [min(g[2], cap) for g, cap in end_caps if cap > 0]
                if caps and max(caps) < power:
                    power = max(0.0, max(caps) * (1 - 1e-06))
                    continue
                step *= 0.5
                if step < 1e-05:
                    return fail(f'На {x / 1000:.3f} км нет передачи для перехода {v * 3.6:.2f} → {next_v * 3.6:.2f} км/ч при {power:.1f} кВт. Проверьте обороты и передаточные числа.')
                continue
            break
        if advance > right - x + 0.0001:
            return fail('Не удалось точно пройти границу участка. Уменьшите шаг времени.')
        valid_end = [g for g in gears if g[2] >= power - 1e-07 and truck.capacity(next_v * p['gears'][g[0] - 1] * p['final_drive'] * 60 / (2 * math.pi * p['radius']), p) >= next_power - 1e-07 and (truck.capacity(next_v * p['gears'][g[0] - 1] * p['final_drive'] * 60 / (2 * math.pi * p['radius']), p) > 0)]
        if not valid_end:
            return fail(f'На {x / 1000:.3f} км переход выходит за рабочий диапазон передачи. Уменьшите шаг времени.')
        chosen = next((g for g in valid_end if g[0] == gear_prev), min(valid_end, key=lambda g: rate(g, average_power)))
        cutoff = downhill and power <= 1e-08 and (next_power <= 1e-08)
        if cutoff:
            r0 = r1 = 0.0
            cuts += 1
        else:
            rpm_end = next_v * p['gears'][chosen[0] - 1] * p['final_drive'] * 60 / (2 * math.pi * p['radius'])
            end_gear = (chosen[0], rpm_end, truck.capacity(rpm_end, p))
            r0 = rate(chosen, power)
            r1 = rate(end_gear, next_power)
        spent = (r0 + r1) / 2 * step / 3600
        node = dict(distance=x, height=h0 + grade * (x - left), speed=v * 3.6, time=time, fuel=fuel, rate=(r0 + r1) / 2, rate_start=r0, rate_end=r1, gear=chosen[0], power=average_power, power_start=power, power_end=next_power, available=min(chosen[2], truck.capacity(next_v * p['gears'][chosen[0] - 1] * p['final_drive'] * 60 / (2 * math.pi * p['radius']), p)), peak_power=max(power, next_power), accel=acc, duration=step, phase=phase, target_speed=target * 3.6, cutoff=cutoff, brake_force=brake_force)
        nodes.append(node)
        if downhill:
            down_time += step
            down_fuel += spent
        if uphill:
            climb_previous = next_power
        x = min(right, x + advance)
        v = next_v
        power = next_power
        gear_prev = chosen[0]
        time += step
        fuel += spent
    if hill_i < len(climbs) and abs(climbs[hill_i][1] - total) < 1e-05:
        crests.append(dict(distance=total, speed=v * 3.6, target=p['vmin']))
    nodes.append(dict(distance=total, height=grid[-1][1], speed=v * 3.6, time=time, fuel=fuel, rate=0, rate_start=0, rate_end=0, gear=0, power=0, power_start=0, power_end=0, available=0, peak_power=0, accel=0, duration=0, phase='финиш', target_speed=p['final'], cutoff=False, brake_force=0))
    if abs(v * 3.6 - p['final']) > 1:
        return fail(f"На финише получено {v * 3.6:.1f} км/ч вместо {p['final']:.1f}. Скорость на вершине и условие финиша могут конфликтовать.")
    if time > budget + 1e-06:
        return dict(feasible=False, strategy='terrain', message=f"Стратегия не выдержала среднюю скорость: {total / time * 3.6:.2f} км/ч вместо {p['average']:.2f}. Проверьте требуемую среднюю скорость и возможности ТС.", actual_average=total / time * 3.6)
    return dict(feasible=True, strategy='terrain', nodes=nodes, params=p, fuel_l=fuel, time_s=time, average_kmh=total / time * 3.6, litres_100km=fuel / (total / 100000), budget_s=budget, segments=len(nodes) - 1, speed_states=0, passes=1, baseline=None, crests=crests, cutoff_steps=cuts, downhill_time_s=down_time, downhill_fuel_l=down_fuel, method='Terrain controller with nonincreasing climb power; heuristic, not an optimizer')

def optimize(body):
    """Bounded coordinate search over the user's monotone-power policy.

    All candidates use identical physics, integration precision and constraints.
    A default automatic seed is included; user controls only trip and vehicle constraints.
    """
    # User input cannot set the policy searched by this automatic mode.
    supplied = dict(body.get('params', {}))
    for key in ('cruise', 'lookahead', 'crest_power', 'momentum'):
        supplied.pop(key, None)
    params = settings(supplied)
    params['cruise'] = max(params['vmin'], min(params['vmax'], params['average']))
    best = None
    manual = None
    seen = set()
    trials = []

    def evaluate(candidate):
        nonlocal best
        key = tuple((candidate[k] for k in ('cruise', 'lookahead', 'crest_power', 'momentum')))
        if key in seen:
            return
        seen.add(key)
        result = simulate(dict(points=body.get('points'), params=candidate))
        trials.append(dict(cruise=key[0], lookahead=key[1], crest_power=key[2], momentum=key[3], time_s=result.get('time_s'), feasible=result['feasible'], fuel_l=result.get('fuel_l'), message=result.get('message'), distance_km=result.get('distance_km')))
        if result['feasible'] and (best is None or result['fuel_l'] < best['fuel_l']):
            best = result
        return result
    manual = evaluate(params)
    for crest in (20.0, 60.0, 100.0):
        evaluate(dict(params, crest_power=crest, cruise=min(params['vmax'], max(params['average'], params['cruise']))))
    for axis, values in (('cruise', [params['average'] * 0.75, params['average'], params['average'] * 1.15]), ('momentum', [0.0, 0.25, 0.5, 1.0]), ('lookahead', [50.0, 250.0, 1000.0, 2000.0]), ('crest_power', [0.0, 20.0, 40.0, 60.0, 80.0, 100.0]), ('cruise', [params['average'], (params['average'] + params['vmax']) / 2, params['vmax']])):
        anchor = dict(best['params'] if best else params)
        for value in values:
            if axis == 'cruise':
                value = min(params['vmax'], max(params['vmin'], value))
            evaluate(dict(anchor, **{axis: value}))
    if best is not None:
        anchor = dict(best['params'])
        for scale in (0.7, 0.8, 0.9, 0.95, 1.05):
            evaluate(dict(anchor, cruise=max(params['vmin'], min(params['vmax'], anchor['cruise'] * scale))))
        anchor = dict(best['params'])
        for momentum in (0.0, 0.125, 0.25, 0.5, 0.75, 1.0):
            evaluate(dict(anchor, momentum=momentum))
    if best is not None:
        anchor = dict(best['params'])
        for cruise in (params['average'] * 0.85, params['average'], params['average'] * 1.05):
            for crest in (20.0, 40.0, 60.0, 100.0):
                evaluate(dict(anchor, cruise=max(params['vmin'], min(params['vmax'], cruise)), crest_power=crest))
    if best is None:
        groups = {}
        for t in trials:
            msg = t['message'] or 'Неизвестная причина'
            category = 'Минимальная скорость' if 'ниже минимума' in msg else 'Передачи и мощность' if 'передач' in msg else 'Средняя скорость' if 'среднюю скорость' in msg else 'Финишная скорость' if 'финише' in msg else 'Торможение' if 'торможение' in msg else 'Расчётные ограничения'
            groups.setdefault(category, []).append(t)
        lines = [f'Допустимый расчёт не найден: проверено {len(trials)} вариантов.']
        for category, items in groups.items():
            example = max(items, key=lambda t: t.get('distance_km') or 0)
            lines.append(f"{category}: {len(items)} вариантов. Пример: {example['message']}")
        lines.append('Это ограниченный поиск, а не доказательство непроходимости маршрута. Проверьте указанные ограничения и профиль высот. Изменять их только ради успешного расчёта не следует.')
        return dict(feasible=False, strategy='terrain', message='\n\n'.join(lines), search=trials)
    best['passes'] = len(trials)
    best['search'] = trials
    best['baseline'] = dict(fuel_l=manual['fuel_l'], time_s=manual['time_s']) if manual and manual['feasible'] else None
    best['optimized'] = True
    best['method'] = 'Bounded coordinate search of terrain policy; best tested feasible fuel, not global optimum'
    return best
