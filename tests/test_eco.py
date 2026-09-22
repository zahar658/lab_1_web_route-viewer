import sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import terrain_strategy as s
# Gravity can exceed accel before reaching vmax. It must trigger braking, not failure.
r=s.simulate({'points':[[0,150],[1000,50],[3000,50]],'params':{'average':35}})
assert r['feasible'],r
assert any(n['cutoff'] and n['brake_force']>0 for n in r['nodes'])
assert all(n['accel']<=r['params']['accel']+1e-7 for n in r['nodes'])
body={'points':[[0,0],[1500,0],[2500,20],[4000,20]],'params':{'average':40}}
r=s.optimize(body)
assert r['feasible'],r
assert r['fuel_l']<=r['baseline']['fuel_l']+1e-9
assert r['fuel_l']==min(t['fuel_l'] for t in r['search'] if t['feasible'])
assert r['time_s']<=r['budget_s']
climb=[n for n in r['nodes'] if n['phase']=='подъём']
assert all(b['power']<=a['power']+1e-8 for a,b in zip(climb,climb[1:]))
assert all(n['peak_power']<=n['available']+1e-7 for n in r['nodes'])
assert math.isclose(sum(n['rate']*n['duration']/3600 for n in r['nodes']),r['fuel_l'],abs_tol=1e-8)
print('PASS: descent acceleration regression, constrained search, monotone climb power, fuel integration')
print('Candidates',r['passes'],'fuel',r['fuel_l'],'baseline',r['baseline']['fuel_l'],'average',r['average_kmh'])
import json
Path('tmp/eco-result.json').write_text(json.dumps(r))
