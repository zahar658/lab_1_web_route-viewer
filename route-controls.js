(() => {
 const slider=document.getElementById('route-seek');
 function sync(){slider.disabled=running||!points.length;slider.max=points.length?points.at(-1).distance:1;slider.value=travel;}
 function seek(distance){if(running||!points.length||!Number.isFinite(distance))return false;travel=Math.max(0,Math.min(points.at(-1).distance,distance));lastTime=null;paintVehicle();document.getElementById('play-state').textContent='Пауза · позиция выбрана';sync();return true;}
 slider.addEventListener('input',()=>seek(Number(slider.value)));
 canvas.addEventListener('click',e=>{if(running||!geometry)return;const {left,right,xmin,xmax,byDistance}=geometry;const x=Math.max(0,Math.min(1,(e.clientX-canvas.getBoundingClientRect().left-left)/(right-left))),value=xmin+x*(xmax-xmin);if(byDistance)seek(value*1000);else{const i=Math.min(points.length-1,Math.floor(value)),j=Math.min(i+1,points.length-1);seek(points[i].distance+(points[j].distance-points[i].distance)*(value-i));}});
 let dragging=false,wasDragging=false,projected=null;
 function nearest(latlng){const p=map.latLngToLayerPoint(latlng);let best=Infinity,distance=0;for(let i=1;i<projected.length;i++){const a=projected[i-1],b=projected[i],dx=b.x-a.x,dy=b.y-a.y,den=dx*dx+dy*dy,t=den?Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/den)):0;const d=(p.x-a.x-t*dx)**2+(p.y-a.y-t*dy)**2;if(d<best){best=d;distance=points[i-1].distance+t*(points[i].distance-points[i-1].distance);}}return distance;}
 function end(){if(!dragging)return;dragging=false;projected=null;if(wasDragging)map.dragging.enable();}
 function bind(v){v.on('mousedown',e=>{if(running)return;L.DomEvent.stop(e.originalEvent);dragging=true;wasDragging=map.dragging.enabled();map.dragging.disable();projected=points.map(p=>map.latLngToLayerPoint([p.lat,p.lon]));});}
 if(map){map.on('mousemove',e=>{if(dragging&&!running)seek(nearest(e.latlng));});map.on('mouseup',end);map.on('zoomstart',end);}window.addEventListener('mouseup',end);window.addEventListener('blur',end);
 window.RouteControls={sync,seek,bind};if(vehicle){bind(vehicle);vehicle._routeSeekBound=true;}sync();
 window.RouteAnalysis={snapshot:()=>({points,model:window.TruckModel?.snapshot(),travel,running,title:document.getElementById('summary').textContent}),seek};
 document.getElementById('all-charts').onclick=()=>window.open('analysis.html','route-analysis');
})();
