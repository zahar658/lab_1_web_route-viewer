import sys,math,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import truck_model as m
start=time.time()
flat=m.optimize({'points':[[0,100],[3000,100]],'params':{'step':250,'average':60,'initial':60,'final':60}})
assert flat['feasible'],flat
assert flat['time_s']<=flat['budget_s']+1e-6
assert flat['fuel_l']>0 and flat['baseline']
assert flat['fuel_l']<=flat['baseline']['fuel_l']+1e-5
for a,b in zip(flat['nodes'],flat['nodes'][1:]):
 t=m.transition(a['speed']/3.6,b['speed']/3.6,b['distance']-a['distance'],b['height']-a['height'],flat['params'])
 assert t and abs(t[1]-a['duration'])<1e-8
 assert a['speed']>=20 and a['speed']<=flat['params']['vmax']
 assert a['peak_power']<=flat['params']['power']+1e-7
assert math.isclose(flat['nodes'][-1]['fuel'],flat['fuel_l'])
assert math.isclose(sum(n['rate']*n['duration']/3600 for n in flat['nodes']),flat['fuel_l'])
fast=m.optimize({'points':[[0,100],[3000,100]],'params':{'average':100}})
assert not fast['feasible']
weak=m.optimize({'points':[[0,0],[1000,300]],'params':{'power':20,'torque':100,'average':30}})
assert not weak['feasible']
for params in [{'mass':-1},{'efficiency':0},{'gears':[1,2]},{'initial':130},{'average':float('nan')}]:
 try:m.optimize({'points':[[0,0],[1000,0]],'params':params});raise AssertionError('Invalid params accepted')
 except ValueError:pass
print('flat',flat['fuel_l'],flat['average_kmh'],'baseline',flat['baseline'])
print('Tests passed in',round(time.time()-start,2),'s')
# Search a bounded educational climb example that needs momentum.
for rise in [20,30,40,50,60]:
 profile=[[0,0],[1500,0],[2000,rise],[3500,rise]]
 r=m.optimize({'points':profile,'params':{'power':150,'average':50,'initial':50,'final':50,'step':250}})
 if r['feasible']:
  ns=r['nodes'];entry=next(n for n in ns if n['distance']==1500)
  crest=next(n for n in ns if n['distance']==2000)
  print('hill',rise,'entry',entry['speed'],'crest',crest['speed'],'avg',r['average_kmh'])
  if entry['speed']>50 and crest['speed']<entry['speed']:
   print('Momentum example passed');break
else:raise AssertionError('No anticipatory acceleration case found')
