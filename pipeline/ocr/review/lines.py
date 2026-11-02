import os
import numpy as np, sys, json
from PIL import Image
def load(p):
    a=np.asarray(Image.open(os.path.join(os.environ.get('GPURA_ITEM_DIR','.'),'images',f'{p}.png')).convert('RGB')).astype(int)
    R,G,B=a[...,0],a[...,1],a[...,2]; gray=(R+G+B)/3
    prn=(gray<115)&((R-B)>=22)
    return a,prn
def cores(prn,x0,x1,y0,y1,thr=200,minlen=14):
    prof=prn[y0:y1,x0:x1].sum(1)
    on=prof>thr; runs=[];s=None
    for i,v in enumerate(on):
        if v and s is None: s=i
        if not v and s is not None:
            runs.append([s,i]); s=None
    if s is not None: runs.append([s,len(on)])
    merged=[]
    for r in runs:
        if merged and r[0]-merged[-1][1]<8: merged[-1][1]=r[1]
        else: merged.append(r)
    return [[y0+a,y0+b] for a,b in merged if b-a>=minlen]
if __name__=='__main__':
    p=sys.argv[1]; x0,x1,y0,y1=map(int,sys.argv[2:6])
    a,prn=load(p)
    for c in cores(prn,x0,x1,y0,y1):
        band=prn[c[0]:c[1]]
        cols=np.where(band.sum(0)>2)[0]
        print(c, c[1]-c[0], cols.min(), cols.max())
