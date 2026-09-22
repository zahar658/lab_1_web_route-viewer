(() => {
 const get=id=>document.getElementById(id),form=get('truck-form');
 const defaults=Object.fromEntries([...form.querySelectorAll('input[name]')].map(e=>[e.name,Number(e.value)]));
 defaults.gears=get('truck-gears').value.split(/\s+/).map(Number);
 let params={...defaults,gears:[...defaults.gears]},result=null,version=0,busy=false;
 const metrics={model_speed:'Скорость ТС (расчёт), км/ч',model_rate:'Расход топлива, л/ч',model_fuel:'Накопленный расход, л',model_power:'Мощность двигателя, кВт',model_available:'Доступная мощность, кВт',model_gear:'Передача'};
 for(const [key,label] of Object.entries(metrics)){const option=new Option(label,key);option.disabled=true;get('metric').add(option);}
 const say=text=>get('truck-status').textContent=text;
 function invalidate(text='Параметры изменились — выполните расчёт заново.'){
  version++;result=null;get('play').disabled=true;get('truck-export').disabled=true;get('truck-results').hidden=true;
  for(const p of points)for(const k of Object.keys(metrics))p[k]=null;
  if(get('metric').value.startsWith('model_'))get('metric').value='elevation_m';
  refreshMetrics();draw();say(text);pauseMotion();
 }
 function indexAt(distance){const ns=result.nodes;let lo=0,hi=ns.length-1;while(lo<hi){const m=(lo+hi+1)>>1;if(ns[m].distance<=distance)lo=m;else hi=m-1;}return Math.min(lo,ns.length-2);}
 function sample(distance){
  if(!result)return null;const ns=result.nodes,i=indexAt(distance),a=ns[i],b=ns[i+1];
  const f=Math.max(0,Math.min(1,(distance-a.distance)/(b.distance-a.distance)));
  const v=Math.sqrt(a.speed*a.speed+(b.speed*b.speed-a.speed*a.speed)*f);
  const ds=Math.hypot(b.distance-a.distance,b.height-a.height)*f;
  const dt=ds===0?0:2*ds/((a.speed+v)/3.6),tf=a.duration?dt/a.duration:0;
  const smooth=result.strategy==='terrain',rate=smooth?a.rate_start+(a.rate_end-a.rate_start)*tf:a.rate,spent=smooth?(a.rate_start*dt+.5*(a.rate_end-a.rate_start)*dt*tf)/3600:(b.fuel-a.fuel)*tf;
  return {model_speed:v,model_rate:distance>=ns.at(-1).distance?0:rate,model_fuel:a.fuel+spent,model_power:distance>=ns.at(-1).distance?0:smooth?a.power_start+(a.power_end-a.power_start)*tf:a.power,model_available:a.available,model_gear:distance>=ns.at(-1).distance?0:a.gear,time:a.time+dt};
 }
 function advance(distance,seconds){
  const ns=result.nodes,target=Math.min(result.time_s,sample(distance).time+seconds);
  let lo=0,hi=ns.length-1;while(lo<hi){const m=(lo+hi+1)>>1;if(ns[m].time<=target)lo=m;else hi=m-1;}
  if(lo>=ns.length-1)return ns.at(-1).distance;
  const a=ns[lo],b=ns[lo+1],dt=target-a.time,total=Math.hypot(b.distance-a.distance,b.height-a.height);
  const travelled=a.speed/3.6*dt+.5*a.accel*dt*dt;
  return a.distance+Math.max(0,Math.min(1,travelled/total))*(b.distance-a.distance);
 }
 function chartSeries(start,end){
  if(!result)return [];
  const low=points[start].distance,high=points[end].distance;
  const distances=[low,...result.nodes.filter(n=>n.distance>low&&n.distance<high).map(n=>n.distance),high];
  return [...new Set(distances)].map(d=>{const pos=positionAt(d);return {p:sample(d),index:pos.index+pos.t};});
 }
 window.TruckModel={invalidate,sample,chartSeries,snapshot:()=>result,active:()=>!!result,advance};
 get('truck-settings').onclick=()=>get('truck-dialog').showModal();get('truck-close').onclick=()=>get('truck-dialog').close();
 get('truck-defaults').onclick=()=>{for(const e of form.querySelectorAll('input[name]'))e.value=defaults[e.name];get('truck-gears').value=defaults.gears.join(' ');};
 form.onsubmit=event=>{event.preventDefault();const next=Object.fromEntries([...form.querySelectorAll('input[name]')].map(e=>[e.name,Number(e.value)]));next.gears=get('truck-gears').value.trim().split(/[\s;]+/).map(Number);
  if(!next.gears.length||next.gears.some((x,i)=>!Number.isFinite(x)||x<=0||(i&&x>=next.gears[i-1]))){get('truck-form-error').textContent='Передачи: положительные числа через пробел, строго по убыванию. Десятичный разделитель — точка.';return;}
  params=next;get('truck-form-error').textContent='';get('truck-dialog').close();invalidate();
 };
 for(const id of ['mass','cargo','truck-profile','truck-strategy'])get(id).addEventListener('change',()=>invalidate());
 function display(data,profile){
  const box=get('truck-results');box.replaceChildren();box.hidden=false;
  for(const text of [`Топливо: ${fmt(data.fuel_l)} л`, `Средний расход: ${fmt(data.litres_100km)} л/100 км`,`Время: ${fmt(data.time_s/3600)} ч / лимит ${fmt(data.budget_s/3600)} ч`,`Средняя скорость: ${fmt(data.average_kmh)} км/ч`,`Профиль: ${profile==='smooth'?'сглаженный':'исходный'}`,`Сетка: ${data.segments} участков, ${data.speed_states} скоростей`]){const div=document.createElement('div');div.textContent=text;box.append(div);}
  if(data.strategy==='terrain'){const extra=document.createElement('p');extra.textContent=`На спусках: ${fmt(data.downhill_fuel_l)} л за ${fmt(data.downhill_time_s)} с. Шагов с отсечкой: ${data.cutoff_steps}.`;box.append(extra);}
  if(data.optimized){const chosen=document.createElement('p');chosen.textContent=`Проверено вариантов: ${data.passes}. Выбрано: разгон за ${fmt(data.params.lookahead)} м, крейсерская ${fmt(data.params.cruise)} км/ч, мощность у вершины ${fmt(data.params.crest_power)}%.` ;box.append(chosen);}
  const compare=document.createElement('p');compare.className='note';compare.textContent=data.strategy==='terrain'?(data.optimized?(data.baseline?`Исходные настройки: ${fmt(data.baseline.fuel_l)} л. Экономия: ${fmt(data.baseline.fuel_l-data.fuel_l)} л. Лучший из проверенных вариантов.`:'Лучший из проверенных вариантов. Исходные ручные настройки не прошли ограничения.'):'Ручная стратегия, без подбора по расходу.'):data.baseline?`Постоянная скорость при тех же условиях: ${fmt(data.baseline.fuel_l)} л.`:'Сравнение с постоянной скоростью доступно, когда начальная, конечная и заданная средняя скорости совпадают, а проезд возможен.';box.append(compare);
 }
 get('truck-calculate').onclick=async()=>{
  if(busy)return;if(!points.length){say('Сначала откройте CSV маршрута.');return;}
  const profile=get('truck-profile').value,key=profile==='smooth'?'elevation_smoothed_m':'elevation_m';
  if(points.some(p=>!Number.isFinite(p[key]))){say('В выбранном профиле есть пропуски высот. Выберите другой профиль или создайте CSV со сглаживанием.');return;}
  invalidate('Расчёт… На длинном маршруте это может занять несколько минут.');const token=version,route=points;
  const input={...params,mass:Number(get('mass').value),cargo:Number(get('cargo').value)};
  busy=true;get('truck-calculate').disabled=true;
  try{
   const response=await fetch('/api/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({strategy:get('truck-strategy').value,params:input,points:route.map(p=>[p.distance,p[key]])})});
   let data;try{data=await response.json();}catch{throw Error('Сервер не вернул результат. Перезапустите обновлённый START.bat.');}
   if(token!==version||route!==points)return;
   if(!response.ok)throw Error(data.error||'Ошибка расчёта.');
   if(!data.feasible){say(data.message+(data.fastest_average?` Максимальная средняя на сетке: ${fmt(data.fastest_average)} км/ч.`:''));return;}
   result=data;result.profile=profile;
   for(const p of points)Object.assign(p,sample(p.distance));
   get('play').disabled=false;get('truck-export').disabled=false;
   refreshMetrics();get('metric').value='model_speed';get('axis').value='distance';get('axis').onchange();travel=0;paintVehicle();
   display(data,profile);say(data.strategy==='terrain'?`Стратегия рельефа рассчитана; ограничение времени соблюдено. На каждом подъёме мощность не возрастает; скорость на вершине определяется расчётом. Выбран допустимый профиль; подбор не гарантирует глобальный минимум топлива.`:'Допустимый профиль найден. Ограничение средней скорости соблюдено. Это приближённый поиск, не гарантия глобального минимума.');
  }catch(error){if(token===version)say(error instanceof TypeError?'Нет связи с локальным сервером. Проверьте START.bat.':error.message);}
  finally{busy=false;get('truck-calculate').disabled=false;}
 };
 get('truck-export').onclick=async()=>{
  if(!result)return;const keys=Object.keys(result.nodes[0]),config=JSON.stringify({params:result.params,profile:result.profile,strategy:result.strategy||'economy',method:result.method});
  const quote=v=>'"'+String(v).replaceAll('"','""')+'"';
  const text='\uFEFF'+[keys.join(',')+',configuration',...result.nodes.map((n,i)=>keys.map(k=>n[k]).join(',')+','+(i===0?quote(config):''))].join('\r\n');
  try{if(!window.showSaveFilePicker){say('Для выбора папки сохранения откройте приложение в Edge или Chrome.');return;}const handle=await showSaveFilePicker({suggestedName:'truck_calculation.csv',types:[{description:'Расчёт грузовика',accept:{'text/csv':['.csv']}}]});const stream=await handle.createWritable();await stream.write(text);await stream.close();say('Расчёт сохранён.');}catch(e){say(e.name==='AbortError'?'Сохранение отменено.':'Не удалось сохранить расчёт.');}
 };
})();
