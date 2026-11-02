#!/usr/bin/env python3
"""Build ocr/p0NN.lines.json from reviewed readings + geometry + Tesseract TSV."""
import os
import csv, json, sys
import numpy as np
from PIL import Image

ROOT = os.environ.get("GPURA_ITEM_DIR", ".")
W, H = 2374, 3495


def load_print(p, thr):
    a = np.asarray(Image.open(f"{ROOT}/images/{p}.png").convert("RGB")).astype(int)
    R, B = a[..., 0], a[..., 2]
    g = a.mean(2)
    return a, (g < thr) & ((R - B) >= 22)


def tsv_words(p):
    rows = list(csv.DictReader(open(f"{ROOT}/ocr/{p}.tess.tsv", encoding="utf-8"),
                               delimiter="\t", quoting=csv.QUOTE_NONE))
    out = []
    for r in rows:
        if r["level"] == "5" and r["text"].strip():
            x, y, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
            out.append((x, y, w, h, r["text"], float(r["conf"])))
    return out


def rect(b):
    x, y, w, h = b
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def union(bs):
    x0 = min(b[0] for b in bs); y0 = min(b[1] for b in bs)
    x1 = max(b[0] + b[2] for b in bs); y1 = max(b[1] + b[3] for b in bs)
    return [x0, y0, x1 - x0, y1 - y0]


def line_geom(prn, core, xlim=(60, 2330)):
    c0, c1 = core
    y0, y1 = c0 - 24, c1 + 26
    band = prn[y0:y1, xlim[0]:xlim[1]]
    cols = np.where(band.sum(0) > 2)[0]
    x0, x1 = xlim[0] + int(cols.min()), xlim[0] + int(cols.max())
    return [x0, y0, x1 - x0 + 1, y1 - y0], [[x0, c1], [x1, c1]]


def tess_for(words, bbox):
    x, y, w, h = bbox
    sel = [wd for wd in words if y <= wd[1] + wd[3] / 2 <= y + h and wd[0] + wd[2] > x - 20 and wd[0] < x + w + 20]
    sel.sort(key=lambda t: t[0])
    if not sel:
        return "", None
    return " ".join(t[4] for t in sel), round(sum(t[5] for t in sel) / len(sel) / 100, 3)


def find(text, sub, occ=1):
    i = -1
    for _ in range(occ):
        i = text.index(sub, i + 1)
    return i, i + len(sub)


def span_from_x(text, bbox, x0, x1):
    """Approximate character span under a horizontal extent, snapped to words."""
    lx, _, lw, _ = bbox
    n = len(text)
    s = int(round((max(x0, lx) - lx) / lw * n)); e = int(round((min(x1, lx + lw) - lx) / lw * n))
    s = max(0, min(s, n)); e = max(s, min(e, n))
    while s > 0 and text[s - 1] != " ":
        s -= 1
    while e < n and text[e] != " ":
        e += 1
    while s < e and text[s] == " ":
        s += 1
    return s, e


def flag(text, typ, sub=None, occ=1, span=None, **kw):
    s, e = span if span else find(text, sub, occ)
    d = {"type": typ, "start": s, "end": e}
    d.update(kw)
    return d


def ink_hand(a, b):
    x, y, w, h = b
    px = a[y:y + h, x:x + w].reshape(-1, 3)
    g = px.mean(1)
    sel = px[(g < 160) & ((px[:, 0] - px[:, 2]) < 15)]   # ignore brown printed ink under the stroke
    if len(sel) == 0:
        return "dark-ink"
    r, gg, bb = np.median(sel, 0)
    return "blue-ink" if len(sel) > 200 else "dark-ink"   # violet-blue ballpoint vs brown/black ink


# ---------------------------------------------------------------- p017
P017_BODY = [
 # (text, hyphen_end, [flag specs])
 ("അമേരിക്കൻ ഐക്യനാട്ടിലെ (യു. എസ്. ഏ.) ബഹുഭൂരിപക്ഷം ആളുകളും ഇ", True, []),
 ("ന്നു്, സ്വന്തം മാതൃഭാഷയെന്ന പോലെ തന്നെ ഇംഗ്ലീഷ് സംസാരിക്കുന്നവരാണു്.", False, []),
 ("എങ്കിലും അവരുടെ ഉച്ചാരണത്തിൽ പ്രകടമായ അനുനാസികത്വം ഉണ്ടു്. അവരു", True, []),
 ("ടെ ശൈലികളും കല്പനകളും ആംഗലേയരിൽ പലർക്കും മനസ്സിലാക്കാൻ പ്രയാസം.", False,
  [("unclear", "പലർക്കും", dict(cert="medium", note="ർ is a small dot-reph over ക്ക in this print; read as പലർക്കും"))]),
 ("ഭാഷയൊന്നു തന്നെ, എങ്കിലും വ്യത്യസ്തം. പല അമേരിക്കൻ ആശയങ്ങളും സ്ഥാ", True, []),
 ("പനങ്ങളും ഇംഗ്ലണ്ടിന്റെ ആശയങ്ങളും സ്ഥാപനങ്ങളും പോലെ തന്നെയാണു്;", False,
  [("unclear", "തന്നെയാണു്;", dict(cert="medium", note="final mark faint: ് and semicolon read from Tesseract shape + image"))]),
 ("എങ്കിലും വ്യത്യാസമുണ്ടു്. ഉദാഹരണത്തിനു് ഇംഗ്ലണ്ടിലെ പാർലമെന്റിനു തു", True, []),
 ("ല്യമാണു് യുണൈറ്റഡ് സ്റ്റേറ്റ്സിലെ കോൺഗ്രസ്. ബ്രിട്ടീഷ് കോമൺസ്", False, []),
 ("സഭ പോലെ അതു് ജനങ്ങളുടെ പ്രാതിനിധ്യം വഹിക്കുന്നു. ജനങ്ങളുടെ വോട്ടു്", False, []),
 ("കൊണ്ടു് അതിലെ അംഗങ്ങളെ തിരഞ്ഞെടുക്കുന്നു. അങ്ങനെ തിരഞ്ഞെടുക്കപ്പെ", True, []),
 ("ടുന്ന അംഗങ്ങൾ രാഷ്ട്രീയകക്ഷികളിൽ പെട്ടവരാണു താനും. എന്നാലും, കോൺ", True, []),
 ("ഗ്രസ്സിന്റെയും കോമൺസഭയുടെയും പ്രവർത്തനവിധങ്ങൾ തമ്മിൽ വലിയ വ്യ", True, []),
 ("ത്യാസം ഉണ്ടു്. ഒരു ഉദാഹരണം : അമേരിക്കൻ മന്ത്രിസഭയിലെ അംഗങ്ങൾക്കു്", False, []),
 ("കോൺഗ്രസ്സിൽ സംബന്ധിക്കുവാൻ അവകാശമില്ല. അമേരിക്കയിലെയും ബ്രി", True, []),
 ("ട്ടനിലെയും രാഷ്ട്രീയകക്ഷികളുടെ ലക്ഷ്യങ്ങൾ തന്നെ വളരെ വിഭിന്നമാണു്.", False, []),
 # paragraph 2
 ("യു. എസ്. ഏ യിലെ ആദ്യത്തെ അധിനിവേശകരിലധികവും ബ്രിട്ടീഷു", True, []),
 ("കാരായിരുന്നതു കൊണ്ടാണു് അവിടത്തെ ഭാഷ ഇംഗ്ലീഷായി തീർന്നതു്. അതേ", False,
  [("ink-over", "രുന്നതു കൊണ്ടാണു്", dict(hand="blue-ink", cert="high", note="reader's underline stroke runs through the upper half of these characters; text still legible"))]),
 ("കാരണം കൊണ്ടു തന്നെ അമേരിക്കയിലെ ആശയഗതികളും സ്ഥാപനമാതൃകകളും", False, []),
 ("ബ്രിട്ടന്റെതിനോടു് സാദൃശ്യമുള്ളതായിത്തീർന്നു. വ്യത്യാസം ഉണ്ടായതു് രണ്ടു കാര", True,
  [("unclear", "ബ്രിട്ടന്റെതിനോടു്", dict(cert="medium", note="printed with the short e-sign (െ) before ൻറ, i.e. ബ്രിട്ടന്റെതിനോടു്; the standard spelling would be ബ്രിട്ടന്റേതിനോടു് (long േ); transcribed as printed. Existing OCR's ബ്രിട്ടനെറതിനോടു് is the same glyphs in visual-order encoding"))]),
 ("ണത്താലാണു്. ഒന്നാമതു് മറ്റു പല രാജ്യക്കാരും യു. എസ്. ഏ യുടെ വളർച്ച", True,
  [("unclear", "വളർച്ച", dict(cert="medium", note="ർ printed as dot-reph above ച്ച"))]),
 ("യ്ക്കു് സഹായിച്ചിട്ടുണ്ടു്. സ്പെയിൻകാരും ഫ്രഞ്ചുകാരും ആയിരുന്നു വടക്കെ അമേ", True, []),
 ("രിക്കയിലെത്തിയ ആദ്യത്തെ അന്വേഷകസംഘങ്ങൾ. പതിനേഴും പതിനെ", True, []),
 ("ട്ടും ശതാബ്ദങ്ങളിൽ ആയിരക്കണക്കിനു് ആഫ്രിക്കൻ നീഗ്രോകളെ അമേരിക്ക", True, []),
 ("യിൽ അടിമകളായി കൊണ്ടു വന്നു. പത്തൊൻപതാം ശതകത്തിൽ യൂറോപ്പിൽ", False, []),
 ("നിന്നു് അമേരിക്കയിലേക്കു് പ്രവഹിച്ച അധിനിവേശകരിൽ ഐർലൻഡുകാർ,", False, []),
 ("ജർമൻകാർ, സ്കാൻഡിനേവിയക്കാർ, ഇറ്റാലിയൻമാർ, സ്ലാവുകൾ എന്നിവ", True,
  [("damage", "ജ", dict(cert="medium", note="left margin crease/tear partly obscures the first character")),
   ("unclear", "ജർമൻകാർ", dict(cert="medium", note="single മ (ജർമൻ) as printed; existing OCR has ജർമ്മൻകാർ"))]),
 ("രെല്ലാം ഉൾപ്പെട്ടിരുന്നു. അവരെല്ലാം തങ്ങളുടെ മുദ്രകൾ അവിടെ പതി", True, []),
]

P018_LINES = [
 # para 1 (continues p017)
 ("p1", "പ്പിച്ചിട്ടുണ്ടു്. സുപരിചിതവും ശ്രദ്ധേയവും ആയ രണ്ടു് ഉദാഹരണം പറയാം.", False, []),
 ("p1", "കാലിഫോർണിയയിലെ ഏറ്റവും വലിയ രണ്ടു നഗരങ്ങൾക്കു് ഇപ്പോഴും സ്പാ", True, []),
 ("p1", "നിഷ് പേരാണു്. മധ്യപശ്ചിമദേശത്തെ ഒരു വലിയ പട്ടണത്തിന്റെ പേരു്", False, []),
 ("p1", "സെന്റു് ലൂയിസ് എന്നും.", False, []),
 # para 2
 ("p2", "അമേരിക്കൻ സംസ്കാരം ആംഗലസംസ്കാരത്തിന്റെ വെറും പകർപ്പല്ലാതിരി", True, []),
 ("p2", "ക്കുന്നതിന്റെ രണ്ടാമത്തെ കാരണം യു. എസ്. ഏ. യുടെ ഭൂമിശാസ്ത്രപരമായ സ", True,
  [("ink-over", "രണ്ടാമത്തെ കാരണം", dict(hand="blue-ink", cert="high", note="underline stroke from the line above is drawn through these words; still legible"))]),
 ("p2", "വിശേഷതയാണു്. യൂറോപ്പിൽ നിന്നു വന്ന അധിനിവേശകരുടെയും അവരുടെ", False, []),
 ("p2", "പരമ്പരകളുടെയും ഭാഗധേയങ്ങൾ രൂപപ്പെടുത്തിയതും കുരുപ്പിടിപ്പിച്ചതും അവർ", False,
  [("unclear", "കുരുപ്പിടിപ്പിച്ചതും", dict(cert="medium", note="first syllable printed as ക with a detached colon-like mark; read as കു (cf. existing OCR); standard word would be കരുപ്പിടിപ്പിച്ചതും"))]),
 ("p2", "പാർപ്പു് ഉറപ്പിച്ച ഭൂമിയാണു്. തങ്ങൾ എവിടെ താമസിക്കണമെന്നും ഏതു", False,
  [("unclear", "പാർപ്പു്", dict(cert="medium", note="u-sign under പ്പ is faint; could be പാർപ്പ്"))]),
 ("p2", "ജീവിതവൃത്തി കൈക്കൊള്ളണമെന്നും അവരെക്കൊണ്ടു് തീരുമാനമെടുപ്പിച്ചതു", False,
  [("unclear", "തീരുമാനമെടുപ്പിച്ചതു", dict(cert="medium", note="line-final ് (if any) lost in the stained right margin"))]),
 ("p2", "നാട്ടിന്റെ ഭൂപ്രകൃതിയും ശീതോഷ്ണാവസ്ഥയും ആണു്. ചില പ്രദേശങ്ങൾ അവ", True, []),
 ("p2", "രെ ആകർഷിച്ചു. ചിലേടങ്ങൾ അവർക്കു് ഇഷ്ടപ്പെട്ടില്ല. ജീവിക്കാൻ തിര", True,
  [("damage", "തിര", dict(cert="medium", note="final ര partly lost at stained right edge"))]),
 ("p2", "ഞ്ഞെടുത്ത പ്രദേശങ്ങൾ, പുതിയ ജീവിതചിന്തകളും ജീവിതശീലങ്ങളും അ", True, []),
 ("p2", "വർക്കു് നൽകി. അവ അധിനിവേശകരുടെ ജീവിതവീക്ഷണം തന്നെ പരിവ", True, []),
 ("p2", "ർത്തനം ചെയ്തു. ഇംഗ്ലീഷ്കാരനെയും ജർമൻകാരനെയും ഇറ്റാലിയനെയും അ", True,
  [("unclear", "ർത്തനം", dict(cert="medium", note="line begins with the dot-reph of പരിവർത്തനം, split across the line break"))]),
 ("p2", "യർലണ്ടുകാരനെയും റഷ്യക്കാരനെയും അമേരിക്കക്കാരാക്കി മാറ്റിയതു് ഐ", True, []),
 ("p2", "ക്യനാടിന്റെ ഭൂമിശാസ്ത്രമാണു്. അമേരിക്കൻ ചരിത്രത്തിന്റെ പശ്ചാത്തലം", False, []),
 ("p2", "അമേരിക്കൻ ഭൂമിശാസ്ത്രമത്രെ.", False, []),
 # heading
 ("hd", "1. വലിപ്പം, ബാഹ്യപ്രകൃതി, ശീതോഷ്ണാവസ്ഥ,", False, []),
 ("hd", "പ്രകൃതിവിഭവങ്ങൾ", False, []),
 # para 3
 ("p3", "അമേരിക്കൻ ഭൂമിശാസ്ത്രത്തിന്റെ ശ്രദ്ധേയമായ പ്രത്യേകത അതിന്റെ വി", True, []),
 ("p3", "സ്തൃതിയാണു്. വിശേഷിച്ചും, കുടിയേറ്റത്തിനു വന്നവരുടെ ജന്മഭൂമികളുടെ", False, []),
 ("p3", "വലിപ്പവുമായി താരതമ്യപ്പെടുത്തുമ്പോൾ. അലാസ്കയും ഹാവായിയും ഉൾ", True, []),
 ("p3", "പ്പെടെ യു. എസ്. ഏ യുടെ വിസ്താരം 3554000 ചതുരശ്രമൈലാണു്. റഷ്യ", False,
  [("unclear", "3554000", dict(cert="medium", note="fifth digit is a broken 0 (left side of the bowl missing); Tesseract read 9")),
   ]),
 ("p3", "ഒഴികെയുള്ള യൂറോപ്പിന്റെ വിസ്തൃതി ഏതാണ്ടു് ഇതിൽ പകുതിയേ വരൂ.", False, []),
 ("p3", "ടെക്സാസ് എന്ന ഒറ്റ സ്റ്റേറ്റിനു് ഇംഗ്ലണ്ടിന്റെ അഞ്ചിരട്ടി വലിപ്പമുണ്ടു്. യു.", False,
  [("ink-over", "ഇംഗ്ലണ്ടിന്റെ അഞ്ചിരട്ടി", dict(hand="blue-ink", cert="medium", note="ink stroke drawn over the upper part of these words; reading supported by context and existing OCR"))]),
 ("p3", "എസ്. വൻകരയുടെ കിഴക്കും പടിഞ്ഞാറും കിടക്കുന്ന കടൽതീരത്തിനു് 1500", False,
  [("ink-over", "വൻകരയുടെ കിഴക്കും", dict(hand="blue-ink", cert="high", note="the sloping underline of the previous line crosses these words"))]),
 ("p3", "മൈൽ വീതം നീളമുണ്ടു്. അതിന്റെ കനേഡിയൻ അതിർത്തിയുടെ നീളം 3,000", False, []),
 ("p3", "മൈൽ വരും. എന്നാൽ ഒരു രാജ്യത്തിന്റെ വിസ്താരം കൊണ്ടു് മാത്രം ആളുകൾ", False,
  [("damage", "ആളുകൾ", dict(cert="medium", note="torn right margin; final ൾ partly lost"))]),
 ("p3", "ആകർഷിക്കപ്പെടുകയില്ല. ആസ്ത്രേലിയയുടെ വിസ്തൃതി 3000000 ചതു", True,
  [("damage", "ചതു", dict(cert="medium", note="torn right margin; തു partly lost")),
   ("unclear", "ആസ്ത്രേലിയയുടെ", dict(cert="medium", note="സ്ത്ര ligature as in ഭൂമിശാസ്ത്രം; existing OCR has ആസ്ട്രേലിയയുടെ"))]),
 ("p3", "രശ്രമൈലാണു്. എന്നാൽ 11000000 മാത്രമാണു് അവിടത്തെ ജനസംഖ്യ. അത", True,
  [("damage", "അത", dict(cert="low", note="at the torn edge; a following ാ (അതാ-യതു്) may have been lost — print shows only അത"))]),
 ("p3", "യതു് യു. എസ്. ഏ. യിലെ ജനസംഖ്യയുടെ ആറു ശതമാനം. യു. എസ്. ഏ. യു", True,
  [("damage", "യു", dict(cert="medium", note="last characters at torn edge"))]),
 ("p3", "ടെ സമശീതോഷ്ണവും എന്നാൽ വൈവിധ്യപൂർണവും ആയ കാലാവസ്ഥയും സമ്പ", True,
  [("damage", "സമ്പ", dict(cert="medium", note="subscript of മ്പ partly lost at torn edge")),
   ("unclear", "വൈവിധ്യപൂർണവും", dict(cert="medium", note="ണ vs ണ്ണ not fully certain"))]),
 ("p3", "ന്നമായ പ്രകൃതിവിഭവങ്ങളുമാണു് കുടിയേറ്റക്കാരെ അങ്ങോട്ടേക്കാകർഷിച്ചതു്", False, []),
 ("p3", "യു. എസ്. ഏ. യുടെ വികസനത്തിനും വളർച്ചയ്ക്കും സഹായകമായി നിന്ന ഘ", True, []),
 ("p3", "ടകങ്ങളും ഇവ തന്നെയായിരുന്നു.", False, []),
]


COMMON_NOTES = [
    "Coordinates are pixels in the full-resolution scan (2374 x 3495), origin top-left; bbox = [x, y, w, h]; polygons are rectangles unless stated.",
    "Encoding: the 1971 reformed-script glyphs NTA (drawn ൻറ) and TTA (drawn ററ) are encoded with the standard atomic-conjunct sequences NTA = ന്റ (U+0D28 U+0D4D U+0D31) and TTA = റ്റ (U+0D31 U+0D4D U+0D31). No chillu-N + RRA or bare RRA RRA sequences are used for them.",
    "Standalone chillus are encoded with the atomic chillu characters (ൻ U+0D7B, ർ U+0D7C, ൽ U+0D7D, ൾ U+0D7E, ൺ U+0D7A). The dot-reph form of ർ that this print uses before a consonant (e.g. പലർക്കും, വളർച്ച, അതിർത്തി) is also encoded as atomic ർ (U+0D7C), not U+0D4E DOT REPH.",
    "Samvruthokaram: the print shows a u-sign plus a small circle (chandrakkala) at word end; encoded as printed with U+0D41 U+0D4D (e.g. ഉണ്ടു്, ആണു്). Where the circle follows a bare consonant with no u-sign (എസ്, ഇംഗ്ലീഷ്, സംസ്കാരം-type visible virama inside words like ടെക്സാസ്, അലാസ്കയും, സ്തൃതി), it is encoded as plain virama U+0D4D. Words printed without the circle (e.g. കൊണ്ടു, നിന്നു, പേരു്) are kept as printed; no samvruthokaram is added or removed.",
    "Visible-virama spellings inside words (സ്°ക, സ്°ത, ബ്°ദ) are encoded as the ordinary conjunct (സ്ക, സ്ത, ബ്ദ); the visible virama is a glyph choice of the font.",
    "Diplomatic transcription: wording and spelling are as printed (e.g. ബ്രിട്ടന്റെതിനോടു്, ജർമൻകാർ, ആസ്ത്രേലിയ, ഇംഗ്ലീഷ്കാരനെയും); nothing modernised. Abbreviations (യു. എസ്. ഏ.) and spacing around punctuation are as printed.",
    "hyphen_end = true marks a word split across the line end; the print uses no hyphen. When joining lines for TEI, concatenate without a space after a hyphen_end line.",
    "Flag offsets (start/end) are Python string indices (Unicode code points) into `text`, end-exclusive. Underline flag spans were derived from the underline's x-extent mapped proportionally onto the line and snapped outward to word boundaries, so they are approximate (±1 word).",
    "text_tesseract/conf come from Tesseract 5.3.4 (tessdata_best) words whose box centre falls in the line bbox; conf is the mean word confidence / 100. Tesseract text keeps its own encoding (ZWJ/ZWNJ, chillu+ZWJ, ൻ+െ+റ split etc.).",
    "Ink colour (`hand`) of underlines was classified automatically from pixel colour: 'blue-ink' = the blue/violet ballpoint used for most underlines, CMS and the p019 notes; 'dark-ink' = brown/black strokes. Treat as indicative.",
    "The `text` readings are a careful model-made reading from zoomed line images, not human-verified ground truth.",
]


def ul_line_index(cores, ub):
    cy = ub[1] + ub[3] / 2
    best = None
    for i, (c0, c1) in enumerate(cores):
        if c0 - 5 <= cy:   # line whose core starts above underline centre
            best = i
    return best


def build_body(page, canvas, printed, cores_file, thr, layout, extras, underlines, notes, xlim=(60, 2330)):
    a, prn = load_print(page, thr)
    cores = eval(open(cores_file).read())
    words = tsv_words(page)
    regions = []
    line_objs = []   # (core_index, line dict)
    rid = 0
    order = 0
    for reg in layout:
        rid += 1
        r = {"id": f"{page}_r{rid:02d}", "type": reg["type"], "production": "printed", "orientation": 0}
        lines = []
        for k, (ci, text, hy, fl) in enumerate(reg["lines"]):
            if ci is None:
                bbox = reg["bbox"]; base = [[bbox[0], bbox[1] + bbox[3] - 4], [bbox[0] + bbox[2], bbox[1] + bbox[3] - 4]]
            else:
                bbox, base = line_geom(prn, cores[ci], xlim)
            tt, cf = tess_for(words, bbox)
            flags = []
            for typ, sub, kw in fl:
                occ = text.count(sub) if typ == "damage" and not kw.get("note", "").startswith("left") else 1
                flags.append(flag(text, typ, sub, occ=occ, **kw))
            ln = {"id": f"{r['id']}_l{k + 1:03d}", "bbox": bbox, "baseline": base,
                  "text_tesseract": tt, "conf": cf, "text": text, "hyphen_end": hy, "flags": flags}
            lines.append(ln)
            if ci is not None:
                line_objs.append((ci, ln))
        r["bbox"] = union([l["bbox"] for l in lines]) if lines else reg["bbox"]
        r["polygon"] = rect(r["bbox"])
        order += 1
        r["reading_order"] = order
        r["lines"] = lines
        regions.append(r)
    # extras: marginalia etc.
    for ex in extras:
        rid += 1
        r = {"id": f"{page}_r{rid:02d}"}
        r.update({k: v for k, v in ex.items() if k != "lines"})
        r.setdefault("orientation", 0)
        r["polygon"] = rect(r["bbox"])
        r.setdefault("reading_order", None)
        r["lines"] = []
        for k, ln in enumerate(ex.get("lines", [])):
            d = {"id": f"{r['id']}_l{k + 1:03d}", "baseline": [[ln["bbox"][0], ln["bbox"][1] + ln["bbox"][3]], [ln["bbox"][0] + ln["bbox"][2], ln["bbox"][1] + ln["bbox"][3]]],
                 "text_tesseract": ln.get("text_tesseract", ""), "conf": ln.get("conf"), "hyphen_end": False}
            d.update(ln)
            d.setdefault("flags", [])
            r["lines"].append(d)
        regions.append(r)
    # underlines
    by_core = {ci: ln for ci, ln in line_objs}
    for ub in underlines:
        bb = ub[:4]
        hand = ub[4] if len(ub) > 4 else ink_hand(a, bb)
        rid += 1
        ci = ul_line_index(cores, bb)
        target = by_core.get(ci)
        note = "reader underline"
        if target is not None:
            s, e = span_from_x(target["text"], target["bbox"], bb[0], bb[0] + bb[2])
            target["flags"].append({"type": "underline", "start": s, "end": e, "hand": hand, "cert": "high",
                                    "note": f"underline graphic {page}_r{rid:02d}; span approximate"})
            note = f"reader underline under line {target['id']}"
        regions.append({"id": f"{page}_r{rid:02d}", "type": "annotation-graphic", "production": "handwritten",
                        "orientation": 0, "bbox": list(map(int, bb)), "polygon": rect(list(map(int, bb))), "reading_order": None,
                        "hand": hand, "note": note, "lines": []})
    for ln in [l for r in regions for l in r["lines"]]:
        ln["flags"].sort(key=lambda f: (f["start"], f["end"]))
    return {"page": page, "canvas": canvas, "printed_page": printed, "width": W, "height": H,
            "regions": regions, "notes": COMMON_NOTES + notes}


def p017():
    L = [(i, t, h, f) for i, (t, h, f) in enumerate(P017_BODY)]
    layout = [
        {"type": "page-number", "bbox": [2073, 332, 26, 106], "lines": [(None, "1", False, [])]},
        {"type": "heading", "bbox": [920, 690, 380, 140], "lines": [(None, "ഭൂപ്രകൃതി", False, [])]},
        {"type": "paragraph", "lines": L[:15]},
        {"type": "paragraph", "lines": L[15:]},
    ]
    extras = [
        {"type": "marginalia", "production": "handwritten", "bbox": [1560, 668, 100, 112], "hand": "blue-ink",
         "lines": [{"bbox": [1560, 668, 100, 112], "text": "CMS", "text_tesseract": "", "conf": None,
                    "flags": [{"type": "unclear", "start": 0, "end": 3, "hand": "blue-ink", "cert": "medium",
                               "note": "reader's handwritten initials/letters right of the title; letter forms read as C-M-S (last letter could be a 3 or a looped S)"}]}]},
        {"type": "marginalia", "production": "handwritten", "bbox": [800, 2638, 56, 82], "hand": "blue-ink",
         "lines": [{"bbox": [800, 2638, 56, 82], "text": "1", "text_tesseract": "", "conf": None,
                    "flags": [{"type": "unclear", "start": 0, "end": 1, "hand": "blue-ink", "cert": "medium",
                               "note": "circled numeral written between ഒന്നാമതു് and മറ്റു (line p017_r04_l005), marking 'firstly'"}]}]},
        {"type": "annotation-graphic", "production": "handwritten", "bbox": [2000, 3160, 190, 20], "hand": "dark-ink",
         "note": "short stray stroke right of the text block, not under any text"},
        {"type": "damage", "production": "none", "bbox": [40, 2950, 140, 545],
         "note": "vertical crease/tear along the left margin in the lower part of the page; touches the first character of p017_r04_l011"},
    ]
    underlines = [
        [1118, 1648, 919, 17], [270, 1708, 1237, 28], [400, 2286, 170, 24, "dark-ink"],
        [616, 2390, 1437, 53], [259, 2471, 1858, 47], [210, 2553, 1800, 34], [214, 2640, 1143, 51],
        [880, 2815, 1178, 38], [243, 2886, 1255, 26],
    ]
    notes = ["Paragraph 2 last line ends mid-word (പതി-) and continues on p018 line p018_r03_l001 (പ്പിച്ചിട്ടുണ്ടു്).",
             "Several small dark dots near the start of paragraph 2 (around x 300-350, y 2320-2340) are reader marks/soiling and are not recorded as regions.",
             "Underline detection was automatic (colour + shape) and then checked by eye; a few very faint or short strokes may be missing."]
    return build_body("p017", 17, "1", "p017_cores.txt", 115, layout, extras, underlines, notes, xlim=(70, 2240))


def p018():
    groups = {}
    for i, (g, t, h, f) in enumerate(P018_LINES):
        groups.setdefault(g, []).append((i + 1, t, h, f))   # core 0 is the running head
    layout = [
        {"type": "page-number", "bbox": [241, 173, 29, 42], "lines": [(None, "2", False, [])]},
        {"type": "header", "bbox": [769, 178, 1024, 59], "lines": [(None, "അമേരിക്കൻ ഐക്യനാടിന്റെ ചരിത്രം", False, [])]},
        {"type": "paragraph", "lines": groups["p1"]},
        {"type": "paragraph", "lines": groups["p2"]},
        {"type": "heading", "lines": groups["hd"]},
        {"type": "paragraph", "lines": groups["p3"]},
    ]
    extras = [
        {"type": "annotation-graphic", "production": "handwritten", "bbox": [1800, 2265, 175, 40], "hand": "blue-ink",
         "note": "short curved underline under ഹാവായിയും (p018_r06_l003)"},
        {"type": "annotation-graphic", "production": "handwritten", "bbox": [210, 3150, 580, 210], "hand": "dark-ink",
         "note": "thin curved arc drawn across the starts of the last three lines (pencil or fine ink); text beneath is legible"},
        {"type": "damage", "production": "none", "bbox": [2240, 0, 134, 1300],
         "note": "brown staining / wear along the right edge near the top; line-final characters remain legible except as flagged"},
        {"type": "damage", "production": "none", "bbox": [2290, 2700, 84, 795],
         "note": "torn/stained right margin from the ആളുകൾ line (p018_r06_l009) to the bottom; some line-final characters partly lost (see damage flags)"},
    ]
    underlines = [
        [614, 744, 1058, 19], [420, 800, 384, 25], [923, 800, 918, 18], [339, 909, 299, 13],
        [752, 1532, 899, 32], [1640, 1553, 441, 16], [379, 1628, 1099, 16],
        [461, 1728, 224, 10], [765, 1728, 531, 10], [1300, 1716, 750, 16, "blue-ink"], [442, 1786, 486, 18],
        [574, 2103, 1531, 52], [350, 2210, 204, 12], [408, 2512, 892, 57], [1464, 2512, 654, 35],
    ]
    # add the ഹാവായിയും underline as a flag too
    d = build_body("p018", 18, "2", "p018_cores.txt", 135, layout, extras, underlines,
                   ["Line p018_r03_l001 continues the word പതി- from p017 (p017_r04_l012).",
                    "Running head reads ഐക്യനാടിന്റെ (printed ഐക്യനാടിൻറെ); the existing Gpura OCR's ഐക്യനാടുകളുടെ is a substitution.",
                    "Damage region boxes are approximate (drawn by eye from zoomed crops).",
                    "Underline detection was automatic (colour + shape) and then checked by eye; a few very faint or short strokes may be missing; underline [1300,1716,750,16] (under ചരിത്രത്തിന്റെ പശ്ചാ-) was added by eye."], xlim=(225, 2320))
    for r in d["regions"]:
        for l in r["lines"]:
            if l["id"] == "p018_r06_l003":
                s, e = find(l["text"], "ഹാവായിയും")
                l["flags"].append({"type": "underline", "start": s, "end": e, "hand": "blue-ink", "cert": "high", "note": "underline graphic p018_r07; span approximate"})
                l["flags"].sort(key=lambda f: (f["start"], f["end"]))
    return d


def rot_line(lid, bbox, text, tt="", conf=None, flags=None, **extra):
    x, y, w, h = bbox
    bx = x + int(w * 0.8)
    d = {"id": lid, "bbox": bbox, "polygon": rect(bbox),
         "baseline": [[bx, y + h], [bx, y]],   # text runs bottom-to-top
         "text_tesseract": tt, "conf": conf, "text": text, "hyphen_end": False, "flags": flags or []}
    d.update(extra)
    return d


def p019():
    page = "p019"
    words = tsv_words(page)
    rot = json.load(open(f"{ROOT}/ocr/p019.rotated.json", encoding="utf-8"))
    def rtt(name):
        ws = rot[name]["words"]
        if not ws:
            return "", None
        return " ".join(w["text"] for w in ws), round(sum(w["conf"] for w in ws) / len(ws) / 100, 3)
    regs = []
    def R(typ, prod, bbox, orient, ro, lines=(), **kw):
        rid = f"{page}_r{len(regs) + 1:02d}"
        d = {"id": rid, "type": typ, "production": prod, "orientation": orient, "bbox": bbox,
             "polygon": rect(bbox), "reading_order": ro}
        d.update(kw)
        d["lines"] = [dict(l, id=f"{rid}_l{i + 1:03d}") for i, l in enumerate(lines)]
        regs.append(d)
        return d
    def up_line(bbox, text, flags=None):
        tt, cf = tess_for(words, bbox)
        return {"bbox": bbox, "baseline": [[bbox[0], bbox[1] + bbox[3] - 6], [bbox[0] + bbox[2], bbox[1] + bbox[3] - 6]],
                "text_tesseract": tt, "conf": cf, "text": text, "hyphen_end": False, "flags": flags or []}
    R("header", "printed", [1086, 261, 172, 63], 0, 1,
      [up_line([1086, 261, 172, 63], "ഭൂപ്രകൃതി", [{"type": "unclear", "start": 0, "end": 9, "cert": "medium",
        "note": "faint print, partly overwritten by the handwritten 'Trueman' stroke; existing OCR gives പ്രകൃതി (drops ഭൂ)"}])])
    R("page-number", "printed", [2203, 259, 35, 39], 0, 2, [up_line([2203, 259, 35, 39], "3")])
    R("image", "printed", [183, 386, 1937, 3015], 90, 3,
      note="relief map of the USA printed rotated 90 deg (north toward the left edge of the page; read upright by rotating the page 90 deg clockwise), inside a ruled frame; elevation shading, rivers, state/region boundaries and place labels. Polygon = frame rectangle.")
    cap_tt, cap_cf = rtt("caption")
    R("caption", "printed", [2160, 1395, 72, 1110], 90, 4,
      [rot_line(None, [2160, 1395, 72, 1110], "അമേരിക്കൻ ഐക്യനാടിന്റെ ഭൂപ്രകൃതി", cap_tt, cap_cf)],
      note="caption outside the right edge of the map frame; text runs bottom-to-top")
    leg_tt, leg_cf = rtt("legend")
    leg = R("legend", "printed", [1855, 1140, 240, 870], 90, 5, [
        rot_line(None, [1860, 1150, 88, 650], "6000 അ. മുകളിൽ", leg_tt, leg_cf,
                 [{"type": "unclear", "start": 0, "end": 1, "cert": "low",
                   "note": "first digit faint/broken; looks most like 6 but could be 5 or 8; Tesseract gave nothing usable. അ. = abbreviation of അടി (feet)."}]),
        rot_line(None, [1955, 1265, 62, 535], "3000 അ. ,,", "", None,
                 [{"type": "unclear", "start": 8, "end": 10, "cert": "medium", "note": "ditto marks (〃) under മുകളിൽ, transcribed as two commas"}]),
        rot_line(None, [2025, 1265, 62, 535], "1200 അ. ,,", "", None,
                 [{"type": "unclear", "start": 8, "end": 10, "cert": "medium", "note": "ditto marks (〃) under മുകളിൽ, transcribed as two commas"}]),
    ], note="three elevation bands, each with a shading swatch (swatches at about y 1800-2000, toward the page bottom = left of the text when upright); Tesseract output for the whole legend is in the line-1 text_tesseract; it is junk")
    labels = [
        ([1200, 1544, 60, 430], "സെന്റ് ലൂയിസ്", "medium", "St. Louis; NTA glyph encoded ന്റ"),
        ([880, 1524, 80, 360], "ചിക്കാഗോ", "medium", "Chicago"),
        ([745, 484, 70, 340], "", "low", "probably Boston (ബോസ്റ്റൺ?) — too faint to transcribe reliably"),
        ([890, 624, 60, 240], "", "low", "probably New York (…യോർക്ക്?) — too faint to transcribe reliably"),
        ([220, 3224, 260, 160], "", "low", "label near the lower-left (= north-west when upright), probably കൊളംബിയ (Columbia river); diagonal; not transcribed"),
        ([600, 2434, 960, 320], "", "low", "curved label along the Rocky Mountains band (probably റോക്കി പർവ്വതം/…), on a curved ribbon; illegible"),
        ([1460, 1714, 190, 320], "", "low", "two labels near the Ohio / Wabash rivers; illegible"),
        ([1250, 1044, 400, 550], "", "low", "diagonal labels along the Appalachians (probably അപ്പലേച്ചിയൻ …); illegible"),
    ]
    for bb, text, cert, note in labels:
        fl = [] if text else []
        if text:
            fl = [{"type": "unclear", "start": 0, "end": len(text), "cert": cert, "note": note}]
        else:
            fl = [{"type": "unclear", "start": 0, "end": 0, "cert": "low", "note": note}]
        R("map-label", "printed", bb, 90, None, [rot_line(None, bb, text, "", None, fl)], note=note)
    R("marginalia", "handwritten", [920, 15, 1170, 240], 0, None,
      [{"bbox": [920, 15, 1170, 240], "baseline": [[930, 240], [2080, 110]], "text_tesseract": "", "conf": None,
        "text": "Trueman Doctrine", "hyphen_end": False,
        "flags": [{"type": "unclear", "start": 0, "end": 7, "hand": "blue-ink", "cert": "medium",
                   "note": "first word read as 'Trueman' (= Truman, misspelt); the existing OCR's 'Freeman' is possible from the letter shapes but the initial looks like a T with a long cross-bar"},
                  {"type": "unclear", "start": 8, "end": 16, "hand": "blue-ink", "cert": "medium",
                   "note": "'Doctrine' with the i undotted/merged; written on a rising slant"}]}],
      hand="blue-ink", note="reader's blue-ink handwriting across the top, slanting upward to the right")
    R("marginalia", "handwritten", [960, 250, 535, 190], 0, None,
      [{"bbox": [960, 250, 535, 190], "baseline": [[965, 435], [1490, 300]], "text_tesseract": "", "conf": None,
        "text": "Kennedy.", "hyphen_end": False,
        "flags": [{"type": "unclear", "start": 7, "end": 8, "hand": "blue-ink", "cert": "low", "note": "trailing dot may be a pen mark"}]}],
      hand="blue-ink", note="written just below the printed running head ഭൂപ്രകൃതി, slanting upward")
    R("annotation-graphic", "handwritten", [190, 1835, 1870, 860], 0, None, hand="blue-ink",
      note="blue-ink tracing along the map's (Gulf/Atlantic) coastline; bbox approximate (colour mask percentiles)")
    R("annotation-graphic", "handwritten", [2050, 3150, 324, 345], 0, None, hand="dark-ink",
      note="dark marks in the bottom-right corner outside the frame; origin uncertain (ink marks or soiling)")
    notes = [
        "Orientation convention: orientation 90 = the region must be rotated 90 deg clockwise to read upright (PAGE-XML @orientation semantics); on the page the text runs bottom-to-top. Rotated-region baselines run from the larger y (start of text) to the smaller y.",
        "Caption and legend were OCR'd from crops rotated 90 deg clockwise with Pillow after light binarisation; word boxes were mapped back to page coordinates (ocr/p019.rotated.json).",
        "FOOTNOTE CHECK: there is no footnote on this page. Apart from the running head, page number, map, its labels, legend and caption, the only text-like marks are the reader's handwriting and show-through (mirror-image text from the other side of the leaf, visible especially in the band y 180-470 under the handwriting). The phrase പ്രസിദ്ധീകരണത്തിൻ്റെ ഭാഗമായ in the existing Gpura OCR does not occur on the page and appears to be a hallucination.",
        "The existing Gpura OCR for this page also merges the running head with the handwriting (Freeman Doctrow / പ്രകൃതി / Kennedy.) and replaces the map with a prose description.",
        "Map labels: only the clearly legible ones are transcribed; the others are listed as map-label regions with empty text and an 'unclear' flag (start=end=0) whose note gives a cautious identification. Many small labels (state names, rivers) were not inventoried at all.",
        "Show-through is not recorded as a region.",
    ]
    return {"page": page, "canvas": 19, "printed_page": "3", "width": W, "height": H, "regions": regs,
            "notes": COMMON_NOTES + notes}


if __name__ == "__main__":
    for fn in (p017, p018, p019):
        d = fn()
        for r in d["regions"]:
            for l in r["lines"]:
                for f in l["flags"]:
                    assert 0 <= f["start"] <= f["end"] <= len(l["text"]), (l["id"], f)
        json.dump(d, open(f"{ROOT}/ocr/{d['page']}.lines.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        nl = sum(len(r["lines"]) for r in d["regions"])
        print(d["page"], len(d["regions"]), "regions", nl, "lines")
