"""Compile tei_all.rng from TEI P5 source (TEIC/TEI 'released' branch) with TEIC/Stylesheets, via SaxonC-HE."""
import sys, os
from saxonche import PySaxonProcessor

P5 = sys.argv[1]          # .../tei-src/P5
XSL = sys.argv[2]         # .../stylesheets
OUT = sys.argv[3]         # output dir
os.makedirs(OUT, exist_ok=True)

def run(proc, style, src, out, params=None):
    x = proc.new_xslt30_processor()
    ex = x.compile_stylesheet(stylesheet_file=style)
    for k, v in (params or {}).items():
        ex.set_parameter(k, proc.make_string_value(v))
    ex.transform_to_file(source_file=src, output_file=out)
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        raise SystemExit(f"failed: {style} -> {out}")
    print("ok", os.path.basename(style), "->", out, os.path.getsize(out))

with PySaxonProcessor(license=False) as proc:
    p5 = os.path.join(OUT, "p5.xml")
    sub = os.path.join(OUT, "p5subset.xml")
    if not os.path.exists(p5):
        run(proc, f"{P5}/Utilities/expand.xsl", f"{P5}/Source/guidelines-en.xml", p5)
    if not os.path.exists(sub):
        run(proc, f"{P5}/Utilities/subset.xsl", p5, sub)
    compiled = os.path.join(OUT, "tei_all.compiled.odd")
    run(proc, f"{XSL}/odds/odd2odd.xsl", f"{P5}/Exemplars/tei_all.odd", compiled,
        {"defaultSource": "file://" + sub})
    run(proc, f"{XSL}/odds/odd2relax.xsl", compiled, os.path.join(OUT, "tei_all.rng"))
