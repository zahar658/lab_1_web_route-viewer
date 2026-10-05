// Создание маршрута по точкам на карте. Координаты API: долгота, широта.
(() => {
  const element = id => document.getElementById(id);
  const dialog = element('route-dialog');
  let pickerMap = null;
  let markers = [];
  let selectedPoints = [];
  let generatedFile = null;
  let busy = false;

  function showMessage(text) {
    element('generator-status').textContent = text;
  }

  function discardFile() {
    generatedFile = null;
    element('save-generated').disabled = true;
  }

  function updateButtons() {
    element('generate-route').disabled = busy || selectedPoints.length < 2;
    element('clear-route-points').disabled = busy;
    element('api-key').disabled = busy;
    element('smooth-window').disabled = busy;
    markers.forEach(marker => busy ? marker.dragging.disable() : marker.dragging.enable());
    element('route-points-list').querySelectorAll('button').forEach(button => button.disabled = busy);
  }

  function redrawPoints() {
    markers.forEach(marker => pickerMap.removeLayer(marker));
    markers = [];
    const list = element('route-points-list');
    list.replaceChildren();
    selectedPoints.forEach((coordinates, index) => {
      const name = index === 0 ? 'Старт' : index === selectedPoints.length - 1 ? 'Финиш' : 'Промежуточная';
      const marker = L.marker([coordinates[1], coordinates[0]], {
        draggable: !busy,
        icon: L.divIcon({className: 'route-number', html: String(index + 1), iconSize: [28, 28], iconAnchor: [14, 14]})
      }).addTo(pickerMap).bindTooltip(`${index + 1}. ${name}`);
      marker.on('dragend', () => {
        const position = marker.getLatLng();
        selectedPoints[index] = [position.lng, position.lat];
        discardFile();
        redrawPoints();
      });
      markers.push(marker);
      const row = document.createElement('li');
      row.append(document.createTextNode(`${name}: ${coordinates[1].toFixed(5)}, ${coordinates[0].toFixed(5)}`));
      function addButton(text, action) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = text;
        button.onclick = () => { if (!busy) { action(); discardFile(); redrawPoints(); } };
        row.append(button);
      }
      if (index > 0) addButton('↑', () => {
        [selectedPoints[index - 1], selectedPoints[index]] = [selectedPoints[index], selectedPoints[index - 1]];
      });
      if (index < selectedPoints.length - 1) addButton('↓', () => {
        [selectedPoints[index + 1], selectedPoints[index]] = [selectedPoints[index], selectedPoints[index + 1]];
      });
      addButton('Удалить', () => selectedPoints.splice(index, 1));
      list.append(row);
    });
    updateButtons();
  }

  element('new-route').onclick = () => {
    pauseMotion();
    dialog.showModal();
    if (!pickerMap) {
      if (!window.L) { showMessage('Не удалось загрузить Leaflet. Проверьте папку vendor.'); return; }
      pickerMap = L.map('route-picker-map', {doubleClickZoom: false}).setView([55.75, 37.62], 6);
      const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; OpenStreetMap'
      }).addTo(pickerMap);
      tiles.on('tileerror', () => element('picker-warning').textContent = 'Фоновая карта недоступна. Проверьте интернет.');
      tiles.on('tileload', () => element('picker-warning').textContent = '');
      pickerMap.on('click', event => {
        if (busy) return;
        if (selectedPoints.length >= 50) { showMessage('Можно выбрать не больше 50 точек.'); return; }
        const position = event.latlng.wrap();
        selectedPoints.push([position.lng, position.lat]);
        discardFile();
        showMessage('');
        redrawPoints();
      });
    }
    requestAnimationFrame(() => pickerMap.invalidateSize());
    updateButtons();
  };

  element('clear-route-points').onclick = () => {
    selectedPoints = [];
    discardFile();
    redrawPoints();
    showMessage('Отметьте новые точки на карте.');
  };
  element('close-generator').onclick = () => {
    if (busy) showMessage('Дождитесь окончания построения маршрута.');
    else dialog.close();
  };
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => element('api-key').value = '');
  element('smooth-window').addEventListener('input', discardFile);

  element('route-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || selectedPoints.length < 2) return;
    const key = element('api-key').value.trim();
    if (!key) { showMessage('Введите API-ключ.'); return; }
    for (let i = 1; i < selectedPoints.length; i++) {
      const [a, b] = [selectedPoints[i - 1], selectedPoints[i]];
      if (RouteData.distance({lat: a[1], lon: a[0]}, {lat: b[1], lon: b[0]}) < 1) {
        showMessage(`Точки ${i} и ${i + 1} должны различаться минимум на 1 метр.`);
        return;
      }
    }
    discardFile();
    busy = true;
    updateButtons();
    showMessage('Строим маршрут через выбранные точки. Это может занять до трёх минут…');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 200000);
    try {
      const response = await fetch('/api/generate', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, signal: controller.signal,
        body: JSON.stringify({key, coordinates: selectedPoints, smooth_window: Number(element('smooth-window').value)})
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Не удалось построить маршрут.');
      }
      generatedFile = await response.blob();
      element('save-generated').disabled = false;
      showMessage('Маршрут готов. Нажмите «Сохранить CSV» и выберите папку.');
    } catch (error) {
      showMessage(error.name === 'AbortError' ? 'Сервис не ответил вовремя. Повторите запрос.' : error.message);
    } finally {
      clearTimeout(timeout);
      busy = false;
      updateButtons();
    }
  });

  element('save-generated').onclick = async () => {
    if (!generatedFile) return;
    if (!window.showSaveFilePicker) {
      showMessage('Для выбора папки сохранения откройте приложение в Edge или Chrome.');
      return;
    }
    try {
      const handle = await window.showSaveFilePicker({suggestedName: 'route.csv', types: [{description: 'Маршрут CSV', accept: {'text/csv': ['.csv']}}]});
      const stream = await handle.createWritable();
      await stream.write(generatedFile);
      await stream.close();
      showMessage(`Файл «${handle.name}» сохранён. Загрузите его через «Открыть маршрут».`);
    } catch (error) {
      showMessage(error.name === 'AbortError' ? 'Сохранение отменено. Файл можно сохранить повторно.' : 'Ошибка сохранения файла.');
    }
  };
})();
