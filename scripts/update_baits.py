#!/usr/bin/env python3
from __future__ import annotations
"""
Fetch Lulu'sTools Ocean Fishing spreadsheet server-side and generate data/baits.json.

This avoids browser CORS issues. GitHub Pages then loads the JSON from same-origin.
"""
import json, os, re
from datetime import datetime, timezone
from urllib.parse import quote
import urllib.request

SHEET_ID = os.environ.get("OF_SHEET_ID","1R0Nt8Ye7EAQtU8CXF1XRRj67iaFpUk1BXeDgt6abxsQ")
SHEETS = [s.strip() for s in os.environ.get("OF_SHEETS","Indigo Route,Ruby Route").split(",") if s.strip()]
OUT_PATH = os.environ.get("OF_OUT_PATH","data/baits.json")

ROUTE_RE = re.compile(r"^[BTRN][DSN]$")

def gviz_url(sheet:str)->str:
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:json&sheet={quote(sheet)}"

def fetch_text(url:str)->str:
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def parse_gviz(text:str)->dict:
    # google.visualization.Query.setResponse({...});
    m = re.search(r"setResponse\((.*)\);\s*$", text, flags=re.S)
    if not m:
        head = text[:400].replace("\n", "\\n")
        raise ValueError(f"gviz response format not recognized. head={head}")
    return json.loads(m.group(1))

def cell(c):
    if c is None: return None
    v = c.get("v", None)
    if isinstance(v, str): v = v.strip()
    return v

def norm(s)->str:
    return re.sub(r"\s+"," ", str(s or "").lower()).strip()

def is_route(v)->bool:
    return isinstance(v, str) and ROUTE_RE.fullmatch(v.strip()) is not None

def best_route_col(cols, rows)->int:
    for i,h in enumerate(cols):
        hn = norm(h)
        if hn=="route" or "route" in hn or "ルート" in str(h):
            return i
    counts = [0]*len(cols)
    for r in rows:
        cs = r.get("c", [])
        for i in range(len(cols)):
            v = cell(cs[i]) if i < len(cs) else None
            if is_route(v): counts[i]+=1
    best = max(range(len(cols)), key=lambda i: counts[i]) if cols else -1
    if best>=0 and counts[best]>0: return best
    raise ValueError("route column not found")

def find_cols(cols, pats):
    out=[]
    for i,h in enumerate(cols):
        hn = norm(h)
        for p in pats:
            if re.search(p, hn):
                out.append(i); break
    return out

def pick_route_name(cols, row):
    cs = row.get("c", [])
    s1c = find_cols(cols, [r"stop\s*1", r"1st", r"第一", r"①"])
    s2c = find_cols(cols, [r"stop\s*2", r"2nd", r"第二", r"②"])
    s3c = find_cols(cols, [r"stop\s*3", r"3rd", r"第三", r"③"])
    def first(idxs):
        for i in idxs:
            v = cell(cs[i]) if i < len(cs) else None
            if isinstance(v,str) and v.strip(): return v.strip()
        return None
    a,b,c = first(s1c), first(s2c), first(s3c)
    if a and b and c:
        return f"{a} → {b} → {c}"
    return None

def extract_baits(cols, row):
    cs = row.get("c", [])
    bait_cols = [i for i,h in enumerate(cols) if ("bait" in norm(h)) or ("餌" in str(h))]
    stop = {"stop1":None,"stop2":None,"stop3":None}
    bucket=[]
    for i in bait_cols:
        hn = norm(cols[i])
        v = cell(cs[i]) if i < len(cs) else None
        if not isinstance(v,str) or not v.strip(): continue
        v=v.strip()
        if re.search(r"stop\s*1|\b1\b|1st|第一|①", hn): stop["stop1"]=v
        elif re.search(r"stop\s*2|\b2\b|2nd|第二|②", hn): stop["stop2"]=v
        elif re.search(r"stop\s*3|\b3\b|3rd|第三|③", hn): stop["stop3"]=v
        else: bucket.append(v)
    for k in ("stop1","stop2","stop3"):
        if stop[k] is None and bucket:
            stop[k]=bucket.pop(0)
    return stop

def build_map(gviz:dict)->dict:
    t = gviz.get("table", {})
    cols = [c.get("label") or c.get("id") or "" for c in t.get("cols", [])]
    rows = t.get("rows", [])
    rcol = best_route_col(cols, rows)
    out={}
    for r in rows:
        cs = r.get("c", [])
        code = cell(cs[rcol]) if rcol < len(cs) else None
        if not is_route(code): continue
        code = code.strip()
        name = pick_route_name(cols, r)
        baits = extract_baits(cols, r)
        out[code] = {"name": name, "baits": baits}
    return out

def main():
    merged={}
    counts={}
    for sheet in SHEETS:
        gviz = parse_gviz(fetch_text(gviz_url(sheet)))
        m = build_map(gviz)
        counts[sheet]=len(m)
        merged.update(m)
    payload = {
        "_meta": {"updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "source": f"google_sheets:{SHEET_ID}",
                  "sheets": counts},
        "routes": merged
    }
    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(OUT_PATH,"w",encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT_PATH} ({len(merged)} routes).", counts)

if __name__=="__main__":
    main()
