"""Public-domain development regression suite, never used as model training rows."""
import json,subprocess
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.cache-data/candidate-v2';m=json.loads((OUT/'model.json').read_text(encoding='utf-8'));tm=m['text_model']
urls=['https://www.chelseafc.com/en','https://www.microsoft.com/en-us/','https://www.apple.com/in/','https://docs.python.org/3/library/urllib.parse.html','https://www.syngenta.com/en','https://www.nasa.gov/missions/','https://www.wikipedia.org/en','https://www.ibm.com/in-en','https://www.infosys.com/','https://www.tata.com/','https://www.adobe.com/products/photoshop.html','https://www.nvidia.com/en-us/','https://www.mozilla.org/en-US/firefox/new/','https://www.paypal.com/signin','https://www.netflix.com/login','https://www.spotify.com/in-en/','https://www.stanford.edu/research/','https://www.mit.edu/education/','https://www.un.org/en/','https://www.who.int/health-topics','https://www.oracle.com/java/','https://www.intel.com/content/www/us/en/homepage.html','https://www.samsung.com/in/','https://www.nike.com/in/','https://www.openai.com/','https://www.stripe.com/payments','https://www.salesforce.com/in/','https://www.wipro.com/','https://www.bbc.com/news','https://www.github.com/login','https://www.amazon.com/s?k=books','https://www.google.com/search?q=mlops']
r=subprocess.run(['node',str(ROOT/'scripts/extract.cjs'),'--bundle'],input=json.dumps(urls),capture_output=True,text=True,check=True);bundle=json.loads(r.stdout);urls=bundle['canonical'];X=np.array(bundle['features'])
v=TfidfVectorizer(analyzer='char',ngram_range=(3,5),vocabulary=tm['vocab'],sublinear_tf=True);v.fit(['placeholder']);v.idf_=np.array(tm['idf']);z=v.transform(urls).dot(np.array(tm['weights']))+tm['intercept'];X[:,20]=1/(1+np.exp(-np.clip(z,-35,35)))
def predict(x):
    p=0
    for t in m['trees']:
        i=0
        while t['left'][i]!=-1:i=t['left'][i] if x[t['feature'][i]]<=t['threshold'][i] else t['right'][i]
        p+=t['prob'][i]
    return p/len(m['trees'])
rows=[{'url':u,'score':predict(x),'text_score':float(x[20]),'expected_no_strong_warning':True} for u,x in zip(urls,X)]
report={'note':'Development regression examples on official domains excluded from training; not a random or untouched test sample. Paths include structural variations and are not asserted to all return HTTP 200. No runtime allowlist is used.','model_id':m['id'],'high_threshold':m['policy']['high'],'rows':rows,'strong_warnings':sum(r['score']>=m['policy']['high'] for r in rows),'lower_risk':sum(r['score']<=m['policy']['low'] for r in rows)}
(ROOT/'dist/official-regressions.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
