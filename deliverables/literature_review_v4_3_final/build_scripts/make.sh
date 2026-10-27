#!/bin/bash
set -e
cd "$(dirname "$0")"
../venv/bin/python build.py
pandoc manuscript_numbered.md -f markdown+tex_math_dollars -t docx --reference-doc=reference.docx --resource-path=. -o raw.docx
../venv/bin/python postprocess.py raw.docx V43.docx
timeout 300 soffice --headless --convert-to pdf --outdir pdf V43.docx >/dev/null 2>&1
pdfinfo pdf/V43.pdf | grep Pages
cd pdf && rm -f p-*.jpg sheet*.jpg && pdftoppm -jpeg -r 80 V43.pdf p && ../../venv/bin/python - <<'PY'
from PIL import Image
import glob
ps=sorted(glob.glob('p-*.jpg'))
for k in range(0,len(ps),4):
    ims=[Image.open(p) for p in ps[k:k+4]]
    w,h=ims[0].size
    sh=Image.new('RGB',(w*2,h*2),'white')
    for i,im in enumerate(ims): sh.paste(im,((i%2)*w,(i//2)*h))
    sh.save('sheet%02d.jpg'%(k//4+1),quality=80)
PY
