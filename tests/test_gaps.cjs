const assert=require('assert');
global.RouteData=require('../data.js');
const {cutRows}=require('../gaps.js');
const head='point_id,latitude,longitude,elevation_m,distance_from_start_m,extra';
const input=head+'\n'+Array.from({length:101},(_,i)=>`${i},55,${37+i*.001},${100+i},${i*1000},"строка, ${i}"`).join('\n');
const original=RouteData.csv(input);
const a=cutRows(input,10,3,42),b=cutRows(input,10,3,42),c=cutRows(input,10,3,43);
assert.equal(a.text,b.text);assert.notEqual(a.text,c.text);assert(a.removed>0);
const rows=RouteData.csv(a.text);assert.deepEqual(rows[0],original[0]);
assert.equal(rows[1][0],'0');assert.equal(rows.at(-1)[0],'100');
for(const row of rows.slice(1))assert.deepEqual(row,original[Number(row[0])+1]);
assert.equal(rows.length,original.length-a.removed);
let last=0;
for(const [start,end] of a.intervals){assert(start-last>=5000&&start-last<15000);assert(end-start>0&&end-start<=4500);last=end;}
assert.throws(()=>cutRows(input,0,2,42));assert.throws(()=>cutRows(input,1,2,-1));
assert(cutRows(input,10000,1,42).removed===0);
console.log('PASS: repeatable randomness, interval bounds, only original rows retained, endpoints, invalid input, no-hit case');
