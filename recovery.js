// Восстановление получает файл только из своего поля загрузки.
// Основной маршрут, points и состояние RouteGaps здесь не используются.
(() => {
  const element = id => document.getElementById(id);
  let damagedText = null;
  let damagedName = '';
  let inputPoints = [];
  let inputLayer = null;
  let recoveredLayer = null;
  let recoveredText = null;
  let busy = false;
  let version = 0;
  const message = text => element('recovery-status').textContent = text;

  function removeResult() {
    recoveredText = null;
    element('save-recovered').disabled = true;
    if (map && recoveredLayer) map.removeLayer(recoveredLayer);
    recoveredLayer = null;
  }

  function visibility() {
    if (!map) return;
    if (inputLayer) element('show-recovery-input').checked ? inputLayer.addTo(map) : map.removeLayer(inputLayer);
    if (recoveredLayer) element('show-recovered').checked ? recoveredLayer.addTo(map) : map.removeLayer(recoveredLayer);
  }

  function drawInput() {
    if (!map) return;
    if (inputLayer) map.removeLayer(inputLayer);
    inputLayer = L.layerGroup();
    // Наблюдения рисуем точками, чтобы не выдавать прямые между ними за дорогу.
    inputPoints.forEach(point => inputLayer.addLayer(L.circleMarker([point.lat, point.lon], {
      radius: 3, color: '#ed741b', weight: 1, fillOpacity: .8
    })));
    visibility();
  }

  function lock(value) {
    busy = value;
    ['recovery-file', 'recovery-key', 'recovery-jump', 'recovery-window'].forEach(id => element(id).disabled = value);
    element('recover-route').disabled = value || !damagedText;
  }

  element('recovery-file').onchange = async event => {
    const file = event.target.files[0];
    if (!file) return;
    const token = ++version;
    damagedText = null; removeResult(); lock(false);
    if (map && inputLayer) map.removeLayer(inputLayer);
    inputLayer = null; inputPoints = [];
    try {
      if (file.size > 10 * 1024 * 1024) throw Error('Максимальный размер повреждённого CSV — 10 МБ.');
      const text = await file.text();
      const parsed = RouteData.parse(text);
      if (version !== token) return;
      damagedText = text; damagedName = file.name; inputPoints = parsed;
      element('show-recovery-input').checked = true;
      drawInput();
      if (map) map.fitBounds(L.latLngBounds(inputPoints.map(p => [p.lat, p.lon])), {padding: [30, 30]});
      message(`Загружен ${file.name}: ${parsed.length} наблюдений. Файл 1 для восстановления не нужен.`);
      lock(false);
    } catch (error) { if (version === token) message(error.message); }
  };
  ['recovery-jump', 'recovery-window'].forEach(id => element(id).addEventListener('input', removeResult));
  element('show-recovery-input').onchange = visibility;
  element('show-recovered').onchange = visibility;

  element('recover-route').onclick = async () => {
    if (busy || !damagedText) return;
    const key = element('recovery-key').value.trim();
    if (!key) { message('Введите API-ключ openrouteservice.'); return; }
    const jump = Number(element('recovery-jump').value);
    const smoothing = Number(element('recovery-window').value);
    if (!Number.isFinite(jump) || jump < .001 || jump > 1000 || !Number.isFinite(smoothing) || smoothing < 1 || smoothing > 10000) {
      message('Порог скачка: 0,001–1000 км. Окно сглаживания: 1–10 000 м.'); return;
    }
    removeResult(); lock(true);
    message('Ищем скачки и запрашиваем предполагаемые пропущенные участки. При нескольких пропусках это может занять несколько минут.');
    const started = Date.now();
    const timer = setInterval(() => { element('recover-route').textContent = `Восстановление: ${Math.floor((Date.now()-started)/1000)} с`; }, 1000);
    try {
      const response = await fetch('/api/recover', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({csv: damagedText, key, jump_km: jump, smooth_window: smoothing})
      });
      const result = await response.json();
      if (!response.ok) throw Error(result.error || 'Ошибка восстановления.');
      const route = RouteData.parse(result.csv);
      recoveredText = result.csv;
      if (map) {
        recoveredLayer = L.polyline(route.map(p => [p.lat, p.lon]), {color: '#8547bc', weight: 4, opacity: .85});
        element('show-recovered').checked = true; visibility();
      }
      element('save-recovered').disabled = false;
      const report = result.report;
      message(`Скачков: ${report.gaps}. Добавлено точек API: ${report.inserted}. Сохранено наблюдений: ${report.observed}.\nДлина результата: ${report.length_km.toFixed(2)} км. ${report.gaps ? 'Полученный маршрут — предположение API. Точки API помечены в CSV.' : 'Скачков выше порога нет: точки не добавлялись.'}\nРасстояния и уклоны пересчитаны. Сохраните файл 3; для расчёта движения откройте его обычной кнопкой «Открыть маршрут».`);
    } catch (error) {
      message(error instanceof TypeError ? 'Нет связи с сервером. Проверьте окно START.bat.' : error.message);
    } finally {
      clearInterval(timer); element('recover-route').textContent = 'Восстановить файл 2';
      element('recovery-key').value = ''; lock(false);
    }
  };
  element('save-recovered').onclick = async () => {
    if (!recoveredText) return;
    if (!window.showSaveFilePicker) { message('Откройте приложение в Edge или Chrome для выбора папки сохранения.'); return; }
    try {
      const handle = await window.showSaveFilePicker({suggestedName: '3.csv', types: [{description: 'Восстановленный маршрут', accept: {'text/csv': ['.csv']}}]});
      if (handle.name === damagedName) { message('Выберите другое имя, чтобы сохранить повреждённый исходник.'); return; }
      const stream = await handle.createWritable(); await stream.write(recoveredText); await stream.close();
      message(`Файл «${handle.name}» сохранён. Исходный повреждённый CSV не изменён.`);
    } catch (error) { message(error.name === 'AbortError' ? 'Сохранение отменено.' : 'Не удалось сохранить файл 3.'); }
  };
})();
