// The exact production feature/prediction/recovery implementations, shared with the browser.
const fs=require('node:fs'),readline=require('node:readline');
const U=require('../dist/features.js'),R=require('../dist/recovery-engine.js');
const base=JSON.parse(fs.readFileSync('dist/model.json','utf8'));
const assets=JSON.parse(fs.readFileSync('dist/recovery-data.json','utf8'));U.configure(base);
function handle(q){
 if(q.op==='info')return {id:base.id,policy:base.policy,names:U.names,importances:base.importances,reference:base.reference,assets};
 if(q.op==='features')return q.urls.map(raw=>{const u=new URL(raw);u.hash='';if(u.href.length>4096)throw Error('URL exceeds 4096 characters');return {url:u.href,x:U.extract(u.href),group:R.group(u.href),role:R.partition(u.href,assets),caution:u.username||u.password?`User information appears before @. The actual destination host is ${u.hostname}; text before @ is not the website host.`:null}});
 if(q.op==='predict')return q.rows.map(x=>R.probability(base,q.artifact,x,U));
 if(q.op==='ready'){const p=R.ready(q.feedback,assets);return {ok:p.ok,train:p.train.length,validation:p.validation.length}};
 if(q.op==='train'){const result=R.train(base,q.feedback,assets,U);return {...result,evaluation:R.evaluate(base,q.champion,result.artifact,q.feedback,assets,U,q.threshold)}};
 if(q.op==='evaluate')return R.evaluate(base,q.champion,q.artifact,q.feedback,assets,U,q.threshold);
 throw Error('Unknown operation');
}
readline.createInterface({input:process.stdin}).on('line',line=>{try{process.stdout.write(JSON.stringify({result:handle(JSON.parse(line))})+'\n')}catch(e){process.stdout.write(JSON.stringify({error:e.message})+'\n')}});
