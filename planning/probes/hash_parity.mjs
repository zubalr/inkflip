// Node parity implementation of inkflip-c14n-v1; no dependencies/network.
import {createHash} from 'node:crypto';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
function u32(n){const b=Buffer.alloc(4);b.writeUInt32BE(n);return b;}
function string(s){if(/\p{Surrogate}/u.test(s))throw new Error('Unpaired surrogate');const b=Buffer.from(s,'utf8');return Buffer.concat([Buffer.from('S'),u32(b.length),b]);}
function canonical(v){
 if(v===null)return Buffer.from('N');if(v===true)return Buffer.from('T');if(v===false)return Buffer.from('F');
 if(typeof v==='number'){if(!Number.isFinite(v)||(Number.isInteger(v)&&!Number.isSafeInteger(v)))throw new Error('Unsafe number');const b=Buffer.alloc(9);b[0]=68;b.writeDoubleBE(v===0?0:v,1);return b;}
 if(typeof v==='string')return string(v);
 if(Array.isArray(v))return Buffer.concat([Buffer.from('L'),u32(v.length),...v.map(canonical)]);
 if(typeof v==='object'){const keys=Object.keys(v).sort((a,b)=>Buffer.compare(Buffer.from(a,'utf8'),Buffer.from(b,'utf8')));return Buffer.concat([Buffer.from('O'),u32(keys.length),...keys.flatMap(k=>[string(k),canonical(v[k])])]);}
 throw new Error('Unsupported canonical type');
}
const raw=JSON.parse(readFileSync(resolve(root,'contracts/hash-vectors.json'),'utf8'));
const vectors=Array.isArray(raw)?raw:raw.vectors;
const results=vectors.map((x,index)=>{const actual=createHash('sha256').update(canonical(x.value)).digest('hex');if(actual!==x.sha256)throw new Error(`Mismatch vector ${index}: ${actual}`);return {vector_index:index,passed:true};});
const result={status:'passed',scope:'Python-authored canonical hash vectors checked in actual Node; not browser runtime',node:process.version,count:results.length,results};
writeFileSync(resolve(root,'probes/results/hash-parity.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
