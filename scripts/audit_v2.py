"""One-off frozen-model audit on additional PhreshPhish test shards, no tuning."""
import json,hashlib,subprocess,concurrent.futures
from pathlib import Path
from urllib.parse import urlsplit
import requests,pandas as pd,numpy as np,tldextract
from sklearn.metrics import confusion_matrix
from collect_external import fetch_shard
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache-data';OUT=CACHE/'candidate-v2'
model=json.loads((OUT/'model.json').read_text(encoding='utf-8'));manifest=json.loads((CACHE/'phresh-manifest.json').read_text());revision=manifest['revision'];repo=manifest['repo']
files=requests.get(f'https://huggingface.co/api/datasets/{repo}/tree/{revision}/data?limit=1000',timeout=30).json()
selected=[f for f in files if f['path'] in ['data/test-004.parquet','data/test-018.parquet']]
assert len(selected)==2
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:records=list(pool.map(fetch_shard,[(repo,revision,f) for f in selected]))
d=pd.concat([pd.read_csv(CACHE/r['file']) for r in records],ignore_index=True).drop_duplicates('url')
ext=tldextract.TLDExtract(suffix_list_urls=(),include_psl_private_domains=True)
def domain(u):
    try:
        host=(urlsplit(u).hostname or '').encode('idna').decode();return ext(host).top_domain_under_public_suffix or host
    except (ValueError,UnicodeError):return ''
excluded=set(json.loads((CACHE/'development-groups-v2.json').read_text()))|set(model['development_smoke_domains'])
d['group']=d.url.map(domain);d=d[~d.group.isin(excluded)&d.group.ne('')].groupby('group',group_keys=False).head(25).reset_index(drop=True)
script="const fs=require('fs'),U=require('./dist/features.js'),m=JSON.parse(fs.readFileSync('.cache-data/candidate-v2/model.json','utf8'));U.configure(m);const urls=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(urls.map(u=>{try{return U.predict(m,U.extract(u))}catch{return null}})));"
r=subprocess.run(['node','-e',script],input=json.dumps(d.url.tolist()),capture_output=True,text=True,check=True,cwd=ROOT);p=json.loads(r.stdout);mask=np.array([s is not None for s in p]);d=d[mask];p=np.array([s for s in p if s is not None]);y=d.label.to_numpy();high=model['policy']['high'];low=model['policy']['low'];tn,fp,fn,tp=confusion_matrix(y,p>=high,labels=[0,1]).ravel()
def wilson(k,n):
    z=1.96;a=k/n;b=z*z/n;delta=z*np.sqrt(a*(1-a)/n+z*z/(4*n*n));return [(a+b/2-delta)/(1+b),(a+b/2+delta)/(1+b)]
report={'model_id':model['id'],'model_sha256':hashlib.sha256((OUT/'model.json').read_bytes()).hexdigest(),'threshold':high,'source_repo':repo,'revision':revision,'files':records,'rows':len(d),'domain_overlap_with_development':0,'legitimate':int((y==0).sum()),'phishing':int((y==1).sum()),'false_positives':int(fp),'false_positive_rate':float(fp/(tn+fp)),'false_positive_rate_95pct_wilson':wilson(int(fp),int(tn+fp)),'strong_warning_precision':float(tp/(tp+fp)),'strong_warning_recall':float(tp/(tp+fn)),'uncertain_rows':int(((p>low)&(p<high)).sum()),'phishing_assigned_lower_risk':int(((y==1)&(p<=low)).sum()),'note':'Additional records and registrable domains excluded from development; frozen candidate, no audit-based threshold adjustment. Sources remain historical and are not an arbitrary-URL guarantee.'}
(ROOT/'dist/classifier-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
