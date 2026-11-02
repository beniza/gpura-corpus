import os
import numpy as np, json, sys
from PIL import Image
from scipy import ndimage
def masks(p):
    a=np.asarray(Image.open(os.path.join(os.environ.get('GPURA_ITEM_DIR','.'),'images',f'{p}.png')).convert('RGB')).astype(int)
    R,G,B=a[...,0],a[...,1],a[...,2]
    gray=(R+G+B)/3
    blue=(B-R>25)&(gray<170)
    # print ink: dark & not bluish. Reader dark ink underlines are dark too (handled later)
    dark=(gray<110)&~blue
    return a,dark,blue
if __name__=='__main__':
    p=sys.argv[1]; x0,x1,y0,y1=map(int,sys.argv[2:6])
    a,dark,blue=masks(p)
    prof=dark[y0:y1,x0:x1].sum(1)
    for i in range(0,y1-y0,4):
        v=prof[i:i+4].mean()
        print(y0+i, int(v), '#'*int(v/20))
