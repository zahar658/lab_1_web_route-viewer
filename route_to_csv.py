#!/usr/bin/env python3
"""Python 3.10+, standard library only. Original API vertices plus a separate distance-smoothed profile; no resampling. See --help. Coordinates: longitude latitude."""
import argparse
import bisect
import csv
from decimal import Decimal
import getpass
import json
import math
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

R = 6371008.8
ENDPOINT = 'https://api.openrouteservice.org/v2/directions/driving-car/geojson'


def distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*R*math.asin(math.sqrt(min(1, max(0, h))))


def bearing(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    return math.degrees(math.atan2(math.sin(lon2-lon1)*math.cos(lat2), math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1))) % 360


def smooth_heights(rows, window):
    """Distance-weighted mean of the piecewise-linear height profile.

    Duplicate distances use their mean height in the smoothing model only.
    Raw rows are never changed. Windows are truncated at the route boundaries.
    """
    if not math.isfinite(window) or window <= 0:
        raise ValueError('Smoothing window must be positive and finite.')
    xs, hs, counts = [], [], []
    for row in rows:
        x, h = row['distance_from_start_m'], float(row['elevation_m'])
        if xs and x == xs[-1]:
            counts[-1] += 1
            hs[-1] += (h-hs[-1])/counts[-1]
        else:
            xs.append(x); hs.append(h); counts.append(1)
    if len(xs) == 1:
        return [hs[0]]*len(rows)
    area = [0.0]
    for i in range(1, len(xs)):
        area.append(area[-1]+(hs[i-1]+hs[i])*(xs[i]-xs[i-1])/2)
    def integral(x):
        i = min(max(bisect.bisect_right(xs, x)-1, 0), len(xs)-2)
        dx = x-xs[i]
        slope = (hs[i+1]-hs[i])/(xs[i+1]-xs[i])
        return area[i]+hs[i]*dx+slope*dx*dx/2
    result = []
    for row in rows:
        x = row['distance_from_start_m']
        left, right = max(xs[0], x-window/2), min(xs[-1], x+window/2)
        result.append((integral(right)-integral(left))/(right-left))
    return result


def build_rows(data, smooth_window=250):
    """One CSV row per API vertex, including duplicates. No resampling."""
    try:
        geometry = data['features'][0]['geometry']
        if geometry['type'] != 'LineString':
            raise ValueError('Expected LineString geometry.')
        coords = geometry['coordinates']
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError('API response does not contain a route LineString.') from exc
    if not isinstance(coords, list) or len(coords) < 2:
        raise ValueError('Route must contain at least two vertices.')
    rows, total = [], 0.0
    for i, p in enumerate(coords):
        if not isinstance(p, list) or len(p) != 3:
            raise ValueError(f'Point {i}: expected longitude, latitude, elevation.')
        if any(isinstance(v, bool) or not isinstance(v, (int, float, Decimal)) or not math.isfinite(v) for v in p):
            raise ValueError(f'Point {i}: invalid numeric coordinate/elevation.')
        if not -180 <= p[0] <= 180 or not -90 <= p[1] <= 90:
            raise ValueError(f'Point {i}: invalid coordinate range.')
        row = dict(point_id=i, latitude=p[1], longitude=p[0], elevation_m=p[2],
                   distance_from_start_m=total, segment_length_m='', elevation_delta_m='',
                   slope_pct='', slope_deg='', bearing_deg='')
        if i:
            previous = coords[i-1]
            ds = distance(previous, p)
            dh = p[2] - previous[2]
            total += ds
            row.update(distance_from_start_m=total, segment_length_m=ds, elevation_delta_m=dh)
            # Preserve coincident vertices, but never divide by zero.
            if ds > 0:
                row.update(slope_pct=100*float(dh)/ds,
                           slope_deg=math.degrees(math.atan2(float(dh), ds)),
                           bearing_deg=bearing(previous, p))
        rows.append(row)
    smoothed = smooth_heights(rows, smooth_window)
    for i, row in enumerate(rows):
        row.update(elevation_smoothed_m=smoothed[i], elevation_delta_smoothed_m='',
                   slope_smoothed_pct='', slope_smoothed_deg='', smoothing_window_m=smooth_window)
        if i:
            dh = smoothed[i]-smoothed[i-1]
            ds = row['segment_length_m']
            row['elevation_delta_smoothed_m'] = dh
            if ds > 0:
                row['slope_smoothed_pct'] = 100*dh/ds
                row['slope_smoothed_deg'] = math.degrees(math.atan2(dh, ds))
    return rows, total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', nargs=2, type=float, default=[131.8855,43.1155], metavar=('LON','LAT'), help='Approximate central Vladivostok')
    parser.add_argument('--end', nargs=2, type=float, default=[135.0719,48.4802], metavar=('LON','LAT'), help='Approximate central Khabarovsk')
    parser.add_argument('--out', type=Path, default=Path('output'), help='Output parent directory')
    parser.add_argument('--from-json', type=Path, help='Reprocess saved route_raw.json offline without an API key')
    parser.add_argument('--smooth-window', type=float, default=250, help='Distance-weighted smoothing window in metres (default 250)')
    args = parser.parse_args()
    if not math.isfinite(args.smooth_window) or args.smooth_window <= 0:
        parser.error('Smoothing window must be positive and finite.')
    for lon, lat in [args.start, args.end]:
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            parser.error('Coordinates must be longitude latitude, in valid ranges.')
    body = dict(coordinates=[args.start,args.end], elevation=True, instructions=False, geometry_simplify=False)
    if args.from_json:
        raw_bytes = args.from_json.read_bytes()
    else:
        key = os.environ.get('ORS_API_KEY','').strip() or getpass.getpass('ORS API key (hidden input): ').strip()
        if not key:
            raise ValueError('API key is empty.')
        req = Request(ENDPOINT, data=json.dumps(body).encode('utf-8'), headers={'Authorization':key, 'Content-Type':'application/json', 'Accept':'application/geo+json'})
        print('Requesting route from openrouteservice...')
        try:
            with urlopen(req, timeout=180) as response:
                raw_bytes = response.read()
        except HTTPError as exc:
            hints = {401:'Check API key.',403:'Check API key and account access.',429:'Quota exceeded; try later.',400:'Check route parameters.',404:'Endpoint or route not found.'}
            raise ValueError(f'ORS HTTP {exc.code}. {hints.get(exc.code, "Service error; try again later.")}') from None
        except (URLError, TimeoutError) as exc:
            raise ValueError('Connection failed or timed out. Check internet access and retry.') from exc
    data = json.loads(raw_bytes.decode('utf-8-sig'), parse_float=Decimal)
    folder = args.out / datetime.now(timezone.utc).strftime('route_%Y%m%d_%H%M%S_%f')
    folder.mkdir(parents=True, exist_ok=False)
    (folder/'route_raw.json').write_bytes(raw_bytes)
    rows, length = build_rows(data, args.smooth_window)
    with (folder/'route.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lengths = [r['segment_length_m'] for r in rows[1:]]
    metadata = dict(
        created_utc=datetime.now(timezone.utc).isoformat(),
        source='openrouteservice / OpenStreetMap contributors', endpoint=ENDPOINT,
        request=body if not args.from_json else None,
        input_json=str(args.from_json) if args.from_json else None,
        processing='original API vertices preserved; separate distance-smoothed height and slope columns',
        smoothing_window_m=args.smooth_window,
        smoothing_method='distance-weighted mean of piecewise-linear heights; truncated window at endpoints; duplicate-distance heights averaged only for smoothing',
        row_count=len(rows), calculated_length_m=length,
        zero_length_segments=sum(d == 0 for d in lengths),
        min_segment_length_m=min(lengths), max_segment_length_m=max(lengths),
        mean_segment_length_m=sum(lengths)/len(lengths),
        distance_method='spherical great-circle, radius 6371008.8 m; cumulative along geometry',
        slope_method='incoming segment: 100 * height difference / horizontal segment distance',
        notes=['Original numeric coordinate/elevation values preserved using Decimal parsing.',
               'Original JSON bytes preserved in route_raw.json.',
               'API vertices may already reflect processing by the provider.',
               'First row incoming-segment fields are empty.',
               'Coincident vertices retained; slope and bearing blank for zero-length segments.',
               'Short segments can produce large slopes; no clipping applied.'])
    (folder/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Done: {len(rows)} rows, {length/1000:.2f} km')
    print(f'CSV: {(folder / "route.csv").resolve()}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('Cancelled.', file=sys.stderr)
        sys.exit(1)
