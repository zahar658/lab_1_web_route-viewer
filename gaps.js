// Пропуски навигации: удаляем строки, сохраняя остальные значения CSV.
(function (root) {
  function randomSequence(seed) {
    let value = seed >>> 0;
    return () => {
      value += 0x6D2B79F5;
      let n = Math.imul(value ^ value >>> 15, 1 | value);
      n ^= n + Math.imul(n ^ n >>> 7, 61 | n);
      return ((n ^ n >>> 14) >>> 0) / 4294967296;
    };
  }

  function cutRows(text, spacingKm, lengthKm, seed) {
    if (![spacingKm, lengthKm].every(n => Number.isFinite(n) && n >= 0.001 && n <= 10000)) {
      throw Error('Интервал и длина должны быть от 0,001 до 10 000 км.');
    }
    if (!Number.isInteger(seed) || seed < 0 || seed > 4294967295) throw Error('Число эксперимента: целое от 0 до 4294967295.');
    const route = RouteData.parse(text);
    const rows = RouteData.csv(text);
    const header = rows.shift();
    if (!header.map(s => s.trim().toLowerCase()).includes('distance_from_start_m')) {
      throw Error('Для удаления по километрам нужен столбец distance_from_start_m.');
    }
    if (route.some((p, i) => p.providedDistance === null || p.providedDistance < 0 || (i && p.providedDistance < route[i - 1].providedDistance))) {
      throw Error('Расстояния должны быть заполнены и идти по возрастанию.');
    }
    const random = randomSequence(seed);
    const draw = mean => mean * (0.5 + random()) * 1000;
    const total = route.at(-1).distance;
    const intervals = [];
    let position = draw(spacingKm);
    while (position < total) {
      if (intervals.length >= 10000) throw Error('Слишком много пропусков. Увеличьте интервал.');
      const end = Math.min(total, position + draw(lengthKm));
      intervals.push([position, end]);
      position = end + draw(spacingKm);
    }
    let interval = 0, removed = 0;
    const kept = rows.filter((row, i) => {
      if (i === 0 || i === rows.length - 1) return true;
      const distance = route[i].distance;
      while (interval < intervals.length && distance >= intervals[interval][1]) interval++;
      const drop = interval < intervals.length && distance >= intervals[interval][0] && distance < intervals[interval][1];
      if (drop) removed++;
      return !drop;
    });
    const quote = value => '"' + String(value).replaceAll('"', '""') + '"';
    return {text: '\uFEFF' + [header, ...kept].map(row => row.map(quote).join(',')).join('\r\n'), removed, total: rows.length, intervals};
  }
  root.RouteGapsCore = {cutRows};
  if (typeof module !== 'undefined') module.exports = root.RouteGapsCore;
})(typeof window !== 'undefined' ? window : globalThis);

if (typeof window !== 'undefined' && typeof document !== 'undefined') (() => {
  const get = id => document.getElementById(id);
  let source = null, comparison = null, comparisonLayer = null, output = null;
  let originalLine = null, originalEndpoints = [];
  let fileVersion = 0;
  const note = text => get('gaps-status').textContent = text;

  function visibility() {
    if (!map) return;
    if (originalLine) get('show-original').checked ? originalLine.addTo(map) : map.removeLayer(originalLine);
    originalEndpoints.forEach(layer => get('show-original').checked ? layer.addTo(map) : map.removeLayer(layer));
    if (comparisonLayer) get('show-damaged').checked ? comparisonLayer.addTo(map) : map.removeLayer(comparisonLayer);
    if (comparisonLayer && get('show-damaged').checked) comparisonLayer.eachLayer(layer => layer.bringToFront?.());
  }

  function drawComparison() {
    if (comparisonLayer && map) map.removeLayer(comparisonLayer);
    comparisonLayer = null;
    if (!comparison || !map) return;
    // Сопоставляем координаты и идентификатор: не соединяем удалённые куски прямой.
    const key = p => `${p.id}|${p.lat}|${p.lon}`;
    const positions = new Map();
    if (source) source.points.forEach((p, i) => {
      const k = key(p); if (!positions.has(k)) positions.set(k, []); positions.get(k).push(i);
    });
    let previous = -1, matched = true;
    const indices = comparison.points.map(p => {
      const index = (positions.get(key(p)) || []).find(i => i > previous);
      if (index === undefined) { matched = false; return -1; }
      previous = index; return index;
    });
    let segments = [[]];
    comparison.points.forEach((p, i) => {
      if (matched && i && indices[i] !== indices[i - 1] + 1) segments.push([]);
      segments.at(-1).push([p.lat, p.lon]);
    });
    comparisonLayer = L.layerGroup();
    segments.forEach(segment => {
      const layer = segment.length > 1 ? L.polyline(segment, {color: '#ed741b', weight: 3, opacity: 1}) : L.circleMarker(segment[0], {radius: 3, color: '#ed741b'});
      comparisonLayer.addLayer(layer);
    });
    get('comparison-name').textContent = comparison.name;
    note(matched ? `Файл 2: ${comparison.points.length} точек. Пропуски показаны разрывами линии.` : 'Файл 2 отображён оранжевым. Он не сопоставлен с исходным по ID и координатам: пропуски автоматически не определены.');
    visibility();
  }

  window.RouteGaps = {restoreVisibility: visibility, onLoad(text, name) {
    if (map && originalLine) map.removeLayer(originalLine);
    if (map) originalEndpoints.forEach(layer => map.removeLayer(layer));
    originalLine = line; originalEndpoints = [...endpoints];
    fileVersion++;
    source = {text, name, points: RouteData.parse(text)};
    comparison = null; output = null;
    if (comparisonLayer && map) map.removeLayer(comparisonLayer);
    comparisonLayer = null;
    get('original-name').textContent = name;
    get('comparison-name').textContent = 'не загружен';
    get('cut-route').disabled = false;
    get('save-damaged').disabled = true;
    get('show-original').checked = true;
    visibility();
    note('Файл 1 готов. Создайте файл 2. Для восстановления сохранённого CSV используйте верхнюю панель восстановления. Графики и расчёт относятся к файлу 1.');
  }};
  get('show-original').onchange = visibility;
  get('show-damaged').onchange = visibility;
  get('cut-route').onclick = () => {
    if (!source) return;
    try {
      const result = RouteGapsCore.cutRows(source.text, Number(get('gap-spacing').value), Number(get('gap-length').value), Number(get('gap-seed').value));
      fileVersion++;
      output = result.text;
      comparison = {name: '2.csv', points: RouteData.parse(output)};
      get('show-damaged').checked = true;
      drawComparison();
      get('save-damaged').disabled = false;
      note(`Удалено ${result.removed} из ${result.total} строк (${(100 * result.removed / result.total).toFixed(1)}%). Задано интервалов: ${result.intervals.length}. Начало и конец сохранены. Исходный файл не изменён.${result.removed ? '' : ' Пропуски не попали на точки: измените настройки.'}`);
    } catch (error) { note(error.message); }
  };
  get('save-damaged').onclick = async () => {
    if (!output) return;
    const blob = new Blob([output], {type: 'text/csv;charset=utf-8'});
    try {
      if (window.showSaveFilePicker) {
        const handle = await window.showSaveFilePicker({suggestedName: '2.csv', types: [{description: 'Маршрут с пропусками', accept: {'text/csv': ['.csv']}}]});
        if (source && handle.name === source.name) { note('Выберите другое имя файла, чтобы не перезаписать исходный CSV.'); return; }
        const stream = await handle.createWritable(); await stream.write(blob); await stream.close();
      } else {
        const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = '2.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
      }
      note('Файл 2 сохранён. Его можно загрузить повторно для сравнения.');
    } catch (error) { note(error.name === 'AbortError' ? 'Сохранение отменено.' : 'Не удалось сохранить файл 2.'); }
  };
})();
