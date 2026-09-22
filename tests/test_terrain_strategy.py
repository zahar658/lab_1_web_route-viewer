import sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import terrain_strategy as s

hill=s.simulate({'points':[[0,0],[1500,0],[1800,6],[2100,8],[2500,20],[4000,20]],'params':{'average':40}})
assert hill['feasible'],hill
assert hill['time_s']<=hill['budget_s']
climb=[n for n in hill['nodes'] if n['phase']=='подъём']
assert len(climb)>20
assert all(b['power']<=a['power']+1e-8 for a,b in zip(climb,climb[1:]))
assert climb[-1]['power']<climb[0]['power']*.25
assert hill['crests'][0]['speed']<climb[0]['speed']
assert max(n['speed'] for n in hill['nodes'])<=90+1e-6
assert min(n['speed'] for n in hill['nodes'])>=20-.3
assert any(n['phase']=='разгон перед подъёмом' for n in hill['nodes'])
assert hill['nodes'][0]['power']>0 # Immediate pedal response, no startup ramp.
for n in hill['nodes'][:-1]:
 assert n['power']<=n['available']+1e-5
 assert n['rate_start']>=0 and n['rate_end']>=0
assert math.isclose(sum((n['rate_start']+n['rate_end'])/2*n['duration']/3600 for n in hill['nodes']),hill['fuel_l'],abs_tol=1e-9)
down=s.simulate({'points':[[0,100],[2000,60],[4000,60]],'params':{'average':40}})
assert down['feasible'],down
assert down['cutoff_steps']>0
assert all(n['rate']==0 and n['power']==0 for n in down['nodes'] if n['cutoff'])
assert not s.simulate({'points':[[0,0],[3000,0]],'params':{'average':100}})['feasible']
steep=s.simulate({'points':[[0,0],[1500,0],[2500,100],[4000,100]],'params':{'average':40}})
assert not steep['feasible'] and 'минимума' in steep['message']
try:s.simulate({'points':[[0,0],[1000,0]],'params':{'crest_power':101}});raise AssertionError('Invalid crest fraction accepted')
except ValueError:pass
print('PASS: monotone climb power over varying slopes, instant command, advance acceleration, bounds, fuel integration, cutoff, infeasible climb/time, validation.')
