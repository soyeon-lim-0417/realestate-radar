"""모아 둔 실거래 원자료로 사이트가 읽을 JSON 을 만들어요.

사용:  python collector/build.py            (실데이터: data/raw)
       python collector/build.py --sample   (테스트 데이터: data/sample_raw)

만드는 것 (site/data/):
  meta.json        업데이트 시각, 테스트 여부
  recommend.json   오늘의 추천 10 + 요약 숫자
  units.json       후보 단지·평형 전체 목록 (가벼운 버전)
  units/<id>.json  단지 상세 (거래 내역, 월별 흐름, 전세, 세대수)
  regions.json     구별 흐름 (월별 가격·거래량·전세, 신호 체크)
"""
import json
import shutil
import statistics as st
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DATA = ROOT / "site" / "data"
HISTORY = ROOT / "data" / "history"
KST = timezone(timedelta(hours=9))


# ---------- 작은 도구들 ----------
def to_int(s):
    try:
        return int(float(str(s).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def to_float(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def ym_add(ym, k):
    y, m = divmod(int(ym[:4]) * 12 + int(ym[4:]) - 1 + k, 12)
    return f"{y}{m + 1:02d}"


def ym_range(a, b):
    out, cur = [], a
    while cur <= b:
        out.append(cur)
        cur = ym_add(cur, 1)
    return out


def median(xs):
    return st.median(xs) if xs else None


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def pyeong(area):
    """전용면적 → 흔히 부르는 평형(대략). 공급면적 ≈ 전용 × 1.38"""
    return round(area * 1.38 / 3.3058)


# ---------- 원자료 읽기 ----------
def load_raw(raw_dir, kind, lawd):
    rows = []
    folder = raw_dir / kind / lawd
    if not folder.exists():
        return rows
    for f in sorted(folder.glob("*.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))
    return rows


# 예전 형식(한글 태그)으로 오는 경우도 받아요
KO = {"거래금액": "dealAmount", "아파트": "aptNm", "전용면적": "excluUseAr", "년": "dealYear", "월": "dealMonth",
      "일": "dealDay", "층": "floor", "법정동": "umdNm", "지번": "jibun", "건축년도": "buildYear",
      "해제여부": "cdealType", "거래유형": "dealingGbn", "보증금액": "deposit", "월세금액": "monthlyRent"}


def en(r):
    out = dict(r)
    for k, v in r.items():
        if k in KO and KO[k] not in out:
            out[KO[k]] = v
    if out.get("cdealType", "").strip() in ("O", "Y"):
        out["cdealType"] = "O"
    return out


def norm_trade(r, lawd):
    r = en(r)
    price = to_int(r.get("dealAmount"))
    area = to_float(r.get("excluUseAr") or r.get("exclUseAr"))
    y, m, d = to_int(r.get("dealYear")), to_int(r.get("dealMonth")), to_int(r.get("dealDay"))
    if not (price and area and y and m and d):
        return None
    nm, umd, jibun = (r.get("aptNm") or "").strip(), (r.get("umdNm") or "").strip(), (r.get("jibun") or "").strip()
    return {
        "key": r.get("aptSeq") or f"{lawd}-{umd}-{jibun}-{nm}",
        "match": f"{umd}|{jibun}|{nm}",
        "name": nm, "dong": umd, "jibun": jibun, "lawd": lawd,
        "built": to_int(r.get("buildYear")),
        "area": area, "bucket": int(area),
        "price": price, "floor": to_int(r.get("floor")) or 0,
        "date": f"{y:04d}-{m:02d}-{d:02d}", "ym": f"{y:04d}{m:02d}",
        "cancelled": (r.get("cdealType") or "").strip().upper() == "O",
        "direct": "직거래" in (r.get("dealingGbn") or ""),
        "rgst": (r.get("rgstDate") or "").strip(),
    }


def norm_rent(r, lawd):
    r = en(r)
    dep = to_int(r.get("deposit"))
    area = to_float(r.get("exclUseAr") or r.get("excluUseAr"))
    y, m = to_int(r.get("dealYear")), to_int(r.get("dealMonth"))
    if not (dep and area and y and m):
        return None
    nm, umd, jibun = (r.get("aptNm") or "").strip(), (r.get("umdNm") or "").strip(), (r.get("jibun") or "").strip()
    return {
        "match": f"{umd}|{jibun}|{nm}", "lawd": lawd, "area": area, "bucket": int(area),
        "deposit": dep, "jeonse": (to_int(r.get("monthlyRent")) or 0) == 0,
        "ym": f"{y:04d}{m:02d}",
    }


# ---------- 구별 흐름 ----------
def region_report(name, trades, rents, last_ym):
    months = ym_range(ym_add(last_ym, -35), last_ym)
    ppm = defaultdict(list)     # 매매 ㎡당 가격
    vol = defaultdict(int)
    jppm = defaultdict(list)    # 전세 ㎡당 보증금
    for t in trades:
        if t["cancelled"]:
            continue
        vol[t["ym"]] += 1
        if not t["direct"]:
            ppm[t["ym"]].append(t["price"] / t["area"])
    for r in rents:
        if r["jeonse"]:
            jppm[r["ym"]].append(r["deposit"] / r["area"])

    def pooled(store, ms):
        xs = [x for m in ms for x in store.get(m, [])]
        return median(xs)

    series = []
    for m in months:
        p, j = median(ppm.get(m, [])), median(jppm.get(m, []))
        series.append({
            "ym": m, "ppm": round(p) if p else None, "vol": vol.get(m, 0),
            "jppm": round(j) if j else None,
            "jratio": round(j / p, 3) if (p and j) else None,
        })

    # 신호 체크 (가장 최근 달은 신고가 덜 들어와서 거래량 비교에서 뺌)
    v_now = sum(vol.get(m, 0) for m in ym_range(ym_add(last_ym, -6), ym_add(last_ym, -1)))
    v_before = sum(vol.get(m, 0) for m in ym_range(ym_add(last_ym, -12), ym_add(last_ym, -7)))
    p_now = pooled(ppm, ym_range(ym_add(last_ym, -2), last_ym))
    p_before = pooled(ppm, ym_range(ym_add(last_ym, -5), ym_add(last_ym, -3)))
    j_now = pooled(jppm, ym_range(ym_add(last_ym, -2), last_ym))
    j_before = pooled(jppm, ym_range(ym_add(last_ym, -5), ym_add(last_ym, -3)))

    all_months = sorted(ppm)
    roll = []
    for i in range(2, len(all_months)):
        v = pooled(ppm, all_months[i - 2:i + 1])
        roll.append((all_months[i], v))
    peak_m, peak_v = max(roll, key=lambda x: x[1]) if roll else (None, None)

    vol_chg = (v_now / v_before - 1) if v_before else None
    p_chg = (p_now / p_before - 1) if (p_now and p_before) else None
    j_chg = (j_now / j_before - 1) if (j_now and j_before) else None
    from_peak = (p_now / peak_v - 1) if (p_now and peak_v) else None

    checks = [
        {"id": "volume", "title": "거래가 먼저 살아나나?", "ok": vol_chg is not None and vol_chg >= 0.10,
         "detail": f"최근 6개월 거래 {v_now}건 · 그 전 6개월 {v_before}건"},
        {"id": "price", "title": "가격 하락이 멈췄나?", "ok": p_chg is not None and p_chg >= -0.005,
         "detail": "최근 3개월 가격이 그 전 3개월보다 " + (f"{abs(p_chg) * 100:.1f}% {'올랐어요' if p_chg >= 0 else '내렸어요'}" if p_chg is not None else "비교할 거래가 부족해요")},
        {"id": "jeonse", "title": "전세가 받쳐주나?", "ok": j_chg is not None and j_chg >= 0.005,
         "detail": "최근 3개월 전세가 그 전보다 " + (f"{abs(j_chg) * 100:.1f}% {'올랐어요' if j_chg >= 0 else '내렸어요'}" if j_chg is not None else "비교할 거래가 부족해요")},
        {"id": "room", "title": "너무 많이 오르진 않았나?", "ok": from_peak is not None and from_peak <= -0.05,
         "detail": (f"동네 전체가 고점보다 {abs(from_peak) * 100:.0f}% 낮아요" if from_peak is not None and from_peak < 0 else "동네 전체가 고점 근처예요")},
    ]
    # 전세 자료가 없으면 그 항목은 빼고 판단 (4개 중 3개 = 75% 기준 유지)
    if j_chg is None:
        checks[2]["na"] = True
        checks[2]["detail"] = "전세 자료가 아직 없어요 (전월세 API 신청 후 자동 반영)"
    avail = [c for c in checks if not c.get("na")]
    n_ok = sum(c["ok"] for c in avail)
    frac = n_ok / len(avail) if avail else 0
    status = "회복 신호" if frac >= 0.75 else ("지켜보기" if frac >= 0.5 else "약세")
    tone = "good" if frac >= 0.75 else ("watch" if frac >= 0.5 else "weak")
    if not trades:
        status, tone = "자료 받는 중", "weak"
    summary = {
        "good": "떨어지던 값이 멈추고 거래가 살아나는 중이에요.",
        "watch": "좋은 신호와 나쁜 신호가 섞여 있어요. 조금 더 지켜봐요.",
        "weak": "아직 가격이 약하거나 거래가 살아나지 않았어요.",
    }[tone] if trades else "실거래 자료를 아직 다 받지 못했어요. 다음 업데이트 때 채워져요."
    last_j = next((s["jratio"] for s in reversed(series) if s["jratio"]), None)
    return {
        "name": name, "status": status, "tone": tone, "okCount": n_ok, "checkCount": len(avail), "summary": summary,
        "checks": checks, "series": series,
        "peak": {"ym": peak_m, "ppm": round(peak_v) if peak_v else None},
        "now": {"ppm": round(p_now) if p_now else None, "fromPeak": from_peak, "jratio": last_j,
                "volChange": vol_chg, "priceChange": p_chg, "jeonseChange": j_chg},
    }


# ---------- 단지·평형 분석 ----------
def analyze_unit(ts, rents_by_match, cfg, today):
    f = cfg["filters"]
    ts = sorted(ts, key=lambda t: t["date"])
    # 등기 안 된 거래: 2023년부터 등기일이 공개돼요. 보통 계약 후 4~6개월 안에 등기되는데,
    # 6개월이 지나도 등기가 없으면 잔금을 안 치렀거나 신고가 띄우기일 수 있어서 계산에서 빼요.
    rg_cut = (today - timedelta(days=183)).isoformat()
    unreg = {id(t) for t in ts if not t["cancelled"] and "2023-01-01" <= t["date"] <= rg_cut and not t["rgst"]}
    valid = [t for t in ts if not t["cancelled"]
             and not (f["exclude_direct_deal"] and t["direct"])
             and id(t) not in unreg
             and t["floor"] > f["exclude_low_floor_upto"]]
    if not valid:
        return None

    # 튀는 거래 걸러내기: 앞뒤 1년 거래(2건 이상) 중간값보다 25% 넘게 '싼' 거래만 '이상치'
    #  (가족 간 거래, 지분 거래 등). 비싼 거래(신고가)는 시장이 오른 것일 수 있어 그대로 둬요.
    outliers = set()
    for i, t in enumerate(valid):
        d = datetime.fromisoformat(t["date"])
        nb = [u["price"] for j, u in enumerate(valid) if j != i and abs((datetime.fromisoformat(u["date"]) - d).days) <= 365]
        if len(nb) >= 2:
            m = median(nb)
            if t["price"] < m * 0.75:
                outliers.add(id(t))
        elif i > 0 and t["price"] < valid[i - 1]["price"] * 0.75:
            # 주변 거래가 적을 땐 바로 앞 거래와 비교: 25% 넘게 싸면 특이 거래(지분·특수관계 등)로 봄
            outliers.add(id(t))
    valid = [t for t in valid if id(t) not in outliers]
    if not valid:
        return None

    # 전고점: 비싼 거래도 그대로 인정 (등기 안 된 거래·취소·직거래·저층은 이미 빠져 있어요)
    def neighborhood_median(t):
        d = datetime.fromisoformat(t["date"])
        xs = [u["price"] for u in valid if abs((datetime.fromisoformat(u["date"]) - d).days) <= 183]
        return median(xs)
    # 전고점 = 지난 상승장(기본 2020~2022년) 안에서 가장 비싼 거래
    #  (요즘 거래가 더 비싸면 '전고점 대비 하락'이 아니라 '전고점 돌파')
    pw = cfg.get("peak_window", {"from": "2020-01-01", "to": "2022-12-31"})
    peak, ath = None, None
    for t in valid:
        if ath is None or t["price"] > ath["price"]:
            ath = t
        if pw["from"] <= t["date"] <= pw["to"] and (peak is None or t["price"] > peak["price"]):
            peak = t

    cut6 = (today - timedelta(days=183)).isoformat()
    cut12 = (today - timedelta(days=365)).isoformat()
    cut24 = (today - timedelta(days=730)).isoformat()
    recent6 = [t["price"] for t in valid if t["date"] >= cut6]
    last = valid[-1]
    # 기준 가격: 1년 안의 가장 최근 3건 중간값 (한 건만 튀는 급매·특이 거래에 덜 흔들리게)
    # 비교 기준 가격 = '가장 최근 거래'와 '최근 3건 중간값' 중 높은 값
    #  - 급매 한 건 때문에 '많이 빠졌다'고 과장하지 않고
    #  - 값이 이미 회복됐는데 옛 거래 때문에 싸 보이지도 않게 (보수적으로)
    last3 = [t["price"] for t in valid if t["date"] >= cut12][-3:]
    if last3:
        m3 = median(last3)
        recent = max(m3, last3[-1])
        basis = "가장 최근 거래" if recent == last3[-1] else f"최근 {len(last3)}건 중간값"
    else:
        recent, basis = None, None

    monthly = defaultdict(list)
    for t in valid:
        monthly[t["ym"]].append(t["price"])

    first = ts[0]
    j_list = [r["deposit"] for r in rents_by_match.get((first["match"], first["bucket"]), [])
              if r["jeonse"] and r["ym"] >= cut12[:7].replace("-", "")]
    jeonse = median(j_list)
    jmonthly = defaultdict(list)
    for r in rents_by_match.get((first["match"], first["bucket"]), []):
        if r["jeonse"]:
            jmonthly[r["ym"]].append(r["deposit"])

    return {
        "id": f"{first['key']}_{first['bucket']}".replace("/", "-").replace(" ", ""),
        "name": first["name"], "dong": first["dong"], "jibun": first["jibun"], "lawd": first["lawd"],
        "built": first["built"], "area": first["bucket"], "pyeong": pyeong(first["bucket"]),
        "peak": {"price": peak["price"], "date": peak["date"], "floor": peak["floor"]} if peak else None,
        "recent": round(recent) if recent else None, "recentBasis": basis,
        "last": {"price": last["price"], "date": last["date"], "floor": last["floor"]},
        "drop": (1 - recent / peak["price"]) if (recent and peak) else None,
        "ath": {"price": ath["price"], "date": ath["date"]} if ath else None,
        "trades2y": sum(1 for t in valid if t["date"] >= cut24),
        "trades1y": sum(1 for t in valid if t["date"] >= cut12),
        "trades6m": len(recent6),
        "jeonse": round(jeonse) if jeonse else None, "jeonseCount": len(j_list),
        "jratio": (jeonse / recent) if (jeonse and recent) else None,
        "trades": [{"d": t["date"], "p": t["price"], "f": t["floor"],
                    "x": "취소" if t["cancelled"] else ("직거래" if t["direct"] else ("등기 안 됨" if id(t) in unreg else ("저층" if t["floor"] <= f["exclude_low_floor_upto"] else ("시세와 동떨어짐" if id(t) in outliers else ""))))}
                   for t in ts],
        "monthly": [{"ym": m, "p": round(median(v))} for m, v in sorted(monthly.items())],
        "jmonthly": [{"ym": m, "p": round(median(v))} for m, v in sorted(jmonthly.items())],
    }


WALK = {"5분이내": 3, "5~10분이내": 8, "10~15분이내": 13, "15~20분이내": 18, "20분초과": 23}
HALL = {"계단식": 1.0, "혼합식": 0.6, "복도식": 0.2}


def score_unit(u, region, cfg, today):
    """항목별 0~1 점수 → 비중(weights)대로 더해 100점 만점."""
    w = cfg["weights"]
    reg_cfg = next(r for r in cfg["regions"] if r["lawd_cd"] == u["lawd"])
    c = u.get("complex") or {}
    hh = c.get("households")
    age = today.year - (u["built"] or today.year)

    # 강남 접근성: 구별 강남역까지 대략 시간 + 단지에서 지하철역까지 걷는 시간
    walk = WALK.get(c.get("walk") or "", 10)
    gmin = cfg.get("gangnam_by_dong", {}).get(u["dong"], reg_cfg.get("gangnam_min", 40) + walk)
    # 학군: 반경 1km 안 학원 수 (학원가 규모). 기준 개수 이상이면 만점
    acad = c.get("academies")
    acad_full = cfg.get("school", {}).get("academies_full", 300)
    school_score = clamp(acad / acad_full) if acad is not None else 0.4
    # 환금성: 1년에 단지 세대 중 몇 %가 거래되나 (모르면 거래 건수로)
    per_year = u.get("complexTrades1y") or 0
    turnover = per_year / hh if hh else None
    liquidity = clamp(turnover / 0.06) if turnover is not None else clamp(per_year / 30)
    size = 0.3 if not hh else (1.0 if hh >= 1500 else 0.85 if hh >= 1000 else 0.5 if hh >= 500 else 0.2)
    hall = c.get("hall")
    drop = u["drop"] if u["drop"] is not None else 0

    # 역세권: 카카오 거리(있으면) → 없으면 공동주택 자료의 '역까지 걷는 시간'
    st = c.get("station")
    if st and st.get("m") is not None:
        m = st["m"]
        station = 1.0 if m <= 300 else 0.8 if m <= 500 else 0.5 if m <= 800 else 0.2 if m <= 1200 else 0.0
    else:
        station = {"5분이내": 1.0, "5~10분이내": 0.7, "10~15분이내": 0.35, "15~20분이내": 0.1, "20분초과": 0.0}.get(c.get("walk") or "", 0.4)
    # 초품아: 가장 가까운 초등학교 거리 (300m 안이면 사실상 단지 옆)
    el = c.get("elementary")
    if el and el.get("m") is not None:
        m = el["m"]
        elementary = 1.0 if m <= 300 else 0.6 if m <= 500 else 0.3 if m <= 800 else 0.0
    else:
        elementary = 0.5  # 아직 모름
    # 2호선·9호선 가산점: 걸어갈 만한 역(역세권 점수 절반 이상)이 2·9호선이면
    lines_txt = (c.get("lines") or "") + " " + ((st or {}).get("name") or "")
    gold = [ln for ln in ("2호선", "9호선") if ln in lines_txt]
    bonus = cfg.get("bonus", {}).get("line_2_9", 0) if (gold and station >= 0.5) else 0

    tier = cfg.get("tier_by_region", {}).get(reg_cfg["name"])
    if tier and u["dong"] in cfg.get("tier_down_dong", {}).get("동", []):
        tier += 1  # 구 급지보다 한 단계 낮춤
    tier = cfg.get("tier_by_dong", {}).get(u["dong"], tier)
    parts = {
        "price_drop": clamp(drop / 0.25),
        "tier": (1 - (tier - 1) * 0.2) if tier else 0.5,
        "growth": clamp(0.7 * region["okCount"] / max(1, region["checkCount"]) + 0.3 * clamp(((u["jratio"] or 0.45) - 0.4) / 0.3)),
        "gangnam": clamp((70 - gmin) / 45),
        "school": school_score,
        "size": size,
        "liquidity": liquidity,
        "structure": HALL.get(hall, 0.5),
        "age": clamp(1 - age / 35),
        "station": station,
        "elementary": elementary,
    }
    total = sum(w.get(k, 0) * v for k, v in parts.items())
    scale = sum(w.get(k, 0) for k in parts) or 1
    score = round(total / scale * 100) + bonus

    peak_txt = "2021~22년 전고점" if u["peak"] else "전고점"
    lines = {
        "price_drop": f"{peak_txt}보다 {round(drop * 100)}% 싸요",
        "growth": f"{region['name']} 흐름이 '{region['status']}'",
        "tier": f"{tier:g}급지" if tier else "급지 미정",
        "gangnam": f"강남까지 약 {gmin}분",
        "school": f"학원가 (1km 안 학원 {acad}곳)" if acad is not None else "학군",
        "size": f"{hh:,}세대 대단지" if hh else "대단지",
        "liquidity": "거래가 잘 되는 단지 (팔기 쉬움)",
        "structure": f"{hall} 구조" if hall else "구조 양호",
        "age": f"{u['built']}년 준공으로 비교적 새 아파트",
        "station": (f"{st['name'].split(' ')[0]} {st['m']}m" if st and st.get('m') is not None else f"역까지 {c.get('walk') or '?'}") + " 역세권",
        "elementary": f"초품아 ({el['name']} {el['m']}m)" if el and el.get('m') is not None and el['m'] <= 300 else "초등학교 가까움",
    }
    top = sorted(parts, key=lambda k: w.get(k, 0) * parts[k], reverse=True)
    reason = " · ".join(lines[k] for k in top[:3])

    tags = []
    d = round(drop * 100)
    if u["peak"] and d >= 20:
        tags.append("전고점 20%↓")
    elif u["peak"] and d >= 10:
        tags.append("전고점 10%↓")
    elif u["peak"] and d < 0:
        tags.append("전고점 돌파")
    if tier:
        tags.insert(0, f"{tier:g}급지")
    if hh and hh >= 1000:
        tags.append(f"대단지 {hh:,}세대")
    if gold and bonus:
        tags.insert(1 if tier else 0, "·".join(gold) + " 역세권")
    elif station >= 0.7:
        tags.append("역세권")
    if el and el.get("m") is not None and el["m"] <= 300:
        tags.append("초품아")
    if hall == "계단식":
        tags.append("계단식")
    elif hall == "복도식":
        tags.append("복도식")
    if gmin <= 35:
        tags.append(f"강남 {gmin}분")
    if liquidity >= 0.8:
        tags.append("환금성 좋음")
    if u["jratio"] and u["jratio"] >= 0.6:
        tags.append(f"전세가율 {round(u['jratio'] * 100)}%")
    if age <= 10:
        tags.append("신축급")
    elif age >= 30:
        tags.append("준공 30년+ (재건축 연한)")
    detail = {"tier": tier, "bonus": bonus, "gold": gold, "station": st, "elementary": el, "lines": c.get("lines"), "gangnamMin": gmin, "walk": c.get("walk"), "academies": acad, "turnover": round(turnover, 3) if turnover is not None else None,
              "tradesPerYear": per_year, "hall": hall, "age": age}
    return score, reason, tags, {k: round(v, 2) for k, v in parts.items()}, detail


# ---------- 단지 규모 (세대수) ----------
import re
from difflib import SequenceMatcher


def norm_name(n):
    n = re.sub(r"\(.*?\)", "", n or "")
    n = re.sub(r"아파트|APT|apt|\s|[·\-_,.]", "", n)
    return n.lower()


def load_kapt():
    p = ROOT / "data" / "kapt.json"
    if not p.exists():
        return {}
    idx = defaultdict(list)  # (구코드, 동이름) → 단지들
    for code, k in json.loads(p.read_text(encoding="utf-8")).items():
        if code.startswith("__"):
            continue
        addr = k.get("kaptAddr") or ""
        m = re.search(r"([가-힣0-9]+동[0-9]*가?)\s+([0-9]+)(?:-([0-9]+))?", addr)
        dong = m.group(1) if m else ""
        k["_dong"], k["_bon"] = dong, (m.group(2) if m else None)
        k["_nm"] = norm_name(k.get("kaptName") or k.get("name"))
        k["code"] = code
        idx[(k.get("lawd"), dong)].append(k)
    return idx


def match_kapt(idx, lawd, dong, jibun, name):
    cands = idx.get((lawd, dong), [])
    if not cands:
        return None
    bon = (jibun or "").split("-")[0].strip()
    nm = norm_name(name)
    best, score = None, 0.0
    for k in cands:
        sc = SequenceMatcher(None, nm, k["_nm"]).ratio()
        if nm and k["_nm"] and (nm in k["_nm"] or k["_nm"] in nm):
            sc = max(sc, 0.85)
        if bon and k["_bon"] == bon:
            sc += 0.5
        if sc > score:
            best, score = k, sc
    return best if score >= 0.75 else None


def complex_size(u, ctotal, cfirst, kidx, today):
    """세대수: K-apt 에서 찾으면 그 값, 못 찾으면 거래량으로 추정 (1년에 약 4%가 거래된다고 가정)."""
    k = match_kapt(kidx, u["lawd"], u["dong"], u["jibun"], u["name"]) if kidx else None
    hh = to_int(k.get("kaptdaCnt")) if k else None
    if hh:
        park = (to_int(k.get("kaptdPcnt")) or 0) + (to_int(k.get("kaptdPcntu")) or 0)
        return {"households": hh, "source": "kapt", "dongCnt": to_int(k.get("kaptDongCnt")),
                "heat": k.get("codeHeatNm"), "hall": k.get("codeHallNm"),
                "parking": round(park / hh, 2) if park else None, "kaptCode": k["code"],
                "subway": " ".join(x for x in [k.get("subwayLine"), k.get("subwayStation")] if x) or None,
                "lines": k.get("subwayLine"),
                "walk": k.get("kaptdWtimesub")}
    start = max(2019.0, float(u["built"] or 2019) + 0.5)
    years = max(0.5, (today.year + today.month / 12) - start)
    est = ctotal / years / 0.04
    young = u["built"] and u["built"] >= today.year - 3  # 새 아파트는 거래가 적어 추정 불가
    return {"households": None if young else int(round(est / 10) * 10), "source": "estimate" if not young else "unknown"}


# ---------- 메인 ----------
def main():
    sample = "--sample" in sys.argv
    raw_dir = ROOT / "data" / ("sample_raw" if sample else "raw")
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    now = datetime.now(KST)
    today = now.date()
    last_ym = ym_add(f"{today.year}{today.month:02d}", -1)  # 이번 달은 신고가 너무 적어 제외

    if (SITE_DATA / "units").exists():
        shutil.rmtree(SITE_DATA / "units")
    (SITE_DATA / "units").mkdir(parents=True, exist_ok=True)

    f = cfg["filters"]
    min_hh = f.get("min_households", 0)
    kidx = {} if sample else load_kapt()
    kp = ROOT / "data" / "kakao.json"
    kakao = {} if (sample or not kp.exists()) else json.loads(kp.read_text(encoding="utf-8"))
    regions, candidates, all_units, small_out = {}, [], 0, 0
    for reg in cfg["regions"]:
        lawd = reg["lawd_cd"]
        trades = [t for t in (norm_trade(r, lawd) for r in load_raw(raw_dir, "trade", lawd)) if t]
        rents = [r for r in (norm_rent(x, lawd) for x in load_raw(raw_dir, "rent", lawd)) if r]
        region = region_report(reg["name"], trades, rents, last_ym)
        region["lawd"] = lawd
        regions[lawd] = region

        rents_by_match = defaultdict(list)
        for r in rents:
            rents_by_match[(r["match"], r["bucket"])].append(r)
        ctotal, cfirst, c1y = defaultdict(int), {}, defaultdict(int)
        cut1y = (today - timedelta(days=365)).isoformat()
        for t in trades:
            if not t["cancelled"]:
                ctotal[t["key"]] += 1
                if t["date"] >= cut1y:
                    c1y[t["key"]] += 1
        groups = defaultdict(list)
        for t in trades:
            if f["area_min_m2"] <= t["bucket"] <= f["area_max_m2"]:  # 84.97㎡ 도 84㎡ 로 봐요
                groups[(t["key"], t["bucket"])].append(t)
        for ts in groups.values():
            u = analyze_unit(ts, rents_by_match, cfg, today)
            if not u:
                continue
            all_units += 1
            u["complex"] = complex_size(u, ctotal[ts[0]["key"]], cfirst, kidx, today)
            u["complexTrades1y"] = c1y[ts[0]["key"]]
            kk = kakao.get(u["complex"].get("kaptCode") or "")
            if kk and kk.get("x"):
                u["complex"]["elementary"] = kk.get("elementary")
                u["complex"]["station"] = kk.get("station")
                u["complex"]["academies"] = kk.get("academies")
            hh = u["complex"]["households"]
            big_enough = hh is None or hh >= min_hh
            if not big_enough:
                small_out += 1
            ok = (u["recent"] and u["peak"] and u["last"]["price"] < f["max_price_manwon"] and u["recent"] < f["max_price_manwon"]
                  and u["trades2y"] >= f["min_trades_2y"] and u["trades1y"] >= f.get("min_trades_1y", 2) and big_enough)
            u["region"] = reg["name"]
            if ok:
                u["score"], u["reason"], u["tags"], u["parts"], u["scoreDetail"] = score_unit(u, region, cfg, today)
                candidates.append(u)
            (SITE_DATA / "units" / f"{u['id']}.json").write_text(json.dumps(u, ensure_ascii=False), encoding="utf-8")

    # 추천: 점수 순, 같은 단지는 한 평형만
    ranked, seen = [], set()
    for u in sorted(candidates, key=lambda x: (-x["score"], -(x["drop"] or 0))):
        k = (u["lawd"], u["name"], u["dong"])
        if k in seen:
            continue
        seen.add(k)
        ranked.append(u)
    top = ranked[:cfg.get("top_n", 10)]

    # 어제 추천과 비교
    HISTORY.mkdir(parents=True, exist_ok=True)
    prev_files = sorted(p for p in HISTORY.glob("*.json") if p.stem < today.isoformat())
    prev_ids = set(json.loads(prev_files[-1].read_text())["ids"]) if (prev_files and not sample) else set()
    if not sample:
        (HISTORY / f"{today.isoformat()}.json").write_text(json.dumps({"ids": [u["id"] for u in top]}))

    def light(u):
        keys = ["id", "name", "dong", "region", "lawd", "built", "area", "pyeong", "peak", "recent", "last",
                "drop", "jratio", "jeonse", "score", "reason", "tags", "trades6m", "parts", "scoreDetail", "complex", "ath"]
        return {k: u.get(k) for k in keys}

    recommend = {
        "date": today.isoformat(),
        "top": [dict(light(u), rank=i + 1, isNew=(bool(prev_ids) and u["id"] not in prev_ids)) for i, u in enumerate(top)],
        "newCount": sum(1 for u in top if prev_ids and u["id"] not in prev_ids) if prev_ids else None,
        "drop10": sum(1 for u in candidates if (u["drop"] or 0) >= 0.10),
        "drop20": sum(1 for u in candidates if (u["drop"] or 0) >= 0.20),
        "candidateCount": len(candidates), "unitCount": all_units, "smallExcluded": small_out,
        "kapt": bool(kidx),
        "filters": f, "weights": cfg["weights"], "regions": [r["name"] for r in cfg["regions"]],
    }
    rone_path = ROOT / "data" / "rone.json"
    meta = {
        "updated": now.strftime("%Y-%m-%d %H:%M"), "sample": sample, "lastMonth": last_ym,
        "hasRone": rone_path.exists() and not sample,
    }
    (SITE_DATA / "recommend.json").write_text(json.dumps(recommend, ensure_ascii=False), encoding="utf-8")
    (SITE_DATA / "units.json").write_text(json.dumps([light(u) for u in ranked], ensure_ascii=False), encoding="utf-8")
    (SITE_DATA / "regions.json").write_text(json.dumps(list(regions.values()), ensure_ascii=False), encoding="utf-8")
    idx = ROOT / "site" / "index.html"
    ver = now.strftime("%Y%m%d%H%M")
    html = re.sub(r'(app\.js|style\.css)(\?v=\d+)?"', lambda m: f'{m.group(1)}?v={ver}"', idx.read_text(encoding="utf-8"))
    idx.write_text(html, encoding="utf-8")
    (SITE_DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    if meta["hasRone"]:
        shutil.copy(rone_path, SITE_DATA / "rone.json")
    print(f"소형 단지로 빠진 곳 {small_out}개 · K-apt {'사용' if kidx else '없음(추정)'}")
    print(f"단지·평형 {all_units}개 중 후보 {len(candidates)}개 · 추천 {len(top)}개 · {'테스트' if sample else '실'}데이터")


if __name__ == "__main__":
    main()
