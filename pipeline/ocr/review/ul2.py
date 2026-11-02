import os
import numpy as np, sys
from PIL import Image, ImageDraw
from scipy import ndimage
def detect(p, cores, minw=150):
    a=np.asarray(Image.open(os.path.join(os.environ.get('GPURA_ITEM_DIR','.'),'images',f'{p}.png')).convert('RGB')).astype(int)
    R,G,B=a[...,0],a[...,1],a[...,2]; gray=(R+G+B)/3
    m=(gray<160)&((R-B)<15)
    incore=np.zeros(a.shape[0],bool)
    for c0,c1 in cores: incore[c0+2:c1-2]=True
    m[incore,:]=False
    m2=ndimage.binary_closing(m,structure=np.ones((3,31)))
    m2=ndimage.binary_opening(m2,structure=np.ones((1,15)))
    lab,n=ndimage.label(m2,structure=np.ones((3,3)))
    out=[]
    for i,sl in enumerate(ndimage.find_objects(lab)):
        h=sl[0].stop-sl[0].start; w=sl[1].stop-sl[1].start
        cnt=int((lab[sl]==i+1).sum())
        if w>=minw and w>4*h and cnt/w<12:
            out.append([sl[1].start,sl[0].start,w,h,cnt])
    return a,out
if __name__=='__main__':
    p=sys.argv[1]; cores=eval(open(f'{p}_cores.txt').read())
    a,out=detect(p,cores)
    im=Image.fromarray(a.astype('uint8')); d=ImageDraw.Draw(im)
    for x,y,w,h,c in out:
        d.rectangle([x,y,x+w,y+h],outline=(255,0,0),width=6); print(x,y,w,h,c)
    im.resize((im.width//3,im.height//3)).save(f'../v/{p}_ul.png')
