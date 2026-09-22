'use strict';
const $=id=>document.getElementById(id),fmt=(n,d=2)=>n==null?'нет данных':n.toLocaleString('ru-RU',{maximumFractionDigits:d});let points=[],line,marker,endpoints=[],selected=-1,geometry=null,loadId=0,viewStart=0,viewEnd=-1;
const map=window.L?L.map('map',{preferCanvas:true}).setView([46,134],5):null;
if(map){const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}).addTo(map);tiles.on('tileerror',()=>{$('map-warning').hidden=false;});tiles.on('tileload',()=>{$('map-warning').hidden=true;});L.control.scale({imperial:false}).addTo(map);}else{$('map-warning').hidden=false;$('map-warning').textContent='Не удалось загрузить библиотеку карты. Проверь папку vendor.';}
const canvas=$('chart'),ctx=canvas.getContext('2d');
function status(message){$('status').textContent=message;$('status').hidden=!message;}
function fit(){if(line)map.fitBounds(line.getBounds(),{padding:[35,35],maxZoom:16});}
function updateRange(){
viewStart=0;viewEnd=points.length-1;
if(map&&points.length){const range=RouteData.visibleRange(points,map.getBounds());viewStart=range[0];viewEnd=range[1];}
if(selected<viewStart||selected>viewEnd||viewEnd<0){selected=-1;$('tooltip').hidden=true;if(marker&&map){map.removeLayer(marker);marker=null;}}
$('selection').textContent=viewEnd<0?'В видимой области карты нет точек маршрута':`На карте: точки ${points[viewStart]?.id} — ${points[viewEnd]?.id} · наведи на график`;
draw();
}
if(map)map.on('moveend',updateRange);
function draw(){const rect=canvas.getBoundingClientRect(),w=rect.width,h=rect.height,dpr=devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);geometry=null;clearVehicleChart();if(!points.length)return;if(viewEnd<0){$('empty').hidden=false;$('empty').textContent='В видимой области карты нет точек маршрута';$('tooltip').hidden=true;return;}const key=metricKey(),series=key.startsWith('model_')&&window.TruckModel?window.TruckModel.chartSeries(viewStart,viewEnd):points.slice(viewStart,viewEnd+1).map((p,i)=>({p,index:viewStart+i})),values=series.map(item=>item.p[key]).filter(v=>Number.isFinite(v));$('empty').hidden=!!values.length;if(!values.length){$('empty').textContent='В этом участке нет данных для выбранного показателя';return;}
let min=Infinity,max=-Infinity;for(const v of values){min=Math.min(min,v);max=Math.max(max,v);}if(/slope|delta/.test(key)){min=Math.min(0,min);max=Math.max(0,max);}const pad=(max-min)*.09||1;min-=pad;max+=pad;const left=65,right=w-18,top=12,bottom=h-30,byDistance=$('axis').value==='distance';const xvalue=i=>byDistance?(points[Math.floor(i)].distance+(points[Math.min(Math.floor(i)+1,points.length-1)].distance-points[Math.floor(i)].distance)*(i-Math.floor(i)))/1000:i;const xmin=xvalue(viewStart),xmax=xvalue(viewEnd),span=xmax-xmin;const x=i=>span?left+(xvalue(i)-xmin)/span*(right-left):(left+right)/2,y=v=>bottom-(v-min)/(max-min)*(bottom-top);geometry={left,right,xmin,xmax,byDistance,x,y,top,bottom};ctx.font='12px system-ui';ctx.lineWidth=1;
for(let j=0;j<=4;j++){const v=min+(max-min)*j/4,yy=y(v);ctx.strokeStyle='#e5ecf1';ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(right,yy);ctx.stroke();ctx.fillStyle='#6a8090';ctx.textAlign='right';ctx.fillText(fmt(v,1),left-9,yy+4);}
for(let j=0;j<=(span?5:0);j++){ctx.textAlign='center';ctx.fillText(fmt(xmin+span*j/5,byDistance?2:0),span?left+(right-left)*j/5:(left+right)/2,h-8);}if(min<0&&max>0){ctx.strokeStyle='#a9bcc8';ctx.beginPath();ctx.moveTo(left,y(0));ctx.lineTo(right,y(0));ctx.stroke();}
ctx.save();ctx.beginPath();ctx.rect(left,top,right-left,bottom-top);ctx.clip();ctx.strokeStyle='#087f83';ctx.lineWidth=1.6;ctx.beginPath();let active=false;series.forEach(({p,index:i})=>{if(!Number.isFinite(p[key])){active=false;return;}if(active)ctx.lineTo(x(i),y(p[key]));else ctx.moveTo(x(i),y(p[key]));active=true;});ctx.stroke();if(viewStart===viewEnd&&points[viewStart][key]!==null){ctx.fillStyle='#087f83';ctx.beginPath();ctx.arc(x(viewStart),y(points[viewStart][key]),4,0,Math.PI*2);ctx.fill();}if(selected>=viewStart&&selected<=viewEnd){const p=points[selected],xx=x(selected);ctx.strokeStyle='#294c63';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(xx,top);ctx.lineTo(xx,bottom);ctx.stroke();ctx.setLineDash([]);if(p[key]!==null){ctx.fillStyle='#087f83';ctx.beginPath();ctx.arc(xx,y(p[key]),4,0,Math.PI*2);ctx.fill();}}ctx.restore();drawVehicleChart();}
function select(i){if(!points.length||viewEnd<0)return;selected=Math.max(viewStart,Math.min(viewEnd,i));const p=points[selected];if(map){if(!marker)marker=L.circleMarker([p.lat,p.lon],{radius:7,color:'#fff',weight:3,fillColor:'#0a7b80',fillOpacity:1}).addTo(map);else marker.setLatLng([p.lat,p.lon]);}const label=$('metric').selectedOptions[0].textContent;$('tooltip').hidden=false;$('tooltip').textContent=`Точка ${p.id} · ${label}: ${fmt(p[metricKey()])}`;$('selection').textContent=`Точка ${p.id} · ${fmt(p.distance/1000)} км · ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`;draw();}
function load(text,name){const next=RouteData.parse(text);pauseMotion();points=next;travel=0;viewStart=0;viewEnd=points.length-1;selected=-1;$('tooltip').hidden=true;status('');if(map){if(line)map.removeLayer(line);if(marker){map.removeLayer(marker);marker=null;}endpoints.forEach(m=>map.removeLayer(m));line=L.polyline(points.map(p=>[p.lat,p.lon]),{color:'#078c91',weight:4,opacity:.95}).addTo(map);endpoints=[0,points.length-1].map((i,j)=>L.circleMarker([points[i].lat,points[i].lon],{radius:6,color:'#fff',weight:2,fillColor:j?'#112d40':'#079883',fillOpacity:1}).addTo(map).bindTooltip(j?'Финиш':'Старт'));fit();$('fit').disabled=false;}
$('summary').textContent=`${name} · ${fmt(points.length,0)} точек · ${fmt(points.at(-1).distance/1000)} км`;$('selection').textContent='Наведи на график — точка появится на карте';$('profile-mode').value='raw';refreshMetrics();updateRange();resetMotion();if(window.TruckModel)window.TruckModel.invalidate('Маршрут загружен. Выберите профиль рельефа и нажмите «Рассчитать скорость».');}
$('file').addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;const token=++loadId;try{if(file.size>30*1024*1024)throw Error('Максимальный размер файла — 30 МБ.');status('Загрузка…');const text=await file.text();if(token===loadId)load(text,file.name);}catch(err){if(token===loadId)status(err.message);}finally{e.target.value='';}});
$('metric').onchange=()=>{draw();if(selected>=0)select(selected);};$('axis').onchange=()=>{$('axislabel').textContent=$('axis').selectedOptions[0].textContent;draw();};$('fit').onclick=fit;
canvas.addEventListener('pointermove',e=>{if(!geometry)return;const {left,right,xmin,xmax,byDistance}=geometry,target=xmin+Math.max(0,Math.min(1,(e.clientX-canvas.getBoundingClientRect().left-left)/(right-left)))*(xmax-xmin);if(!byDistance)select(Math.round(target));else{let lo=viewStart,hi=viewEnd;while(lo<hi){const mid=(lo+hi)>>1;if(points[mid].distance/1000<target)lo=mid+1;else hi=mid;}if(lo>viewStart&&Math.abs(points[lo-1].distance/1000-target)<Math.abs(points[lo].distance/1000-target))lo--;select(lo);}});
canvas.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();select(selected<0?viewStart:selected+(e.key==='ArrowRight'?1:-1));}});
new ResizeObserver(()=>{draw();if(map)map.invalidateSize();}).observe(document.querySelector('main'));draw();

// Vehicle position is independent of the chart hover marker.
let travel=0,vehicle=null,running=false,frame=0,lastTime=null,lastFollow=0;
function parameters(){
 const inputs=['cargo','mass'];
 const invalid=inputs.find(id=>$(id).value.trim()===''||!$(id).checkValidity()||!Number.isFinite(Number($(id).value)));
 $('transport-error').hidden=!invalid;
 $('transport-error').textContent=invalid?'Проверь параметры: масса ТС 1–1 000 000 кг, груз 0–1 000 000 кг.':'';
 $('total-mass').textContent=invalid?'—':`${fmt(Number($('cargo').value)+Number($('mass').value),0)} кг`;
 return invalid?null:{scale:Number($('time-scale').value)};
}
function positionAt(distance){
 const last=points.length-1;
 if(distance>=points[last].distance)return {lat:points[last].lat,lon:points[last].lon,index:last,t:0};
 let low=0,high=last;
 while(low<high){const mid=(low+high)>>1;if(points[mid].distance<=distance)low=mid+1;else high=mid;}
 const b=points[low],a=points[Math.max(0,low-1)],length=b.distance-a.distance;
 const t=length>0?Math.max(0,Math.min(1,(distance-a.distance)/length)):0;
 const longitudeDelta=((b.lon-a.lon+540)%360)-180;
 return {index:Math.max(0,low-1),t,lat:a.lat+(b.lat-a.lat)*t,lon:((a.lon+longitudeDelta*t+540)%360)-180};
}
function paintVehicle(center=false){
 if(!points.length)return;
 const p=positionAt(travel),total=points.at(-1).distance;
 if(map){
  if(!vehicle){vehicle=L.circleMarker([p.lat,p.lon],{radius:9,color:'#fff',weight:3,fillColor:'#e77c21',fillOpacity:1}).addTo(map).bindTooltip('ТС · на паузе можно перетащить');
  if(vehicle&&!vehicle._routeSeekBound&&window.RouteControls){window.RouteControls.bind(vehicle);vehicle._routeSeekBound=true;}}
  else vehicle.setLatLng([p.lat,p.lon]);
  vehicle.bringToFront();
  if(center)map.panTo([p.lat,p.lon],{animate:false});
 }
 $('trip-progress').value=total>0?travel/total*100:0;
 $('trip-distance').textContent=`${fmt(travel/1000)} / ${fmt(total/1000)} км`;
 drawVehicleChart();
 if(window.RouteControls)window.RouteControls.sync();
}
function pauseMotion(){running=false;cancelAnimationFrame(frame);lastTime=null;$('play').textContent='Запуск';if(window.RouteControls)window.RouteControls.sync();if(points.length)$('play-state').textContent='Пауза';}
function resetMotion(){
 if(vehicle&&map)map.removeLayer(vehicle);vehicle=null;travel=0;
 for(const id of ['rewind','finish'])$(id).disabled=!points.length;
 $('play').disabled=!window.TruckModel?.active();
 $('play-state').textContent='Готов к движению';paintVehicle();
}
function tick(timestamp){
 if(!running)return;
 if(!window.TruckModel?.active()){pauseMotion();return;}
 const config=parameters();if(!config){pauseMotion();return;}
 const seconds=lastTime===null?0:Math.max(0,(timestamp-lastTime)/1000);lastTime=timestamp;
 travel=window.TruckModel.advance(travel,seconds*config.scale);
 const follow=$('follow').checked&&timestamp-lastFollow>=250;
 paintVehicle(follow);if(follow)lastFollow=timestamp;
 if(travel>=points.at(-1).distance){pauseMotion();$('play-state').textContent='Финиш';return;}
 $('play-state').textContent=`По расчёту · ${fmt(window.TruckModel.sample(travel).model_speed,1)} км/ч`;
 frame=requestAnimationFrame(tick);
}
$('play').onclick=()=>{
 if(running){pauseMotion();return;}
 if(!points.length||!parameters()||!window.TruckModel?.active())return;
 if(points.at(-1).distance<=0){$('play-state').textContent='Нет протяжённости для движения';return;}
 if(travel>=points.at(-1).distance)travel=0;
 running=true;lastTime=null;lastFollow=0;$('play').textContent='Пауза';$('play-state').textContent='В движении';paintVehicle($('follow').checked);frame=requestAnimationFrame(tick);
};
$('rewind').onclick=()=>{if(!points.length)return;pauseMotion();travel=0;paintVehicle(true);$('play-state').textContent='Начало маршрута';};
$('finish').onclick=()=>{if(!points.length)return;pauseMotion();travel=points.at(-1).distance;paintVehicle(true);$('play-state').textContent='Финиш';};
for(const id of ['cargo','mass','time-scale'])$(id).addEventListener('input',()=>{if(!parameters())pauseMotion();lastTime=null;});
$('follow').addEventListener('change',()=>{if($('follow').checked)paintVehicle(true);});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&running)pauseMotion();});
parameters();

function clearVehicleChart(){
 const overlay=$('vehicle-chart');
 if(overlay.width!==canvas.width)overlay.width=canvas.width;
 if(overlay.height!==canvas.height)overlay.height=canvas.height;
 const c=overlay.getContext('2d');c.setTransform(1,0,0,1,0,0);c.clearRect(0,0,overlay.width,overlay.height);
}
function drawVehicleChart(){
 clearVehicleChart();
 if(!points.length||!geometry||viewEnd<0)return;
 const {index,t}=positionAt(travel),position=index+t;
 if(position<viewStart||position>viewEnd)return;
 const key=metricKey(),a=points[index][key],b=points[Math.min(index+1,points.length-1)][key];
 const value=key.startsWith('model_')&&window.TruckModel?window.TruckModel.sample(travel)?.[key]??null:t===0?a:t===1?b:(a===null||b===null?null:a+(b-a)*t);
 const {left,right,xmin,xmax,byDistance,x,y,top,bottom}=geometry;
 const xx=byDistance?(xmax===xmin?(left+right)/2:left+(travel/1000-xmin)/(xmax-xmin)*(right-left)):x(position);
 const c=$('vehicle-chart').getContext('2d'),dpr=devicePixelRatio||1;
 c.setTransform(dpr,0,0,dpr,0,0);c.save();c.beginPath();c.rect(left-7,top-7,right-left+14,bottom-top+14);c.clip();
 c.strokeStyle='#e77c21';c.lineWidth=1.5;c.setLineDash([4,4]);c.beginPath();c.moveTo(xx,top);c.lineTo(xx,bottom);c.stroke();c.setLineDash([]);
 if(value!==null){c.beginPath();c.arc(xx,y(value),6,0,Math.PI*2);c.fillStyle='#e77c21';c.fill();c.strokeStyle='#fff';c.lineWidth=2;c.stroke();}
 c.restore();
}

function metricKey(value=$('metric').value){
 if($('profile-mode').value!=='smooth')return value;
 return {elevation_m:'elevation_smoothed_m',slope_pct:'slope_smoothed_pct',slope_deg:'slope_smoothed_deg',elevation_delta_m:'elevation_delta_smoothed_m'}[value]??value;
}
function refreshMetrics(){
 const available=points.some(p=>p.elevation_smoothed_m!==null||p.slope_smoothed_pct!==null||p.slope_smoothed_deg!==null);
 $('profile-mode').options[1].disabled=!available;
 if(!available)$('profile-mode').value='raw';
 for(const option of $('metric').options)option.disabled=!points.some(p=>Number.isFinite(p[metricKey(option.value)]));
 if($('metric').selectedOptions[0].disabled){const next=[...$('metric').options].find(o=>!o.disabled);if(next)$('metric').value=next.value;}
 $('metric').disabled=[...$('metric').options].every(o=>o.disabled);
 const window=points.find(p=>p.smoothing_window_m!==null)?.smoothing_window_m;
 $('profile-note').textContent=!available?'В этом CSV нет сглаженных данных. Для сравнения создайте маршрут в новой версии.':$('profile-mode').value==='smooth'?`Сглаженные данные${window!=null?' · окно '+fmt(window,0)+' м':''}. Исходные значения сохранены в CSV.`:'Исходные данные API · без сглаживания';
}
$('profile-mode').onchange=()=>{refreshMetrics();draw();if(selected>=0)select(selected);};
