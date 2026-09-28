"""모아 둔 실거래 원자료로 사이트가 읽을 JSON 을 만들어요.

사용:  python collector/build.py            (실데이터: data/raw)
       python collector/build.py --sample   (테스트 데이터: data/sample_raw)

만드는 것 (site/data/):
  meta.json        업데이트 시각, 테스트 여부
  recommend.json   오늘의 추천 10 + 요약 숫자
  units.json       후보 단지·평형 전체 목록 (가벼운 버전)
  units/<id>.json  단지 상세 (거래 내역, 월별 흐름, 전세)
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
        return int(str(s).replace(",", "").strip())
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
    n_ok = sum(c["ok"] for c in checks)
    status = "회복 신호" if n_ok >= 3 else ("지켜보기" if n_ok == 2 else "약세")
    tone = "good" if n_ok >= 3 else ("watch" if n_ok == 2 else "weak")
    summary = {
        "good": "떨어지던 값이 멈추고 거래가 살아나는 중이에요.",
        "watch": "좋은 신호와 나쁜 신호가 섞여 있어요. 조금 더 지켜봐요.",
        "weak": "아직 가격이 약하거나 거래가 살아나지 않았어요.",
    }[tone]
    last_j = next((s["jratio"] for s in reversed(series) if s["jratio"]), None)
    return {
        "name": name, "status": status, "tone": tone, "okCount": n_ok, "summary": summary,
        "checks": checks, "series": series,
        "peak": {"ym": peak_m, "ppm": round(peak_v) if peak_v else None},
        "now": {"ppm": round(p_now) if p_now else None, "fromPeak": from_peak, "jratio": last_j,
                "volChange": vol_chg, "priceChange": p_chg, "jeonseChange": j_chg},
    }


# ---------- 단지·평형 분석 ----------
def analyze_unit(ts, rents_by_match, cfg, today):
    f = cfg["filters"]
    ts = sorted(ts, key=lambda t: t["date"])
    valid = [t for t in ts if not t["cancelled"]
             and not (f["exclude_direct_deal"] and t["direct"])
             and t["floor"] > f["exclude_low_floor_upto"]]
    if not valid:
        return None

    # 전고점: 앞뒤 6개월 거래 중간값보다 20% 넘게 튀는 거래는 이상치로 보고 제외
    def neighborhood_median(t):
        d = datetime.fromisoformat(t["date"])
        xs = [u["price"] for u in valid if abs((datetime.fromisoformat(u["date"]) - d).days) <= 183]
        return median(xs)
    peak = None
    for t in valid:
        nm = neighborhood_median(t)
        if nm and t["price"] <= nm * 1.2 and (peak is None or t["price"] > peak["price"]):
            peak = t

    cut6 = (today - timedelta(days=183)).isoformat()
    cut12 = (today - timedelta(days=365)).isoformat()
    cut24 = (today - timedelta(days=730)).isoformat()
    recent6 = [t["price"] for t in valid if t["date"] >= cut6]
    last = valid[-1]
    if recent6:
        recent, basis = median(recent6), f"최근 6개월 거래 {len(recent6)}건의 중간값"
    elif last["date"] >= cut12:
        recent, basis = last["price"], "최근 1년 안 마지막 거래"
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
        "trades2y": sum(1 for t in valid if t["date"] >= cut24),
        "trades6m": len(recent6),
        "jeonse": round(jeonse) if jeonse else None, "jeonseCount": len(j_list),
        "jratio": (jeonse / recent) if (jeonse and recent) else None,
        "trades": [{"d": t["date"], "p": t["price"], "f": t["floor"],
                    "x": "취소" if t["cancelled"] else ("직거래" if t["direct"] else ("저층" if t["floor"] <= f["exclude_low_floor_upto"] else ""))}
                   for t in ts],
        "monthly": [{"ym": m, "p": round(median(v))} for m, v in sorted(monthly.items())],
        "jmonthly": [{"ym": m, "p": round(median(v))} for m, v in sorted(jmonthly.items())],
    }


def score_unit(u, region, cfg, today):
    w = cfg["weights"]
    reg_cfg = next(r for r in cfg["regions"] if r["lawd_cd"] == u["lawd"])
    commute = cfg.get("commute_by_dong", {}).get(u["dong"], reg_cfg.get("commute_min", 40))
    school = cfg.get("school_by_dong", {}).get(u["dong"], 3)
    age = today.year - (u["built"] or today.year)
    parts = {
        "price_drop": clamp((u["drop"] or 0) / 0.25),
        "growth": clamp(0.7 * region["okCount"] / 4 + 0.3 * clamp(((u["jratio"] or 0.45) - 0.4) / 0.3)),
        "commute": clamp((60 - commute) / 45),
        "school": clamp((school - 1) / 4),
        "condition": clamp(1 - age / 40),
    }
    total = sum(w[k] * v for k, v in parts.items())
    scale = sum(w[k] for k in parts) or 1
    score = round(total / scale * 100)

    lines = {
        "price_drop": f"최고가보다 {round((u['drop'] or 0) * 100)}% 싸게 거래되고 있어요",
        "growth": f"{region['name']} 흐름이 지금 '{region['status']}' 상태예요",
        "commute": f"출퇴근 약 {commute}분",
        "school": "학군 좋은 동네로 표시해 둔 곳이에요",
        "condition": f"{u['built']}년 준공으로 비교적 새 아파트예요",
    }
    top = sorted(parts, key=lambda k: w[k] * parts[k], reverse=True)
    reason = lines[top[0]] + (". " + lines[top[1]] if len(top) > 1 else "") + "."

    tags = []
    d = round((u["drop"] or 0) * 100)
    if d >= 20:
        tags.append("전고점 20%↓")
    elif d >= 10:
        tags.append("전고점 10%↓")
    if u["trades6m"] >= 4:
        tags.append("거래 활발")
    if u["jratio"] and u["jratio"] >= 0.6:
        tags.append(f"전세가율 {round(u['jratio'] * 100)}%")
    if age <= 10:
        tags.append("신축급")
    elif age >= 30:
        tags.append("준공 30년+ (재건축 연한)")
    return score, reason, tags, {k: round(v, 2) for k, v in parts.items()}, commute


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
    regions, candidates, all_units = {}, [], 0
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
        groups = defaultdict(list)
        for t in trades:
            if f["area_min_m2"] <= t["area"] <= f["area_max_m2"]:
                groups[(t["key"], t["bucket"])].append(t)
        for ts in groups.values():
            u = analyze_unit(ts, rents_by_match, cfg, today)
            if not u:
                continue
            all_units += 1
            ok = (u["recent"] and u["peak"] and u["recent"] <= f["max_price_manwon"]
                  and u["trades2y"] >= f["min_trades_2y"])
            u["region"] = reg["name"]
            if ok:
                u["score"], u["reason"], u["tags"], u["parts"], u["commute"] = score_unit(u, region, cfg, today)
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
                "drop", "jratio", "jeonse", "score", "reason", "tags", "trades6m", "commute", "parts"]
        return {k: u.get(k) for k in keys}

    recommend = {
        "date": today.isoformat(),
        "top": [dict(light(u), rank=i + 1, isNew=(bool(prev_ids) and u["id"] not in prev_ids)) for i, u in enumerate(top)],
        "newCount": sum(1 for u in top if prev_ids and u["id"] not in prev_ids) if prev_ids else None,
        "drop10": sum(1 for u in candidates if (u["drop"] or 0) >= 0.10),
        "drop20": sum(1 for u in candidates if (u["drop"] or 0) >= 0.20),
        "candidateCount": len(candidates), "unitCount": all_units,
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
    (SITE_DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    if meta["hasRone"]:
        shutil.copy(rone_path, SITE_DATA / "rone.json")
    print(f"단지·평형 {all_units}개 중 후보 {len(candidates)}개 · 추천 {len(top)}개 · {'테스트' if sample else '실'}데이터")


if __name__ == "__main__":
    main()
