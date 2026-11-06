// The exact production feature/prediction/recovery implementations, shared with the browser.
const fs=require('node:fs'),readline=require('node:readline');
const U=require('../dist/features.js'),R=require('../dist/recovery-engine.js');
const base=JSON.parse(fs.readFileSync('dist/model.json','utf8'));
const assets=JSON.parse(fs.readFileSync('dist/recovery-data.json','utf8'));U.configure(base);
const official=JSON.parse(fs.readFileSync('dist/official-regressions.json','utf8')).rows;
function evaluate(q,artifact){
 const e=R.evaluate(base,q.champion,artifact,q.feedback,assets,U,q.threshold);
 const limit=Math.max(.005,(e.championHistorical.fpr||0)+.0025);
 const scores=official.map(r=>R.probability(base,artifact,U.extract(r.url),U));
 const violations=scores.filter(p=>p>base.policy.low).length;
 e.checks.push({name:'Historical false-positive guard',pass:e.historical.fpr!==null&&e.historical.fpr<=limit,detail:`FPR ${e.historical.fpr}; limit ${limit}`},
 {name:'Recent legitimate-site regression',pass:e.recent.fpr!==null&&e.recent.fpr<=e.championRecent.fpr,detail:`Recent FPR ${e.recent.fpr} vs champion ${e.championRecent.fpr}; no increase allowed`},
 {name:'Official-domain regression suite',pass:violations===0,detail:`${violations}/${official.length} development regression examples left the lower-risk band. This suite is not a random safety guarantee.`});
 e.official_regressions={n:official.length,violations,max_score:Math.max(...scores),scope:'development regression guard, not untouched evaluation or runtime allowlist'};
 e.pass=e.checks.every(c=>c.pass);return e;
}
function handle(q){
 if(q.op==='info')return {id:base.id,policy:base.policy,names:U.names,importances:base.importances,reference:base.reference,assets};
 if(q.op==='features')return q.urls.map(raw=>{const u=new URL(raw);u.hash='';if(u.href.length>4096)throw Error('URL exceeds 4096 characters');return {url:u.href,x:U.extract(u.href),group:R.group(u.href),role:R.partition(u.href,assets),caution:u.username||u.password?`User information appears before @. The actual destination host is ${u.hostname}; text before @ is not the website host.`:null}});
 if(q.op==='predict')return q.rows.map(x=>R.probability(base,q.artifact,x,U));
 if(q.op==='ready'){const p=R.ready(q.feedback,assets);return {ok:p.ok,train:p.train.length,validation:p.validation.length}};
 if(q.op==='train'){const result=R.train(base,q.feedback,assets,U);return {...result,evaluation:evaluate(q,result.artifact)}};
 if(q.op==='evaluate')return evaluate(q,q.artifact);
 throw Error('Unknown operation');
}
readline.createInterface({input:process.stdin}).on('line',line=>{try{process.stdout.write(JSON.stringify({result:handle(JSON.parse(line))})+'\n')}catch(e){process.stdout.write(JSON.stringify({error:e.message})+'\n')}});
