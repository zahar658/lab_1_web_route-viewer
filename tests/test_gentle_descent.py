import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import terrain_strategy as s
# A shallow downhill cannot overcome rolling resistance. It must receive fuel.
r=s.simulate({'points':[[0,50],[4000,34],[5000,34]],'params':{'average':40}})
assert r['feasible'],r
assert r['downhill_fuel_l']>0
assert any(n['power']>0 and n['distance']<4000 for n in r['nodes'])
# At a summit finish the final speed still applies.
r=s.simulate({'points':[[0,0],[1500,0],[2500,20]],'params':{'average':35}})
assert r['feasible'],r
assert abs(r['nodes'][-1]['speed']-40)<=1
# Errors summarize all rejection categories rather than just the last attempt.
r=s.optimize({'points':[[0,0],[1500,0],[2500,200]],'params':{'average':40}})
assert not r['feasible']
assert '\n\n' in r['message'] and 'Пример:' in r['message']
print('PASS: traction on gentle descent, summit finish, grouped errors')
