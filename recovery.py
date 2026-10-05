"""Восстановление по одному повреждённому CSV. Файлы с диска не читаются."""
import csv
import io
import math
from decimal import Decimal

import route_to_csv


def read_observations(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Выберите повреждённый CSV.')
    text = text.lstrip('\ufeff')
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = reader.fieldnames or []
    names = {name.strip().lower(): name for name in headers}
    if len(names) != len(headers):
        raise ValueError('В CSV повторяются имена столбцов.')
    required = ('longitude', 'latitude', 'elevation_m')
    if not all(name in names for name in required):
        raise ValueError('В CSV нужны longitude, latitude и elevation_m.')
    observations = []
    for number, row in enumerate(reader, 2):
        try:
            point = [Decimal(row[names[name]].strip().replace(',', '.')) for name in required]
            if not all(value.is_finite() for value in point):
                raise ValueError()
            if not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90 or abs(point[2]) > 15000:
                raise ValueError()
        except (ValueError, TypeError, AttributeError, ArithmeticError):
            raise ValueError(f'Строка {number}: некорректные координаты или высота.') from None
        observations.append(point)
        if len(observations) > 100000:
            raise ValueError('Максимум 100 000 наблюдений.')
    if len(observations) < 2:
        raise ValueError('Нужно минимум две сохранившиеся точки.')
    return observations


def recover(body, request_route):
    """request_route получает только две граничные координаты и возвращает GeoJSON."""
    # ID, прежние расстояния и уклоны намеренно не используются.
    observations = read_observations(body.get('csv'))
    threshold = body.get('jump_km', 1)
    window = body.get('smooth_window', 250)
    for value, low, high, label in [(threshold, .001, 1000, 'Порог скачка, км'), (window, 1, 10000, 'Окно сглаживания, м')]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{label}: допустимо от {low} до {high}.')
    gaps = []
    for index in range(1, len(observations)):
        jump = route_to_csv.distance(observations[index-1], observations[index])
        if jump > threshold * 1000:
            gaps.append((index, jump))
    if len(gaps) > 50:
        raise ValueError(f'Найдено {len(gaps)} скачков. Максимум 50 запросов за восстановление; увеличьте порог скачка.')
    missing = dict(gaps)
    coordinates = [observations[0]]
    provenance = [('observed', 0)]
    reports = []
    for index in range(1, len(observations)):
        if index in missing:
            first, last = observations[index-1], observations[index]
            try:
                data = request_route([[float(first[0]), float(first[1])], [float(last[0]), float(last[1])]])
                rows, _ = route_to_csv.build_rows(data, window)
                geometry = [[row['longitude'], row['latitude'], row['elevation_m']] for row in rows]
                snap_start = route_to_csv.distance(first, geometry[0])
                snap_end = route_to_csv.distance(last, geometry[-1])
                if max(snap_start, snap_end) > 100:
                    raise ValueError('Дорога из API удалена от граничной точки более чем на 100 м.')
            except (ValueError, KeyError, TypeError, IndexError) as error:
                raise ValueError(f'Скачок {len(reports)+1}, между наблюдениями {index} и {index+1}, {missing[index]/1000:.3f} км: {error}. Файл 3 не создан.') from None
            inserted = 0
            for point in geometry:
                if route_to_csv.distance(coordinates[-1], point) < .1 or route_to_csv.distance(point, last) < .1:
                    continue
                coordinates.append(point)
                provenance.append(('api', len(reports)+1))
                inserted += 1
            reports.append(dict(before_observation=index, after_observation=index+1,
                                jump_km=missing[index]/1000, inserted=inserted,
                                snap_start_m=snap_start, snap_end_m=snap_end))
        coordinates.append(observations[index])
        provenance.append(('observed', 0))
        if len(coordinates) > 200000:
            raise ValueError('После восстановления больше 200 000 точек. Выберите более короткий маршрут.')
    # Геометрия изменилась: пересчитываем расстояния, уклоны и сглаживание.
    rows, length = route_to_csv.build_rows({'features': [{'geometry': {'type': 'LineString', 'coordinates': coordinates}}]}, window)
    for row, (source, gap) in zip(rows, provenance):
        row['point_source'] = source
        row['recovery_gap'] = gap
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return dict(csv='\ufeff'+output.getvalue(), report=dict(observed=len(observations),
                inserted=len(coordinates)-len(observations), gaps=len(gaps), length_km=length/1000,
                details=reports))
