"""Local route viewer and ORS bridge. Python 3.10+, standard library only."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from functools import partial
import threading
import webbrowser
import json
from decimal import Decimal
import csv
import io
import math
import re
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
import route_to_csv
import terrain_strategy
import recovery
ROOT = Path(__file__).resolve().parent
MODEL_LOCK = threading.Lock()

def point(value):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('Укажите координаты обеих точек.')
    if any((isinstance(v, bool) or not isinstance(v, (int, float)) or (not math.isfinite(v)) for v in value)):
        raise ValueError('Координаты должны быть конечными числами.')
    if not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90:
        raise ValueError('Широта: от −90 до 90; долгота: от −180 до 180.')
    return value

def api_key(body):
    key = body.get('key')
    if not isinstance(key, str) or not key.strip() or len(key) > 4096 or any((ord(c) < 33 or ord(c) > 126 for c in key.strip())):
        raise ValueError('Введите корректный API-ключ openrouteservice.')
    return key.strip()

def ors(url, key, body=None):
    accept = 'application/geo+json' if url == route_to_csv.ENDPOINT else 'application/json'
    request = Request(url, data=None if body is None else json.dumps(body).encode(), headers={'Authorization': key, 'Content-Type': 'application/json', 'Accept': accept})
    try:
        with urlopen(request, timeout=180) as response:
            return json.load(response, parse_float=Decimal) if url == route_to_csv.ENDPOINT else json.load(response)
    except HTTPError as exc:
        hints = {400: 'Проверьте точки и ограничения маршрута.', 401: 'Неверный API-ключ.', 403: 'Проверьте API-ключ и доступ к сервису.', 404: 'Место или маршрут не найдены.', 406: 'Сервис отклонил запрошенный формат ответа (заголовок Accept).', 413: 'Маршрут превышает ограничения сервиса.', 429: 'Лимит запросов исчерпан. Повторите позже.'}
        raise ValueError(f"openrouteservice: HTTP {exc.code}. {hints.get(exc.code, 'Сервис временно недоступен.')}") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError('Не удалось связаться с openrouteservice. Проверьте интернет и повторите запрос.') from None
    except (json.JSONDecodeError, UnicodeError):
        raise ValueError('Сервис вернул некорректный ответ.') from None

def generate(body):
    key = api_key(body)
    coordinates = body.get('coordinates')
    if not isinstance(coordinates, list) or not 2 <= len(coordinates) <= 50:
        raise ValueError('Отметьте на карте от 2 до 50 точек в порядке движения.')
    coordinates = [point(value) for value in coordinates]
    for index, (first, second) in enumerate(zip(coordinates, coordinates[1:]), 1):
        if route_to_csv.distance(first, second) < 1:
            raise ValueError(f'Точки {index} и {index + 1} должны различаться минимум на 1 метр.')
    window = body.get('smooth_window', 250)
    if isinstance(window, bool) or not isinstance(window, (int, float)) or (not math.isfinite(window)) or (not 1 <= window <= 10000):
        raise ValueError('Окно сглаживания должно быть от 1 до 10 000 метров.')
    data = ors(route_to_csv.ENDPOINT, key, dict(coordinates=coordinates, elevation=True, instructions=False, geometry_simplify=False))
    try:
        rows, length = route_to_csv.build_rows(data, window)
    except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError):
        raise ValueError('API не вернул пригодный маршрут с высотами. Проверьте точки и доступность автомобильных дорог.') from None
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8-sig')

class Handler(SimpleHTTPRequestHandler):

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, max-age=0')
        super().end_headers()

    def reply(self, code, payload, content_type='application/json; charset=utf-8'):
        data = json.dumps(payload, ensure_ascii=False).encode() if isinstance(payload, dict) else payload
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        expected = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected or self.headers.get('Origin') != f'http://{expected}':
            self.reply(403, {'error': 'Запрос разрешён только со страницы локального приложения.'})
            return
        if self.path not in ('/api/generate', '/api/optimize', '/api/recover'):
            self.reply(404, {'error': 'Неизвестный запрос.'})
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Ожидается JSON.')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= (20 * 1024 * 1024 if self.path in ('/api/optimize', '/api/recover') else 16384):
                raise ValueError('Некорректный размер запроса.')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('Некорректный запрос.')
            if self.path == '/api/optimize':
                if not MODEL_LOCK.acquire(blocking=False):
                    self.reply(409, {'error': 'Другой расчёт ещё выполняется. Дождитесь его завершения.'})
                    return
                try:
                    strategy = body.get('strategy', 'terrain')
                    if strategy != 'terrain':
                        raise ValueError('Неизвестная стратегия.')
                    self.reply(200, terrain_strategy.optimize(body))
                finally:
                    MODEL_LOCK.release()
            elif self.path == '/api/recover':
                key = api_key(body)
                def request_gap(coordinates):
                    return ors(route_to_csv.ENDPOINT, key, dict(coordinates=coordinates, elevation=True, instructions=False, geometry_simplify=False))
                self.reply(200, recovery.recover(body, request_gap))
            else:
                self.reply(200, generate(body), 'text/csv; charset=utf-8')
        except (ValueError, UnicodeError) as exc:
            self.reply(400, {'error': str(exc) if not isinstance(exc, json.JSONDecodeError) else 'Некорректный JSON.'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.reply(500, {'error': 'Не удалось обработать маршрут. Попробуйте ещё раз.'})
if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'Route viewer: {url}\nKeep this window open. Press Ctrl+C to stop.')
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
