import csv,io,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import start
captured=[]
def fake_api(url,key,body):
    captured.append(body)
    return {'features':[{'geometry':{'type':'LineString','coordinates':[point+[100+i] for i,point in enumerate(body['coordinates'])]}}]}
start.ors=fake_api
points=[[37,55],[37.1,55.1],[37.2,55.2],[37.3,55.3]]
result=start.generate({'key':'test','coordinates':points})
assert captured[0]['coordinates']==points
rows=list(csv.DictReader(io.StringIO(result.decode('utf-8-sig'))))
assert len(rows)==4 and rows[-1]['longitude']=='37.3'
for invalid in [[],[points[0]],[points[0],points[0]],[[181,0],[0,0]],points*13]:
    try:start.generate({'key':'test','coordinates':invalid});raise AssertionError('Bad points accepted')
    except ValueError:pass
print('PASS: ordered waypoints, CSV, coordinate and duplicate validation')
