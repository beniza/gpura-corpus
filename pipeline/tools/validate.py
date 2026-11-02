import sys
from lxml import etree
xsd, files = sys.argv[1], sys.argv[2:]
s = etree.XMLSchema(etree.parse(xsd))
for f in files:
    ok = s.validate(etree.parse(f))
    print(("PASS" if ok else "FAIL"), f)
    for e in s.error_log: print("   ", e.line, e.message)
