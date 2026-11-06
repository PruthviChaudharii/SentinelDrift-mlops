"""Reproducible URL-only baseline. Does not fetch or visit dataset URLs."""
from pathlib import Path
import hashlib,json,subprocess,zipfile
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import classification_report,roc_auc_score,confusion_matrix
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
archive=ROOT/'.cache-data/phiusiil.zip'
with zipfile.ZipFile(archive) as z:
    name=next(n for n in z.namelist() if n.endswith('.csv'))
    df=pd.read_csv(z.open(name),usecols=['URL','label']).drop_duplicates('URL')
df=df.sample(min(80000,len(df)),random_state=42).reset_index(drop=True)
output=subprocess.run(['node',str(ROOT/'scripts/extract.cjs')],input=json.dumps(df.URL.tolist()),capture_output=True,text=True,check=True)
rows=json.loads(output.stdout);valid=np.array([r is not None for r in rows]);df=df[valid].reset_index(drop=True)
X=np.array([r for r in rows if r is not None]);y=1-df.label.to_numpy() # UCI 0=phishing; this model 1=phishing
groups=df.URL.map(lambda u:'.'.join((urlsplit(u).hostname or '').lower().split('.')[-2:])).to_numpy()
train,test=next(GroupShuffleSplit(n_splits=1,test_size=.2,random_state=42).split(X,y,groups))
clf=RandomForestClassifier(n_estimators=48,max_depth=11,min_samples_leaf=8,class_weight='balanced',random_state=42,n_jobs=-1)
clf.fit(X[train],y[train]);p=clf.predict_proba(X[test])[:,1];pred=(p>=.5).astype(int)
report=classification_report(y[test],pred,output_dict=True);tn,fp,fn,tp=confusion_matrix(y[test],pred).ravel()
reference=[]
for j in range(X.shape[1]):
    edges=np.unique(np.quantile(X[train,j],np.linspace(0,1,11)))[1:-1].tolist()
    counts=np.bincount(np.searchsorted(edges,X[train,j],side='right'),minlength=len(edges)+1)
    reference.append({'edges':edges,'counts':counts.tolist()})
trees=[]
for estimator in clf.estimators_:
    t=estimator.tree_;v=t.value[:,0,:];trees.append({'left':t.children_left.tolist(),'right':t.children_right.tolist(),'feature':t.feature.tolist(),'threshold':t.threshold.tolist(),'prob':(v[:,1]/v.sum(axis=1)).tolist()})
metrics={'f1':report['1']['f1-score'],'precision':report['1']['precision'],'recall':report['1']['recall'],'fnr':float(fn/(fn+tp)),'fpr':float(fp/(fp+tn)),'auc':roc_auc_score(y[test],p),'confusion':{'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)}}
metadata={'id':'phiusiil-rf-v1','family':'Random Forest · URL-only','source':'UCI PhiUSIIL, Prasad & Chandra, CC BY 4.0','source_url':'https://archive.ics.uci.edu/dataset/967/phiusiil+phishing+url+dataset','dataset_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'seed':42,'train_rows':len(train),'test_rows':len(test),'group_overlap':len(set(groups[train])&set(groups[test])),'split':'Hostname last-two-label groups; heuristic, not Public Suffix List. No temporal split available.','metrics':metrics,'limitations':'Historical benchmark with collection/source bias. URL-only model cannot verify website contents or guarantee arbitrary URL safety. Scores are not calibrated probabilities.'}
model={**metadata,'reference':reference,'importances':clf.feature_importances_.tolist(),'trees':trees}
(ROOT/'dist/model.json').write_text(json.dumps(model,separators=(',',':')),encoding='utf-8')
(ROOT/'dist/model-card.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
fixtures=[]
for i in test[:50]:fixtures.append({'url':df.URL.iloc[i],'expected':float(clf.predict_proba(X[i:i+1])[0,1])})
(ROOT/'.cache-data/parity.json').write_text(json.dumps(fixtures),encoding='utf-8')
(ROOT/'tests/model-parity.json').write_text(json.dumps([{'features':X[i].tolist(),'expected':float(clf.predict_proba(X[i:i+1])[0,1])} for i in test[:50]]),encoding='utf-8')
print(json.dumps(metadata,indent=2))
def gh(s):
    h=2166136261
    for c in s:
        h=((h^ord(c))*16777619)&0xffffffff
    return str(h)
def subset(indices,n):
    # Class-balanced, disjoint historical replay and governance pools.
    return np.concatenate([indices[y[indices]==label][:n] for label in [0,1]])
replay=subset(train,200);gate=subset(test,200)
def records(indices):
    return [{'x':X[i].tolist(),'y':int(y[i]),'group':gh(groups[i])} for i in indices]
assets={'base_id':metadata['id'],'replay':records(replay),'historical_gate':records(gate),'mean':X[train].mean(axis=0).tolist(),'scale':np.maximum(X[train].std(axis=0),1e-6).tolist(),'note':'Historical governance gate is drawn from the original reported holdout; future candidates evaluated here do not have an untouched final-test claim.'}
(ROOT/'dist/recovery-data.json').write_text(json.dumps(assets,separators=(',',':')),encoding='utf-8')
