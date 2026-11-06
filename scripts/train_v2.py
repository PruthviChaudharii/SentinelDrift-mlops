"""Multi-source URL-only classifier. Selection uses validation only; final sets are separate."""
import hashlib,json,subprocess,zipfile
from pathlib import Path
from urllib.parse import urlsplit
import numpy as np,pandas as pd,tldextract
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix,roc_auc_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import GroupKFold
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache-data'
manifest=json.loads((CACHE/'phresh-manifest.json').read_text())
ext=tldextract.TLDExtract(suffix_list_urls=(),include_psl_private_domains=True)
def canonical(u):
    try:
        p=urlsplit(str(u));host=(p.hostname or '').encode('idna').decode().lower()
        if p.scheme not in ['http','https'] or not host:return None
        auth=(p.username or '')+(':'+p.password if p.password else '')+'@' if p.username is not None else ''
        return p._replace(netloc=auth+host+(':'+str(p.port) if p.port else ''),fragment='').geturl()
    except (ValueError,UnicodeError):return None
def group(u):
    h=urlsplit(u).hostname;return ext(h).top_domain_under_public_suffix or h
parts=[];external=[]
for item in manifest['files']:
    d=pd.read_csv(CACHE/item['file']);d['source']='PhreshPhish';(external if 'test-' in item['path'] else parts).append(d)
d=pd.read_csv(CACHE/'mendeley.csv');d['source']='Hannousse-Yahiouche';parts.append(d)
with zipfile.ZipFile(CACHE/'phiusiil.zip') as z:d=pd.read_csv(z.open(next(n for n in z.namelist() if n.endswith('.csv'))),usecols=['URL','label']).rename(columns={'URL':'url'})
d['label']=1-d.label;d=d.groupby('label',group_keys=False).sample(n=2500,random_state=42);d['source']='PhiUSIIL';parts.append(d)
smoke_domains=['chelseafc.com','wikipedia.org','microsoft.com','apple.com','google.com','amazon.com','syngenta.com','github.com','openai.com','bbc.com','nasa.gov','mit.edu','stanford.edu','python.org','adobe.com','salesforce.com','nike.com','samsung.com','tata.com','infosys.com','wipro.com','ibm.com','oracle.com','nvidia.com','intel.com','mozilla.org','paypal.com','stripe.com','netflix.com','spotify.com','un.org','who.int']
def clean(d):
    d=d.copy();d['url']=d.url.map(canonical);d=d.dropna(subset=['url','label']);d['label']=d.label.astype(int)
    conflicts=d.groupby('url').label.nunique();d=d[~d.url.isin(conflicts[conflicts>1].index)].drop_duplicates('url')
    d['group']=d.url.map(group);d=d[~d.group.isin(smoke_domains)]
    # Domain cap prevents a few large sites dominating the classifier.
    return d.sample(frac=1,random_state=42).groupby('group',group_keys=False).head(25).reset_index(drop=True)
data=clean(pd.concat(parts));outside=clean(pd.concat(external));outside=outside[~outside.group.isin(set(data.group))].reset_index(drop=True)
def features(d):
    r=subprocess.run(['node',str(ROOT/'scripts/extract.cjs'),'--bundle'],input=json.dumps(d.url.tolist()),capture_output=True,text=True,check=True)
    bundle=json.loads(r.stdout);x=bundle['features'];valid=np.array([v is not None for v in x]);d=d[valid].reset_index(drop=True);d['url']=[u for u,v in zip(bundle['canonical'],valid) if v];return d,np.array([v for v in x if v is not None])
data,X=features(data);outside,Xout=features(outside);y=data.label.to_numpy();yo=outside.label.to_numpy()
fold=data.group.map(lambda s:int(hashlib.sha256(('42:'+s).encode()).hexdigest()[:8],16)%100).to_numpy()
train=np.where(fold<60)[0];val=np.where((fold>=60)&(fold<75))[0];gate=np.where((fold>=75)&(fold<85))[0];test=np.where(fold>=85)[0]
groups_by_split=[set(data.group.iloc[ix]) for ix in [train,val,gate,test]]
assert all(not groups_by_split[i]&groups_by_split[j] for i in range(4) for j in range(i+1,4))
assert not set(outside.group)&set(data.group)
def measure(y,p,threshold):
    tn,fp,fn,tp=confusion_matrix(y,p>=threshold,labels=[0,1]).ravel();n0=int(tn+fp);n1=int(tp+fn)
    return {'n':len(y),'legitimate':n0,'phishing':n1,'f1':float(2*tp/(2*tp+fp+fn or 1)),'precision':float(tp/(tp+fp or 1)),'recall':float(tp/(tp+fn or 1)),'fnr':float(fn/(n1 or 1)),'fpr':float(fp/(n0 or 1)),'auc':float(roc_auc_score(y,p)),'confusion':{'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)},'uncertain':int(((p>.2)&(p<threshold)).sum()),'low_risk_phishing':int(((y==1)&(p<=.2)).sum())}
# Text model fit only on training domains; RF training uses out-of-fold text evidence.
vectorizer=TfidfVectorizer(analyzer='char',ngram_range=(3,5),lowercase=True,min_df=3,max_features=18000,sublinear_tf=True)
T=vectorizer.fit_transform(data.url.iloc[train]);Tall=vectorizer.transform(data.url);Tout=vectorizer.transform(outside.url)
def fit_text(ix):return SGDClassifier(loss='log_loss',alpha=.00003,max_iter=500,tol=1e-4,class_weight={0:2,1:1},random_state=42).fit(T[ix],y[train][ix])
text_clf=fit_text(np.arange(len(train)));X[:,20]=text_clf.predict_proba(Tall)[:,1];Xout[:,20]=text_clf.predict_proba(Tout)[:,1]
for fit_ix,held_ix in GroupKFold(n_splits=3).split(T,y[train],data.group.iloc[train]):
    fold_model=fit_text(fit_ix);X[train[held_ix],20]=fold_model.predict_proba(T[held_ix])[:,1]
text_export={'vocab':{k:int(v) for k,v in vectorizer.vocabulary_.items()},'idf':vectorizer.idf_.tolist(),'weights':text_clf.coef_[0].tolist(),'intercept':float(text_clf.intercept_[0]),'ngrams':[3,5],'normalization':'sublinear TF-IDF, L2'}
# Remove the strongest known collection shortcut: HTTPS is monitored but never split on.
selected=[i for i in range(21) if i!=9]
configs=[{'n_estimators':96,'max_depth':14,'min_samples_leaf':10,'class_weight':{0:2,1:1}},{'n_estimators':96,'max_depth':16,'min_samples_leaf':6,'class_weight':{0:3,1:1}}]
choices=[]
for config in configs:
    clf=RandomForestClassifier(**config,max_features=.75,random_state=42,n_jobs=-1).fit(X[train][:,selected],y[train])
    p=clf.predict_proba(X[val][:,selected])[:,1]
    candidates=[]
    for threshold in np.arange(.5,.996,.01):
        m=measure(y[val],p,float(threshold))
        if m['fpr']<=.005:candidates.append((m['recall'],float(threshold),m))
    best=max(candidates,key=lambda c:c[0]) if candidates else (0,.99,measure(y[val],p,.99))
    choices.append((best[0],clf,best[1],best[2],config))
_,clf,threshold,validation,config=max(choices,key=lambda c:c[0])
def probs(x):return clf.predict_proba(x[:,selected])[:,1]
def histogram(indices):
    result=[]
    for j in range(21):
        edges=np.unique(np.quantile(X[indices,j],np.linspace(0,1,11)))[1:-1].tolist();counts=np.bincount(np.searchsorted(edges,X[indices,j],side='right'),minlength=len(edges)+1)
        result.append({'edges':edges,'counts':counts.tolist()})
    return result
trees=[]
for e in clf.estimators_:
    t=e.tree_;v=t.value[:,0,:];features=[int(selected[i]) if i>=0 else int(i) for i in t.feature]
    trees.append({'left':t.children_left.tolist(),'right':t.children_right.tolist(),'feature':features,'threshold':t.threshold.tolist(),'prob':(v[:,1]/v.sum(axis=1)).tolist()})
importance=np.zeros(21);importance[selected]=clf.feature_importances_
metadata={'id':'multisource-rf-v2','family':'Random Forest + learned URL-text evidence','feature_version':3,'source':'PhreshPhish (Dalton et al.), Hannousse & Yahiouche, PhiUSIIL (Prasad & Chandra); CC BY 4.0','development_smoke_domains':smoke_domains,'source_url':'https://huggingface.co/datasets/phreshphish/phreshphish','sources':manifest,'seed':42,'train_rows':len(train),'validation_rows':len(val),'governance_rows':len(gate),'test_rows':len(test),'external_test_rows':len(outside),'group_overlap':0,'split':'Fixed SHA256 partitions of registrable domains using bundled Public Suffix List (including private suffixes). Train 60%, selection 15%, governance 10%, final test 15%. External PhreshPhish test domains overlapping development excluded. Smoke domains excluded from all partitions.','policy':{'high':round(threshold,4),'low':.2,'target_validation_fpr':.005,'selected_on':'validation only; maximize phishing recall subject to FPR <= 0.5%'},'validation_metrics':validation,'metrics':measure(y[test],probs(X[test]),threshold),'external_metrics':measure(yo,probs(Xout),threshold),'config':config,'limitations':'URL-only structural evidence cannot establish a site is official or safe. Scores are not calibrated probabilities. Abstention is not protection. Historical benchmark sources are not live threat intelligence; domain caps/splits reduce but cannot eliminate collection and campaign bias. False positives and false negatives remain.'}
model={**metadata,'text_model':text_export,'public_suffixes':sorted(ext.tlds),'reference':histogram(train),'importances':importance.tolist(),'trees':trees}
out=CACHE/'candidate-v2';out.mkdir(exist_ok=True)
(out/'model.json').write_text(json.dumps(model,separators=(',',':')),encoding='utf-8');(out/'model-card.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
def gh(s):
    h=2166136261
    for c in s:h=((h^ord(c))*16777619)&0xffffffff
    return str(h)
def subset(indices,n):return np.concatenate([indices[y[indices]==label][:n] for label in [0,1]])
def records(ix):return [{'x':X[i].tolist(),'y':int(y[i]),'group':gh(data.group.iloc[i])} for i in ix]
assets={'base_id':metadata['id'],'replay':records(subset(train,200)),'historical_gate':records(subset(gate,200)),'mean':X[train].mean(axis=0).tolist(),'scale':np.maximum(X[train].std(axis=0),1e-6).tolist(),'note':'Governance is a separate domain-disjoint partition, not final test.'}
(out/'recovery-data.json').write_text(json.dumps(assets,separators=(',',':')),encoding='utf-8')
(out/'model-parity.json').write_text(json.dumps([{'features':X[i].tolist(),'expected':float(probs(X[i:i+1])[0])} for i in test[:50]]),encoding='utf-8')
(CACHE/'v2-evaluation.csv').write_text(pd.DataFrame({'url':data.url.iloc[test],'label':y[test],'score':probs(X[test])}).to_csv(index=False),encoding='utf-8')
(CACHE/'development-groups-v2.json').write_text(json.dumps(sorted(set(data.group)|set(outside.group))),encoding='utf-8')
(CACHE/'v2-external-evaluation.csv').write_text(pd.DataFrame({'url':outside.url,'label':yo,'score':probs(Xout)}).to_csv(index=False),encoding='utf-8')
metadata_summary={k:metadata[k] for k in ['id','train_rows','validation_rows','governance_rows','test_rows','external_test_rows','policy','validation_metrics','metrics','external_metrics']}
print(json.dumps(metadata_summary,indent=2),flush=True)
