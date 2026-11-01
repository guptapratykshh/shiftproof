// Run from the repository root: node scripts/check-translations.mjs
import fs from 'node:fs';
import path from 'node:path';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';
const catalog=JSON.parse(fs.readFileSync('frontend/src/locales/hi.json','utf8'));
const normalized=s=>s.replace(/\s+/g,' ').trim();
const failures=[];let keys=0;
const literalEnglishAllowed=new Set(['shiftproof','ShiftProof','Aarambh Packaging','Prisma STT','Timbre TTS','Timbre','EMP-017','12–128','PUMP-01','ORD-582','BATCH-01','B-17','Seal inspection','Packing floor','Carton team','Today evening','Asia/Kolkata','“Packing complete hai, lekin quality check pending hai.”','“Dispatch ke liye ready hai.”']);
function scan(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const f=path.join(dir,entry.name);if(entry.isDirectory())scan(f);else if(/\.(tsx|ts)$/.test(f)){
 const s=fs.readFileSync(f,'utf8');if(s.includes('\u2014'))failures.push(f+': literal em dash');
 const ast=ts.createSourceFile(f,s,ts.ScriptTarget.Latest,true,f.endsWith('tsx')?ts.ScriptKind.TSX:ts.ScriptKind.TS);
 const report=(n,m)=>failures.push(`${f}:${ast.getLineAndCharacterOfPosition(n.getStart(ast)).line+1}: ${m}`);
 function visit(n){
 if(ts.isJsxAttribute(n)&&['value','defaultValue','name','id','key'].includes(n.name.getText(ast))&&n.initializer&&/\b(tr|label|claimValue|roleLabel)\(/.test(n.initializer.getText(ast)))report(n,'Translation must not change form values or identity');
 if(ts.isCallExpression(n)&&n.expression.getText(ast)==='tr'&&n.arguments.length&&ts.isStringLiteral(n.arguments[0])){const key=normalized(n.arguments[0].text);keys++;if(!Object.hasOwn(catalog,key)&&!Object.keys(catalog).some(k=>k.toLowerCase()===key.toLowerCase()))report(n,'Missing Hindi translation: '+key);}
 if(ts.isJsxText(n)){const key=normalized(n.text);if(/[a-z]{3}/i.test(key)&&!literalEnglishAllowed.has(key))report(n,'Unlocalized JSX text: '+key);}
 ts.forEachChild(n,visit);
 }visit(ast);
}}}
scan('frontend/src');
for(const [key,value]of Object.entries(catalog)){if(!value.trim())failures.push('Empty translation: '+key);if((key+value).includes('\u2014'))failures.push('Em dash in catalog: '+key);}
if(failures.length){console.error(failures.join('\n'));process.exitCode=1;}else console.log(`Translation audit passed: ${keys} literal uses, ${Object.keys(catalog).length} catalog entries; no raw interface text or em dashes.`);
