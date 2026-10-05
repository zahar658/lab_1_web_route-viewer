"""Educational spatial truck model, standard library. No calibrated vehicle data."""
import math
DEFAULTS = dict(mass=12000, cargo=10000, average=60, vmin=20, vmax=120, initial=40, final=40, dv=5, step=250, power=250, torque=1800, rpm_min=700, rpm_peak=1300, rpm_max=2300, torque_low=0.7, torque_high=0.65, final_drive=3.5, radius=0.5, efficiency=0.92, rolling=0.007, cd=0.65, area=8, air=1.225, rotation=1.05, accel=0.5, brake=1.5, adhesion=0.6, driven=0.55, bsfc=210, rpm_best=1300, load_best=0.75, rpm_penalty=0.25, load_penalty=0.6, idle=2, aux=2, density=0.835, gears=[12, 9.2, 7.1, 5.5, 4.2, 3.2, 2.5, 1.9, 1.45, 1.1, 0.85, 0.65])
LIMITS = dict(mass=(500, 100000), cargo=(0, 150000), average=(1, 150), vmin=(1, 100), vmax=(2, 150), initial=(1, 150), final=(1, 150), dv=(2, 20), step=(25, 2000), power=(10, 2000), torque=(50, 15000), torque_low=(0.1, 1), torque_high=(0.1, 1), rpm_min=(300, 3000), rpm_peak=(400, 4000), rpm_max=(500, 6000), final_drive=(1, 10), radius=(0.2, 1.5), efficiency=(0.5, 1), rolling=(0.001, 0.1), cd=(0.1, 2), area=(1, 20), air=(0.5, 2), rotation=(1, 1.5), accel=(0.05, 3), brake=(0.1, 8), adhesion=(0.05, 1.5), driven=(0.1, 1), bsfc=(150, 500), rpm_best=(400, 4000), load_best=(0.1, 1), rpm_penalty=(0, 5), load_penalty=(0, 5), idle=(0, 20), aux=(0, 50), density=(0.7, 1))

def parameters(given):
    p = DEFAULTS.copy()
    if not isinstance(given, dict):
        raise ValueError('Некорректные параметры грузовика.')
    p.update({k: v for k, v in given.items() if k in p})
    for k, (lo, hi) in LIMITS.items():
        v = p[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or (not math.isfinite(v)) or (not lo <= v <= hi):
            raise ValueError(f'Параметр {k}: допустимо от {lo} до {hi}.')
    if not p['vmin'] < p['vmax'] or not all((p['vmin'] <= p[k] <= p['vmax'] for k in ('initial', 'final'))):
        raise ValueError('Начальная и конечная скорости должны быть внутри диапазона min–max.')
    if not p['rpm_min'] < p['rpm_peak'] < p['rpm_max'] or not p['rpm_min'] <= p['rpm_best'] <= p['rpm_max']:
        raise ValueError('Проверьте диапазон оборотов, обороты пика момента и минимального расхода.')
    gears = p['gears']
    if not isinstance(gears, list) or not 1 <= len(gears) <= 16 or any((isinstance(g, bool) or not isinstance(g, (int, float)) or (not math.isfinite(g)) or (not 0.1 <= g <= 30) for g in gears)):
        raise ValueError('Передачи: от 1 до 16 чисел в диапазоне 0,1–30.')
    if any((a <= b for a, b in zip(gears, gears[1:]))):
        raise ValueError('Передаточные числа должны строго убывать.')
    return p

def road_grid(raw, step):
    if not isinstance(raw, list) or not 2 <= len(raw) <= 200000:
        raise ValueError('Нужно от 2 до 200 000 точек с высотами.')
    xs = []
    hs = []
    for row in raw:
        if not isinstance(row, list) or len(row) != 2 or any((isinstance(v, bool) or not isinstance(v, (int, float)) or (not math.isfinite(v)) for v in row)):
            raise ValueError('Для расчёта нужны расстояние и высота каждой точки без пропусков.')
        x, h = row
        if x < 0 or abs(h) > 15000 or (xs and x < xs[-1]):
            raise ValueError('Некорректные расстояния или высоты.')
        if xs and x == xs[-1]:
            if abs(h - hs[-1]) > 0.01:
                raise ValueError('Разные высоты при одинаковом расстоянии. Выберите сглаженный профиль.')
            continue
        xs.append(x)
        hs.append(h)
    if len(xs) < 2 or xs[-1] - xs[0] <= 0:
        raise ValueError('Маршрут имеет нулевую длину.')
    offset = xs[0]
    xs = [x - offset for x in xs]
    grid = [(0, hs[0])]
    for i in range(1, len(xs)):
        n = math.ceil((xs[i] - xs[i - 1]) / step)
        if len(grid) + n > 20000:
            raise ValueError('Расчётная сетка превышает 20 000 участков. Увеличьте максимальный шаг или используйте более короткий маршрут.')
        for j in range(1, n + 1):
            f = j / n
            grid.append((xs[i - 1] + f * (xs[i] - xs[i - 1]), hs[i - 1] + f * (hs[i] - hs[i - 1])))
    return grid

def capacity(rpm, p):
    if not p['rpm_min'] <= rpm <= p['rpm_max']:
        return 0
    if rpm <= p['rpm_peak']:
        fraction = p['torque_low'] + (1 - p['torque_low']) * (rpm - p['rpm_min']) / (p['rpm_peak'] - p['rpm_min'])
    else:
        fraction = 1 - (1 - p['torque_high']) * (rpm - p['rpm_peak']) / (p['rpm_max'] - p['rpm_peak'])
    return min(p['power'], p['torque'] * fraction * rpm * 2 * math.pi / 60000)
