(() => {
 const get=id=>document.getElementById(id),dialog=get('route-dialog');
 const resolved={start:null,end:null},versions={start:0,end:0};let busy=false,generated=null;
 const message=text=>{get('generator-status').textContent=text;};
 function clearOutput(){generated=null;get('save-generated').disabled=true;}
 function update(){get('generate-route').disabled=busy||!resolved.start||!resolved.end;}
 function invalidate(side){versions[side]++;resolved[side]=null;get(`${side}-choice`).hidden=true;get(`${side}-note`).textContent='';get(`${side}-query`).removeAttribute('aria-invalid');clearOutput();update();}
 async function post(path,body){
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),200000);
  try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
   if(!response.ok){let text='Не удалось выполнить запрос. Перезапустите приложение через START.bat.';try{text=(await response.json()).error||text;}catch{}throw Error(text);}
   return path.endsWith('/generate')?await response.blob():await response.json();
  }catch(error){if(error.name==='AbortError')throw Error('Время ожидания истекло. Повторите запрос позже.');if(error instanceof TypeError)throw Error('Нет связи с локальным сервером. Проверьте окно START.bat.');throw error;}finally{clearTimeout(timeout);}
 }
 get('new-route').onclick=()=>{pauseMotion();dialog.showModal();};
 function close(){if(busy){message('Дождитесь завершения генерации перед закрытием.');return;}dialog.close();}
 get('close-generator').onclick=close;
 dialog.addEventListener('cancel',event=>{if(busy){event.preventDefault();message('Дождитесь завершения генерации.');}});
 dialog.addEventListener('close',()=>{get('api-key').value='';for(const side of ['start','end']){versions[side]++;resolved[side]=null;get(`${side}-choice`).hidden=true;get(`${side}-note`).textContent='';}update();});
 get('smooth-window').addEventListener('input',()=>{clearOutput();message('');});
 get('api-key').addEventListener('input',()=>{invalidate('start');invalidate('end');message('');});
 for(const side of ['start','end']){
  get(`${side}-query`).addEventListener('input',()=>{invalidate(side);message('');});
  get(`check-${side}`).onclick=async()=>{
   const key=get('api-key').value.trim(),query=get(`${side}-query`).value.trim();
   if(!key){message('Введите API-ключ.');get('api-key').focus();return;}
   if(query.length<2){get(`${side}-query`).setAttribute('aria-invalid','true');get(`${side}-note`).textContent='Введите точку маршрута.';return;}
   invalidate(side);const version=versions[side];get(`check-${side}`).disabled=true;get(`${side}-note`).textContent='Проверка…';
   try{const result=await post('/api/resolve',{key,query});if(version!==versions[side])return;
    const select=get(`${side}-choice`);select.replaceChildren();select.add(new Option('Выберите найденное место…',''));
    result.candidates.forEach((item,i)=>select.add(new Option(`${item.label} (${item.coordinates[1].toFixed(5)}, ${item.coordinates[0].toFixed(5)})`,String(i))));
    select.hidden=false;get(`${side}-note`).textContent=result.note;
    select.onchange=()=>{resolved[side]=select.value===''?null:result.candidates[Number(select.value)].coordinates;clearOutput();message('');update();};
    if(result.candidates.length===1){select.value='0';select.onchange();}
   }catch(error){if(version===versions[side]){get(`${side}-query`).setAttribute('aria-invalid','true');get(`${side}-note`).textContent=error.message;}}
   finally{get(`check-${side}`).disabled=false;update();}
  };
 }
 function lock(value){busy=value;for(const id of ['api-key','start-query','end-query','start-choice','end-choice','check-start','check-end','smooth-window'])get(id).disabled=value;update();}
 get('route-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!resolved.start||!resolved.end)return;
  if(!window.showSaveFilePicker){message('Для выбора папки сохранения откройте этот адрес в Microsoft Edge или Google Chrome.');return;}
  const [a,b]=[resolved.start,resolved.end];
  if(RouteData.distance({lat:a[1],lon:a[0]},{lat:b[1],lon:b[0]})<1){message('Начальная и конечная точки должны различаться минимум на 1 метр.');return;}
  clearOutput();lock(true);message('Получаем маршрут с высотами и сохраняем исходные точки… Это может занять до трёх минут.');
  try{generated=await post('/api/generate',{key:get('api-key').value.trim(),start:a,end:b,smooth_window:Number(get('smooth-window').value)});get('save-generated').disabled=false;message('CSV готов. Выберите, куда его сохранить.');}
  catch(error){message(error.message);}finally{lock(false);}
 });
 get('save-generated').onclick=async()=>{
  if(!generated)return;const blob=generated;get('save-generated').disabled=true;let stream;
  try{const handle=await window.showSaveFilePicker({suggestedName:`route_${new Date().toISOString().slice(0,10)}.csv`,types:[{description:'Маршрут CSV',accept:{'text/csv':['.csv']}}]});stream=await handle.createWritable();await stream.write(blob);await stream.close();stream=null;message(`Файл «${handle.name}» сохранён. Откройте его через «Открыть маршрут».`);}
  catch(error){if(stream)try{await stream.abort();}catch{}message(error.name==='AbortError'?'Сохранение отменено. CSV остаётся доступным для сохранения.':'Не удалось сохранить файл. Выберите другую папку и повторите.');}
  finally{get('save-generated').disabled=!generated;}
 };
})();
