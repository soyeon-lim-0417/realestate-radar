"""(선택) 한국부동산원 R-ONE 주간 아파트 가격지수를 받아 data/rone.json 에 저장.

- 인증키: 환경변수 RONE_KEY (R-ONE 누리집 > 오픈API 에서 발급)
- 키가 없으면 조용히 건너뛰어요. 사이트는 실거래가만으로도 동작해요.
"""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"


def fetch_table(key: str, statbl_id: str, cycle: str = "WK"):
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "KEY": key, "Type": "json", "STATBL_ID": statbl_id,
            "DTACYCLE_CD": cycle, "pIndex": page, "pSize": 1000,
        })
        with urllib.request.urlopen(f"{URL}?{q}", timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
        if "SttsApiTblData" not in body:
            raise RuntimeError(f"R-ONE 오류: {body.get('RESULT')}")
        block = body["SttsApiTblData"]
        total = block[0]["head"][0]["list_total_count"]
        batch = block[1]["row"]
        rows += batch
        if len(rows) >= total or not batch:
            return rows
        page += 1


def main():
    key = os.environ.get("RONE_KEY", "").strip()
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if not key:
        print("RONE_KEY 없음 · 부동산원 지수는 건너뜀")
        return
    names = {r["name"] for r in cfg["regions"]}
    out = {}
    for label, sid in (("sale", cfg["rone"].get("weekly_sale_index_statbl_id")),
                       ("jeonse", cfg["rone"].get("weekly_jeonse_index_statbl_id"))):
        if not sid:
            continue
        rows = fetch_table(key, sid)
        series = {}
        for r in rows:
            nm = (r.get("CLS_NM") or "").strip()
            if nm in names:
                series.setdefault(nm, []).append({"t": r.get("WRTTIME_DESC"), "v": float(r["DTA_VAL"])})
        out[label] = series
        print(f"R-ONE {label}: {sum(len(v) for v in series.values())}건")
    (ROOT / "data" / "rone.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
