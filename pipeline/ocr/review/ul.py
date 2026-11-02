import os
import numpy as np, sys
from PIL import Image, ImageDraw
from scipy import ndimage
def annot_mask(p):
    a=np.asarray(Image.open(os.path.join(os.environ.get('GPURA_ITEM_DIR','.'),'images',f'{p}.png')).convert('RGB')).astype(int)
    R,G,B=a[...,0],a[...,1],a[...,2]; gray=(R+G+B)/3
    return a,(gray<150)&((R-B)<18)
def underlines(p):
    a,m=annot_mask(p)
    m2=ndimage.binary_closing(m,structure=np.ones((5,25)))
    lab,n=ndimage.label(m2)
    out=[]
    for i,sl in enumerate(ndimage.find_objects(lab)):
        h=sl[0].stop-sl[0].start; w=sl[1].stop-sl[1].start
        cnt=(lab[sl]==i+1).sum()
        if w>=120 and h<=70 and w>3*h:
            out.append([sl[1].start,sl[0].start,w,h,int(cnt)])
    return a,m,out
if __name__=='__main__':
    p=sys.argv[1]
    a,m,out=underlines(p)
    im=Image.fromarray(a.astype('uint8')); d=ImageDraw.Draw(im)
    for x,y,w,h,c in out:
        d.rectangle([x,y,x+w,y+h],outline=(255,0,0),width=5); print(x,y,w,h,c)
    im.resize((im.width//3,im.height//3)).save(f'../v/{p}_ul.png')
