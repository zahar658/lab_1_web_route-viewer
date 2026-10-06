import csv,io,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import recovery

calls=[]
def api(coordinates):
    calls.append(coordinates)
    a,b=coordinates
    return {'features':[{'geometry':{'type':'LineString','coordinates':[
        a+[100],[(a[0]+b[0])/2,(a[1]+b[1])/2,105],b+[110]]}}]}
# IDs and old distance columns are deliberately inconsistent and ignored.
text='longitude,latitude,elevation_m,point_id,distance_from_start_m\n37,55,100,1000,90000\n37.0001,55,101,4,10\n37.1,55,110,5,11\n'
r=recovery.recover({'csv':text,'jump_km':1},api)
assert len(calls)==1 and r['report']['gaps']==1
rows=list(csv.DictReader(io.StringIO(r['csv'].lstrip('\ufeff'))))
assert len(rows)==4
assert [r['segment_recovered'] for r in rows]==['0','0','1','1']
assert [r['segment_recovery_gap'] for r in rows]==['0','0','1','1']
assert rows[-1]['point_source']=='observed' and rows[-1]['is_recovered']=='0'
assert [float(x['longitude']) for x in rows if x['point_source']=='observed']==[37,37.0001,37.1]
assert [float(x['elevation_m']) for x in rows if x['point_source']=='observed']==[100,101,110]
assert sum(x['point_source']=='api' for x in rows)==1
assert all(float(b['distance_from_start_m'])>=float(a['distance_from_start_m']) for a,b in zip(rows,rows[1:]))
other='longitude,latitude,elevation_m\n37,55,100\n37.0001,55,101\n37.1,55,110\n'
assert recovery.recover({'csv':other,'jump_km':1},api)['csv']==r['csv']
calls.clear()
r=recovery.recover({'csv':other,'jump_km':100},api)
assert not calls and r['report']['inserted']==0
try:recovery.recover({'csv':other,'jump_km':0},api);raise AssertionError()
except ValueError:pass
# API error must not silently bridge the gap or return a successful file.
def failed(coords):raise ValueError('HTTP 429')
try:recovery.recover({'csv':other,'jump_km':1},failed);raise AssertionError()
except ValueError as e:assert 'Файл 3 не создан' in str(e)
print('PASS: coordinate-only detection, no IDs/distances dependence, observed points preserved, provenance, no-gap, invalid threshold, API failure')

# More than the former 50-gap cap: every detected gap must be requested.
calls.clear()
many = 'longitude,latitude,elevation_m\n' + ''.join(f'{37+i*.02:.4f},55,100\n' for i in range(137))
result = recovery.recover({'csv':many,'jump_km':1},api)
assert len(calls)==136 and result['report']['gaps']==136
assert result['report']['observed']==137 and result['report']['inserted']==136
print('PASS: all 136 gaps recovered without a request-count cap')
