import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import terrain_strategy as s
points=[[0,0],[1500,0],[2500,20],[4000,20]]
a=s.optimize({'points':points,'params':{'average':40}})
b=s.optimize({'points':points,'params':{'average':40,'cruise':120,'lookahead':5000,'crest_power':0,'response':60,'grade_threshold':.05,'momentum':0}})
assert a['feasible'] and b['feasible']
assert a['fuel_l']==b['fuel_l'] and a['time_s']==b['time_s']
assert b['params']['response']==8 and b['params']['grade_threshold']==.002
assert all(n['speed']>=b['params']['vmin']-1e-8 for n in b['nodes'])
assert b['crests'] and all(c['speed']>=b['params']['vmin']-1e-8 for c in b['crests'])
assert b['time_s']<=b['budget_s']
html=(Path(__file__).resolve().parents[1]/'index.html').read_text()
for key in ('cruise','lookahead','crest_power','response','grade_threshold'):
 assert f'id="truck-{key}"' not in html
print('PASS: removed controls, server defaults, automatic policy ignores old inputs, minimum crest speed and time limit')
