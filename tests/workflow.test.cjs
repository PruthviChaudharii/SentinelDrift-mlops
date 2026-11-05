const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
function workspace(){
 const elements=new Map();const stored=new Map();
 const ctx=vm.createContext({URL,Date,JSON,Math,Number,String,Set,Error,crypto:require('node:crypto').webcrypto,location:{hash:'#overview'},localStorage:{getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)},document:{getElementById:id=>{if(!elements.has(id))elements.set(id,{style:{},textContent:'',innerHTML:'',showModal(){},close(){}});return elements.get(id)},querySelectorAll:()=>[]},window:{addEventListener(){},scrollTo(){}},setInterval(){},setTimeout:f=>{f();return 1},clearTimeout(){}});
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../dist/app.js'),'utf8'),ctx);
 vm.runInContext('render=()=>{};toast=()=>{};',ctx);
 return {get:expr=>vm.runInContext(expr,ctx)};
}
test('candidate cannot promote before canary evidence; rollback restores champion',async()=>{
 const w=workspace();w.get('traffic(true)');await w.get('recover()');assert.equal(w.get('state.candidate'),'rf-002');w.get("action('promote')");assert.equal(w.get('state.champion'),'rf-001');w.get("action('canary')");w.get("action('promote')");assert.equal(w.get('state.champion'),'rf-001');w.get("action('observe');action('promote')");assert.equal(w.get('state.champion'),'rf-002');assert.equal(w.get('state.candidate'),null);w.get("action('rollback')");assert.equal(w.get('state.champion'),'rf-001');assert.equal(w.get('state.models.filter(m=>m.status===\"Champion\").length'),1);
});
test('failed gates preserve champion and do not create deployable candidate',async()=>{
 const w=workspace();w.get('traffic(true)');await w.get('recover(true)');assert.equal(w.get('state.runs[0].status'),'Rejected');assert.equal(w.get('state.candidate'),null);w.get("action('canary');action('promote')");assert.equal(w.get('state.champion'),'rf-001');assert.equal(w.get('state.canary'),false);
});
test('stable distribution takes no action and disabled policy blocks recovery',async()=>{
 const w=workspace();await w.get('recover()');assert.equal(w.get('state.runs[0].status'),'No action');w.get('state.settings.enabled=false');await w.get('recover(true)');assert.equal(w.get('state.runs.length'),1);
});
test('URL validation rejects executable protocols; risk scoring is explicit',()=>{
 const w=workspace();assert.throws(()=>w.get("scoreURL('javascript:alert(1)')"));assert.equal(w.get("scoreURL('https://example.com').score"),5);assert.equal(w.get("scoreURL('http://account-verify.example.xyz/login').flag"),true);
});
test('CSV parser supports quoted commas, CRLF and rejects unclosed quotes',()=>{
 const w=workspace();assert.equal(w.get('parseCSV(\'url,label\\r\\n"https://example.com/a,b",0\\r\\n\')[1][0]'),'https://example.com/a,b');assert.throws(()=>w.get('parseCSV(\'url,label\\n"unclosed,1\')'));
});
