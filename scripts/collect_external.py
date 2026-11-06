"""Read URL/label columns only; never fetch pages named by dataset URLs."""
import io,json,hashlib,concurrent.futures
from pathlib import Path
import requests,pandas as pd,pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1];CACHE=ROOT/'.cache-data';CACHE.mkdir(exist_ok=True)
class RemoteFile(io.RawIOBase):
    def __init__(self,url,size):self.url=url;self.size=size;self.pos=0
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        return self.pos
    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        n=min(n,self.size-self.pos)
        if not n:return b''
        if n>16000000:raise ValueError('Refusing large range: HTML is not needed')
        start=self.pos;end=start+n-1
        for attempt in range(3):
            r=requests.get(self.url+f'?range={start}-{end}',headers={'Range':f'bytes={start}-{end}'},timeout=90)
            if r.status_code==206 and len(r.content)==n:break
        else:raise RuntimeError(f'Range fetch failed {r.status_code} {start} {n}')
        self.pos+=n;return r.content
def fetch_shard(args):
    repo,rev,item=args;path=item['path'];dest=CACHE/('phresh-'+path.replace('/','-')+'.csv')
    if not dest.exists():
        f=RemoteFile(f'https://huggingface.co/datasets/{repo}/resolve/{rev}/{path}',item['size'])
        table=pq.ParquetFile(f).read(columns=['url','label'])
        d=table.to_pandas();d['label']=d.label.map({'benign':0,'phish':1});d.to_csv(dest,index=False)
    d=pd.read_csv(dest);print(path,len(d),d.label.value_counts().to_dict(),flush=True)
    return {'path':path,'file':dest.name,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'rows':len(d)}
def main():
    repo='phreshphish/phreshphish';rev='eca603e0ecd4f698f8d4d226c088659e72681239'
    items=requests.get(f'https://huggingface.co/api/datasets/{repo}/tree/{rev}/data?limit=1000',timeout=30).json()
    # Spread across collection shards, fixed selection independent of model outcomes.
    tr=sorted([i for i in items if '/train-' in i['path']],key=lambda i:i['path']);te=sorted([i for i in items if '/test-' in i['path']],key=lambda i:i['path'])
    selected=[tr[i] for i in sorted(set(round(j*(len(tr)-1)/7) for j in range(8)))]+[te[i] for i in sorted(set(round(j*(len(te)-1)/3) for j in range(4)))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:records=list(pool.map(fetch_shard,[(repo,rev,i) for i in selected]))
    manifest={'repo':repo,'revision':rev,'license':'CC BY 4.0; anti-phishing research','files':records}
    (CACHE/'phresh-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    repo='pirocheto/phishing-url';rev='1375d450d4540205ac11781b807249c9509739cd';parts=[]
    for split in ['train','test']:
        b=requests.get(f'https://huggingface.co/datasets/{repo}/resolve/{rev}/data/{split}.parquet',timeout=60).content
        d=pq.read_table(io.BytesIO(b),columns=['url','status']).to_pandas();parts.append(d)
    d=pd.concat(parts);d['label']=d.status.map({'legitimate':0,'phishing':1});d[['url','label']].to_csv(CACHE/'mendeley.csv',index=False)
    manifest['mendeley']={'mirror':repo,'revision':rev,'source':'https://data.mendeley.com/datasets/c2gw7fy2j4/3','sha256':hashlib.sha256((CACHE/'mendeley.csv').read_bytes()).hexdigest()}
    (CACHE/'phresh-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Collection complete',flush=True)

if __name__=='__main__':main()
