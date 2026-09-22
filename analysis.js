'use strict';
const $=id=>document.getElementById(id),fmt=(v,d=2)=>Number.isFinite(v)?v.toLocaleString('ru-RU',{maximumFractionDigits:d}):'нет данных';
let state=null,lastPoints=null,lastModel=null,lo=0,hi=1,cursor=null;let draggedPanel=null;
const configs=[
 ['Высота, м','raw',['elevation_m','elevation_smoothed_m']],
 ['Уклон, °','raw',['slope_deg','slope_smoothed_deg']],
 ['Уклон, %','raw',['slope_pct','slope_smoothed_pct']],
 ['Перепад высоты, м','raw',['elevation_delta_m','elevation_delta_smoothed_m']],
 ['Скорость ТС (расчёт), км/ч','model',['speed']],
 ['Расход топлива, л/ч','model',['rate']],
 ['Накопленный расход, л','model',['fuel']],
 ['Мощность двигателя, кВт','model',['power','available']],
 ['Передача','model',['gear']]
];
const panels=configs.map(([title,source,keys])=>{
 const section=document.createElement('section');section.className='panel';
 const heading=document.createElement('h2');heading.textContent=title;const bar=document.createElement('div');bar.className='panel-heading';heading.draggable=true;heading.title='Перетащите для изменения порядка';bar.append(heading);const up=document.createElement('button'),down=document.createElement('button');up.textContent='↑';down.textContent='↓';up.setAttribute('aria-label','Поднять график: '+title);down.setAttribute('aria-label','Опустить график: '+title);bar.append(up,down);section.append(bar);
 if(keys[0]==='power'){const note=document.createElement('p');note.className='units';note.textContent='Бирюзовый — средняя требуемая; фиолетовый — минимальная доступная на участке';section.append(note);}
 const plot=document.createElement('div');plot.className='plot';const canvas=document.createElement('canvas'),overlay=document.createElement('canvas');overlay.className='overlay';overlay.setAttribute('aria-hidden','true');canvas.setAttribute('aria-label',title);const empty=document.createElement('div');empty.className='empty';plot.append(canvas,overlay,empty);section.append(plot);const readout=document.createElement('div');readout.className='readout';section.append(readout);$('charts').append(section);
 const p={source,keys,canvas,overlay,empty,readout,section,up,down};
 const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=true;label.append(check,document.createTextNode(title));$('chart-choices').append(label);p.check=check;
 check.addEventListener('change',()=>{section.hidden=!check.checked;updateOrder();render();});
 up.onclick=()=>moveVisible(p,-1);down.onclick=()=>moveVisible(p,1);
 heading.addEventListener('dragstart',e=>{draggedPanel=p;e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',title);section.classList.add('dragging');});
 heading.addEventListener('dragend',()=>{draggedPanel=null;section.classList.remove('dragging');});
 section.addEventListener('dragover',e=>{if(draggedPanel&&draggedPanel!==p){e.preventDefault();e.dataTransfer.dropEffect='move';}});
 section.addEventListener('drop',e=>{e.preventDefault();if(!draggedPanel||draggedPanel===p)return;const moved=draggedPanel;const after=e.clientY>section.getBoundingClientRect().top+section.getBoundingClientRect().height/2;panels.splice(panels.indexOf(moved),1);panels.splice(panels.indexOf(p)+(after?1:0),0,moved);moved.section.classList.remove('dragging');draggedPanel=null;updateOrder();render();});
 canvas.addEventListener('pointermove',e=>{cursor=atMouse(p,e);drawOverlays();});canvas.addEventListener('pointerleave',()=>{cursor=null;drawOverlays();});
 canvas.addEventListener('click',e=>{if(!state)return;try{const ok=window.opener?.RouteAnalysis?.seek(atMouse(p,e));$('notice').textContent=ok?'Положение ТС изменено.':'Для перемещения поставьте движение на паузу в основном окне.';}catch{$('notice').textContent='Основное окно недоступно.';}});
 canvas.addEventListener('wheel',e=>{if(!state)return;e.preventDefault();const center=atMouse(p,e),factor=e.deltaY>0?1.25:.8,total=state.points.at(-1).distance;const width=Math.max(Math.min(1,total),Math.min(total,(hi-lo)*factor));const fraction=(center-lo)/(hi-lo);lo=Math.max(0,Math.min(total-width,center-width*fraction));hi=lo+width;syncInputs();render();},{passive:false});return p;
});
function updateOrder(){
 const visible=panels.filter(p=>!p.section.hidden);
 for(const p of panels){$('charts').append(p.section);const i=visible.indexOf(p);p.up.disabled=i<=0;p.down.disabled=i<0||i===visible.length-1;}
}
function moveVisible(p,direction){const visible=panels.filter(x=>!x.section.hidden),target=visible[visible.indexOf(p)+direction];if(!target)return;const a=panels.indexOf(p),b=panels.indexOf(target);[panels[a],panels[b]]=[panels[b],panels[a]];updateOrder();render();}
updateOrder();
function atMouse(p,e){const r=p.canvas.getBoundingClientRect();return lo+Math.max(0,Math.min(1,(e.clientX-r.left-68)/(r.width-86)))*(hi-lo);}
function rows(p){return p.source==='model'?(state?.model?.nodes||[]):(state?.points||[]);}
function valueAt(data,d,key,model){if(!data.length)return null;let a=0,b=data.length-1;while(a<b){const m=(a+b+1)>>1;if(data[m].distance<=d)a=m;else b=m-1;}const x=data[a],y=data[Math.min(a+1,data.length-1)];const span=y.distance-x.distance,f=span?Math.max(0,Math.min(1,(d-x.distance)/span)):0;
 if(!Number.isFinite(x[key]))return null;if(f===0)return model&&state?.model?.strategy==='terrain'&&['rate','power'].includes(key)?x[key+'_start']:x[key];if(!Number.isFinite(y[key]))return null;
 if(model&&state?.model?.strategy==='terrain'&&['rate','power','fuel'].includes(key)){const v=Math.sqrt(x.speed*x.speed+(y.speed*y.speed-x.speed*x.speed)*f),dt=2*Math.hypot(span,y.height-x.height)*f/((x.speed+v)/3.6),tf=x.duration?dt/x.duration:0;if(key==='fuel')return x.fuel+(x.rate_start*dt+.5*(x.rate_end-x.rate_start)*dt*tf)/3600;return x[key+'_start']+(x[key+'_end']-x[key+'_start'])*tf;}
 if(model&&['rate','power','available','gear'].includes(key))return x[key];
 if(model&&key==='speed')return Math.sqrt(x.speed*x.speed+(y.speed*y.speed-x.speed*x.speed)*f);
 if(model&&key==='fuel'){const v=Math.sqrt(x.speed*x.speed+(y.speed*y.speed-x.speed*x.speed)*f),dt=2*Math.hypot(span,y.height-x.height)*f/((x.speed+v)/3.6);return x.fuel+(y.fuel-x.fuel)*(x.duration?dt/x.duration:0);}
 return x[key]+(y[key]-x[key])*f;}
function resize(canvas){const r=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;canvas.width=r.width*dpr;canvas.height=r.height*dpr;const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);return [c,r.width,r.height];}
function render(){for(const p of panels){if(p.section.hidden)continue;p.xy=null;const [c,w,h]=resize(p.canvas);resize(p.overlay);const data=rows(p);p.data=data;const inside=data.filter(r=>r.distance>lo&&r.distance<hi);const ds=[lo,...inside.map(r=>r.distance),hi];const curves=p.keys.map(key=>ds.map(d=>[d,valueAt(data,d,key,p.source==='model')]));const values=curves.flat().map(a=>a[1]).filter(Number.isFinite);p.empty.hidden=!!values.length;p.empty.textContent=p.source==='model'?'Сначала рассчитайте скорость в основном окне.':'Нет данных в выбранном участке.';
 if(!values.length)continue;let min=Infinity,max=-Infinity;for(const v of values){min=Math.min(min,v);max=Math.max(max,v);}const pad=(max-min)*.08||1;min-=pad;max+=pad;const top=12,bottom=h-30,left=68,right=w-18,x=d=>left+(d-lo)/(hi-lo)*(right-left),y=v=>bottom-(v-min)/(max-min)*(bottom-top);p.xy={x,y,top,bottom,left,right};c.font='12px system-ui';c.fillStyle='#647d8d';
 for(let i=0;i<=4;i++){const v=min+(max-min)*i/4,yy=y(v);c.strokeStyle='#e6edf2';c.beginPath();c.moveTo(left,yy);c.lineTo(right,yy);c.stroke();c.textAlign='right';c.fillText(fmt(v,1),left-8,yy+4);}
 for(let i=0;i<=5;i++){c.textAlign='center';c.fillText(fmt((lo+(hi-lo)*i/5)/1000),left+(right-left)*i/5,h-8);}
 curves.forEach((curve,j)=>{c.strokeStyle=j?'#8660ae':'#087f83';c.lineWidth=1.8;c.beginPath();let active=false,prev=null;for(const [d,v] of curve){if(!Number.isFinite(v)){active=false;prev=null;continue;}if(!active)c.moveTo(x(d),y(v));else {if(p.source==='model'&&(state?.model?.strategy==='terrain'?['available','gear']:['rate','power','available','gear']).includes(p.keys[j]))c.lineTo(x(d),y(prev));c.lineTo(x(d),y(v));}active=true;prev=v;}c.stroke();});}drawOverlays();}
function drawOverlays(){for(const p of panels){if(p.section.hidden)continue;const [c,w,h]=resize(p.overlay);if(!p.xy||!state)continue;const {x,top,bottom}=p.xy;for(const [d,color] of [[state.travel,'#e77c21'],[cursor,'#496879']]){if(d===null||d<lo||d>hi)continue;c.strokeStyle=color;c.setLineDash([4,4]);c.beginPath();c.moveTo(x(d),top);c.lineTo(x(d),bottom);c.stroke();}const d=cursor??state.travel;p.readout.textContent=`${fmt(d/1000)} км · `+p.keys.map((key,i)=>`${p.keys.length>1?(p.source==='raw'?(i?'Сглаженные: ':'Исходные: '):(i?'Доступная: ':'Требуемая: ')):''}${fmt(valueAt(p.data||[],d,key,p.source==='model'))}`).join(' · ');}}
function syncInputs(){$('from').value=(lo/1000).toFixed(4);$('to').value=(hi/1000).toFixed(4);}
$('apply').onclick=()=>{if(!state)return;const a=Number($('from').value)*1000,b=Number($('to').value)*1000;if($('from').value===''||$('to').value===''||!Number.isFinite(a)||!Number.isFinite(b)||a<0||b<=a||b>state.points.at(-1).distance+.1){$('notice').textContent='Укажите возрастающий диапазон внутри маршрута.';return;}lo=a;hi=b;render();};
$('full').onclick=()=>{if(!state)return;lo=0;hi=state.points.at(-1).distance||1;syncInputs();render();};
$('back').onclick=()=>{try{if(window.opener&&!window.opener.closed){window.opener.focus();return;}}catch{}location.href='index.html';};
function poll(){try{if(!window.opener||window.opener.closed){if(state)$('notice').textContent='Основное окно закрыто. Показан последний полученный расчёт.';return;}const next=window.opener.RouteAnalysis?.snapshot();if(!next?.points.length)return;state=next;$('route-title').textContent=state.title;if(lastPoints!==state.points||lastModel!==state.model){const changed=lastPoints!==state.points;lastPoints=state.points;lastModel=state.model;if(changed){lo=0;hi=state.points.at(-1).distance||1;syncInputs();}$('notice').textContent=state.model?`Расчёт по ${state.model.profile==='smooth'?'сглаженному':'исходному'} рельефу. Горизонтальная ось всех графиков — расстояние от старта, км.`:'Маршрут загружен. Графики скорости и топлива появятся после расчёта.';render();}else drawOverlays();}catch{$('notice').textContent='Откройте страницу из основного приложения кнопкой «Все графики».';}}
new ResizeObserver(()=>render()).observe($('charts'));setInterval(poll,250);poll();
