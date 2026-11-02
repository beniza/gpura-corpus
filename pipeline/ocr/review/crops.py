import os
import sys
from PIL import Image
p=sys.argv[1]; cores=eval(open(f'{p}_cores.txt').read())
im=Image.open(os.path.join(os.environ.get('GPURA_ITEM_DIR','.'),'images',f'{p}.png'))
for k in range(0,len(cores),3):
    grp=cores[k:k+3]
    y0=grp[0][0]-35; y1=grp[-1][1]+40
    im.crop((40,y0,1260,y1)).save(f'../v/{p}_L{k+1:02d}a.png')
    im.crop((1180,y0,2380,y1)).save(f'../v/{p}_L{k+1:02d}b.png')
