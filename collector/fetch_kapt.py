"""(선택) 공동주택관리정보시스템(K-apt)에서 단지 세대수·동수·난방·주차를 받아 data/kapt.json 에 저장.

- 인증키: DATA_GO_KR_KEY (공공데이터포털에서 아래 두 API 를 활용신청해야 해요)
    국토교통부_공동주택 단지 목록제공 서비스
    국토교통부_공동주택 기본 정보제공 서비스
- 한 달에 한 번만 새로 받아요 (단지 정보는 거의 안 바뀌어서).
- 안 되면 조용히 건너뛰고, 사이트는 거래량으로 세대수를 추정해요.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_molit import call  # 같은 호출 도구 사용

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "kapt.json"
BASE = "https://apis.data.go.kr/1613000/"
LIST_APIS = ["AptListService4/getSigunguAptList4", "AptListService3/getSigunguAptList3"]
BASIC_APIS = ["AptBasisInfoServiceV5/getAphusBassInfoV5", "AptBasisInfoServiceV4/getAphusBassInfoV4"]
DETAIL_APIS = ["AptBasisInfoServiceV5/getAphusDtlInfoV5", "AptBasisInfoServiceV4/getAphusDtlInfoV4"]


def items_of(body: bytes):
    """XML 이든 JSON 이든 item 목록과 전체 건수를 꺼내요."""
    text = body.decode("utf-8", "replace").strip()
    if text.startswith("{"):
        d = json.loads(text)
        b = d.get("response", {}).get("body", {})
        it = b.get("items", {})
        if isinstance(it, dict):
            it = it.get("item", [])
        if isinstance(it, dict):
            it = [it]
        if not it and isinstance(b.get("item"), dict):
            it = [b["item"]]
        code = str(d.get("response", {}).get("header", {}).get("resultCode", "00"))
        if code not in ("00", "000"):
            raise RuntimeError(d.get("response", {}).get("header", {}).get("resultMsg"))
        return it or [], int(b.get("totalCount") or len(it or []))
    import xml.etree.ElementTree as ET
    root = ET.fromstring(body)
    if root.tag == "OpenAPI_ServiceResponse":
        raise RuntimeError(root.findtext(".//returnAuthMsg") or "인증 오류")
    code = (root.findtext(".//resultCode") or "00").strip()
    if code not in ("00", "000", ""):
        raise RuntimeError(root.findtext(".//resultMsg"))
    its = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    return its, int((root.findtext(".//totalCount") or len(its)) or 0)


def first_working(paths, params):
    last = None
    for p in paths:
        try:
            return p, items_of(call(BASE + p, dict(params)))
        except Exception as e:
            last = e
    raise RuntimeError(last)


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_KEY 없음 · K-apt 건너뜀")
        return
    if OUT.exists() and datetime.fromtimestamp(OUT.stat().st_mtime) > datetime.now() - timedelta(days=30) \
            and json.loads(OUT.read_text(encoding="utf-8")):
        print("K-apt 정보가 최근 것이라 건너뜀")
        return
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    out, fails = {}, 0
    try:
        for reg in cfg["regions"]:
            page, rows = 1, []
            while True:
                api, (its, total) = first_working(LIST_APIS, {"serviceKey": key, "sigunguCode": reg["lawd_cd"], "numOfRows": 1000, "pageNo": page})
                rows += its
                if len(rows) >= total or not its:
                    break
                page += 1
            print(f"{reg['name']} 단지 목록 {len(rows)}개 ({api})")
            for r in rows:
                code = r.get("kaptCode")
                if not code:
                    continue
                info = {"name": r.get("kaptName"), "bjdCode": r.get("bjdCode"), "lawd": reg["lawd_cd"]}
                try:
                    _, (b, _) = first_working(BASIC_APIS, {"serviceKey": key, "kaptCode": code})
                    if b:
                        b = b[0]
                        info.update({k: b.get(k) for k in ("kaptName", "kaptAddr", "doroJuso", "kaptdaCnt", "kaptDongCnt", "kaptUsedate", "codeHeatNm", "codeHallNm", "kaptBcompany")})
                    _, (d, _) = first_working(DETAIL_APIS, {"serviceKey": key, "kaptCode": code})
                    if d:
                        d = d[0]
                        info.update({k: d.get(k) for k in ("kaptdPcnt", "kaptdPcntu", "subwayLine", "subwayStation", "kaptdWtimesub")})
                except Exception as e:
                    info["error"] = str(e)[:80]
                    fails += 1
                    if fails >= 3 and len(out) < 3:
                        raise RuntimeError(f"기본정보 API 사용 불가: {e}")
                out[code] = info
                time.sleep(0.05)
    except Exception as e:
        print(f"K-apt API 사용 불가 · 세대수는 거래량으로 추정해요 ({e})")
        if old:
            return
    if out:
        OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"K-apt 단지 {len(out)}개 저장")


if __name__ == "__main__":
    main()
