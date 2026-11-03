#!/usr/bin/env python3
"""Sarvam Document AI "Parse" (Sarvam Vision) on page images, one job per image.

    python3 pipeline/tools/sarvam_parse.py OUT_DIR page1.jpg [page2.jpg ...] [--lang ml-IN] [--format json]

Reads SARVAM_API_KEY from the environment or from .env in the repository root (never printed).
Flow (docs.sarvam.ai, Document Intelligence): POST /doc-ai/v1/job/parse (multipart: file, language,
output_format) -> poll GET /doc-ai/v1/job/<id>/status -> GET /doc-ai/v1/job/<id>/download-url -> ZIP.
Each result is unpacked to OUT_DIR/<image stem>/ with a timings.json beside it.
"""
import argparse
import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
API = "https://api.sarvam.ai/doc-ai/v1/job"


def api_key():
    key = os.environ.get("SARVAM_API_KEY")
    env = REPO / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SARVAM_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("SARVAM_API_KEY not set (add it to .env)")
    return key


def parse(img, out, key, lang, fmt):
    h = {"api-subscription-key": key}
    t0 = time.time()
    with open(img, "rb") as f:
        r = requests.post(f"{API}/parse", headers=h, timeout=120,
                          files={"file": (img.name, f, "image/jpeg")}, data={"language": lang, "output_format": fmt})
    if r.status_code >= 400:
        raise SystemExit(f"{img.name}: submit failed HTTP {r.status_code}: {r.text[:300]}")
    job = r.json()
    jid = job["job_id"]
    while True:
        time.sleep(4)
        st = requests.get(f"{API}/{jid}/status", headers=h, timeout=60).json()
        if st.get("status") in ("completed", "partially_completed", "failed", "rejected"):
            break
    t1 = time.time()
    rec = {"image": img.name, "job_id": jid, "status": st.get("status"), "usage": st.get("usage"),
           "seconds_to_result": round(t1 - t0, 1)}
    if st["status"] in ("completed", "partially_completed"):
        dl = requests.get(f"{API}/{jid}/download-url", headers=h, timeout=60).json()
        z = requests.get(dl["url"], timeout=120).content
        zipfile.ZipFile(io.BytesIO(z)).extractall(out)
    else:
        rec["detail"] = st
    (out / "timings.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--lang", default="ml-IN")
    ap.add_argument("--format", default="json", choices=["json", "md", "html"])
    a = ap.parse_args()
    key = api_key()
    for p in map(Path, a.images):
        out = Path(a.out) / p.stem
        out.mkdir(parents=True, exist_ok=True)
        rec = parse(p, out, key, a.lang, a.format)
        print(f"  {p.name}: {rec['status']} in {rec['seconds_to_result']} s  usage={rec.get('usage')}", flush=True)


if __name__ == "__main__":
    main()
