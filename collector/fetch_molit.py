"""국토교통부 아파트 매매·전월세 실거래가를 받아 data/raw 에 월별로 저장.

- 인증키: 환경변수 DATA_GO_KR_KEY (공공데이터포털 '일반 인증키(Decoding)')
- 처음 실행하면 config.json 의 history_start 부터 전부 받고,
  그 뒤로는 최근 몇 달(refetch_recent_months)만 다시 받아요.
  (실거래는 계약 후 30일 안에 신고되고, 취소도 나중에 반영되기 때문)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

ENDPOINTS = {
    "trade": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    "rent": "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent",
}
# 공공데이터포털은 기본 스크립트 User-Agent 를 막는 경우가 있어 브라우저처럼 보냄
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def months_between(start_ym: str, end: date):
    y, m = int(start_ym[:4]), int(start_ym[4:])
    while (y, m) <= (end.year, end.month):
        yield f"{y}{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def call(url: str, params: dict, retries: int = 3) -> bytes:
    params = dict(params)
    key = params.pop("serviceKey")
    # 'Encoding 키'(이미 %로 인코딩됨)와 'Decoding 키' 둘 다 받아요
    key_q = key if "%" in key else urllib.parse.quote(key, safe="")
    q = f"serviceKey={key_q}&" + urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": UA})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:  # 네트워크 일시 오류는 잠깐 쉬고 다시
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"API 호출 실패: {last}")


def parse_items(xml_bytes: bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        raise RuntimeError(f"API 응답을 읽을 수 없어요: {xml_bytes[:200]!r}")
    if root.tag == "OpenAPI_ServiceResponse":  # 인증 오류 등은 이 모양으로 와요
        raise RuntimeError("API 인증 오류: " + (root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or ""))
    code = (root.findtext(".//resultCode") or "").strip()
    if code not in ("", "00", "000"):
        msg = root.findtext(".//resultMsg") or ""
        raise RuntimeError(f"API 오류 {code}: {msg}")
    total = int((root.findtext(".//totalCount") or "0").strip() or 0)
    items = []
    for it in root.iter("item"):
        items.append({c.tag: (c.text or "").strip() for c in it})
    return items, total


def fetch_month(kind: str, key: str, lawd: str, ym: str):
    rows, page = [], 1
    while True:
        body = call(ENDPOINTS[kind], {
            "serviceKey": key, "LAWD_CD": lawd, "DEAL_YMD": ym,
            "pageNo": page, "numOfRows": 1000,
        })
        items, total = parse_items(body)
        rows += items
        if len(rows) >= total or not items:
            return rows
        page += 1


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        sys.exit("DATA_GO_KR_KEY 가 없어요. README 의 '인증키 넣기'를 봐 주세요.")
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    today = date.today()
    months = list(months_between(cfg["history_start"], today))
    recent = set(months[-cfg.get("refetch_recent_months", 3):])

    calls = 0
    kinds = ["trade", "rent"]
    # 전월세 API 는 활용신청을 안 했을 수도 있어요 → 한 번 시험해 보고 안 되면 건너뜀
    try:
        fetch_month("rent", key, cfg["regions"][0]["lawd_cd"], months[-1])
    except Exception as e:
        print(f"전월세 API 사용 불가 · 전세 정보 없이 진행해요 ({e})")
        kinds = ["trade"]
    for region in cfg["regions"]:
        for kind in kinds:
            folder = RAW / kind / region["lawd_cd"]
            folder.mkdir(parents=True, exist_ok=True)
            for ym in months:
                path = folder / f"{ym}.json"
                if path.exists() and ym not in recent:
                    continue
                rows = fetch_month(kind, key, region["lawd_cd"], ym)
                path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                calls += 1
                print(f"{region['name']} {kind} {ym}: {len(rows)}건")
                time.sleep(0.15)
    print(f"완료 · API 호출 {calls}회")


if __name__ == "__main__":
    main()
