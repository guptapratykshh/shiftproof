// Explicit source transformation, never DOM rewriting or source-evidence translation.
import fs from 'node:fs';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';
const catalogPath='frontend/src/locales/hi.json';
const catalog=JSON.parse(fs.readFileSync(catalogPath,'utf8'));
for(const line of fs.readFileSync('scripts/hindi-ui.tsv','utf8').split('\n')) {
  if(!line) continue;
  const tab=line.indexOf('\t'); if(tab<0) throw new Error('Invalid translation row: '+line);
  catalog[line.slice(0,tab)]=line.slice(tab+1);
}
fs.writeFileSync(catalogPath,JSON.stringify(catalog,null,2)+'\n');
const files=fs.readdirSync('frontend/src/platform').filter(f=>f.endsWith('.tsx')).map(f=>'frontend/src/platform/'+f).concat(['frontend/src/App.tsx']);
const normalize=s=>s.replace(/\s+/g,' ').trim();
const available=s=>Object.hasOwn(catalog,normalize(s));
const display=n=>{
  const p=n.parent;
  if(ts.isJsxExpression(p))return ts.isJsxElement(p.parent)||ts.isJsxFragment(p.parent);
  if(ts.isConditionalExpression(p)&&n!==p.condition)return display(p);
  if(ts.isBinaryExpression(p)&&n===p.right&&[ts.SyntaxKind.BarBarToken,ts.SyntaxKind.QuestionQuestionToken].includes(p.operatorToken.kind))return display(p);
  if(ts.isParenthesizedExpression(p))return display(p);
  return false;
};
let total=0;
for(const file of files){
 const source=fs.readFileSync(file,'utf8'),ast=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),edits=[];
 function visit(n){
  if(ts.isJsxText(n)&&available(n.text)&&normalize(n.text)){
   const inline=!n.text.includes('\n'),before=inline&&/^\s/.test(n.text)?'{" "}':'',after=inline&&/\s$/.test(n.text)?'{" "}':'';
   edits.push([n.pos,n.end,before+'{tr('+JSON.stringify(normalize(n.text))+')}'+after]);return;
  }
  if(ts.isJsxAttribute(n)&&['placeholder','title','aria-label','label','alt'].includes(n.name.getText(ast))&&n.initializer&&ts.isStringLiteral(n.initializer)&&available(n.initializer.text)){
   edits.push([n.initializer.getStart(ast),n.initializer.end,'{tr('+JSON.stringify(n.initializer.text)+')}']);return;
  }
  if(ts.isStringLiteral(n)&&available(n.text)&&display(n)){
   edits.push([n.getStart(ast),n.end,'tr('+JSON.stringify(n.text)+')']);return;
  }
  ts.forEachChild(n,visit);
 }
 visit(ast);if(!edits.length)continue;
 let result=source;for(const [start,end,text] of edits.sort((a,b)=>b[0]-a[0]))result=result.slice(0,start)+text+result.slice(end);
 if(!/import\s*\{[^}]*\btr\b[^}]*\}\s*from\s*["']\.\.?\/i18n/.test(result))result='import { tr } from '+JSON.stringify(file.endsWith('/App.tsx')?'./i18n':'../i18n')+';\n'+result;
 fs.writeFileSync(file,result);total+=edits.length;
}
console.log(`Localized ${total} static interface expressions. Catalog: ${Object.keys(catalog).length} messages.`);
