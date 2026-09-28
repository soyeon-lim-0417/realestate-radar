"""인증키 없이 화면을 확인하기 위한 '테스트 데이터' 생성기.

국토부 API 응답과 똑같은 모양(필드 이름·문자열 형식)으로 data/sample_raw 에 만들어요.
단지 이름과 가격은 모두 가짜예요.
"""
import json
import math
import random
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample_raw"
random.seed(7)

DONGS = {
    "11440": ["아현동", "공덕동", "도화동", "염리동", "대흥동", "신공덕동", "상암동", "망원동"],
    "11200": ["행당동", "금호동", "옥수동", "성수동", "하왕십리동", "응봉동", "마장동"],
    "11560": ["당산동", "문래동", "영등포동", "양평동", "신길동", "대림동", "여의도동"],
}
WORDS = ["푸른숲", "하늘채움", "리버힐", "센트럴", "솔숲", "한강빛", "역앞마을", "새뜰", "언덕마을", "강변마을", "철길숲", "파크뷰"]
# 구별 시장 흐름: (2021 고점 상승폭, 2023 저점 하락폭, 지금까지 회복폭)
MARKET = {"11440": (0.48, 0.24, 0.13), "11200": (0.52, 0.26, 0.16), "11560": (0.40, 0.22, 0.05)}


def market_index(lawd, t):
    """t = 2019.0 부터의 연 단위 시간. 1.0 이 2019년 초 가격."""
    up, down, rec = MARKET[lawd]
    peak_t, trough_t = 2.8, 4.3
    if t <= peak_t:
        return 1 + up * (t / peak_t) ** 1.3
    peak = 1 + up
    if t <= trough_t:
        return peak * (1 - down * math.sin((t - peak_t) / (trough_t - peak_t) * math.pi / 2))
    trough = peak * (1 - down)
    return trough * (1 + rec * min(1, (t - trough_t) / 3.4) ** 0.8)


def won(v):
    return f"{int(round(v / 100.0)) * 100:,}"


def main():
    today = date.today()
    for lawd, dongs in DONGS.items():
        complexes = []
        for i in range(14):
            dong = random.choice(dongs)
            built = random.choice([1994, 1997, 1998, 2001, 2003, 2006, 2009, 2012, 2015, 2018])
            complexes.append({
                "aptNm": f"{dong[:-1]} {random.choice(WORDS)}{'' if i % 3 else ' ' + str(i % 4 + 1) + '차'}",
                "aptSeq": f"{lawd}-{900 + i}",
                "umdNm": dong, "jibun": str(random.randint(1, 600)),
                "buildYear": str(built),
                "base59": random.uniform(5.2, 8.6) * 10000 * (1 + (built - 2000) * 0.008),
                "own": random.uniform(-0.08, 0.08),
                "liq": random.uniform(0.3, 1.2),
            })
        for kind in ("trade", "rent"):
            (OUT / kind / lawd).mkdir(parents=True, exist_ok=True)
        y, m = 2019, 1
        while (y, m) <= (today.year, today.month):
            t = (y - 2019) + (m - 1) / 12
            idx = market_index(lawd, t)
            # 거래량: 고점 전 많고, 하락기 적고, 최근 회복
            vol = 1.0 if t < 2.6 else (0.35 if t < 4.5 else 0.55 + 0.1 * min(4, t - 4.5))
            trades, rents = [], []
            for c in complexes:
                for area, mult in ((59.97, 1.0), (84.95, 1.33)):
                    n = sum(1 for _ in range(3) if random.random() < 0.28 * vol * c["liq"])
                    for _ in range(n):
                        fl = random.randint(1, 20)
                        p = c["base59"] * mult * idx * (1 + c["own"] * min(1, t / 5)) * random.uniform(0.95, 1.05)
                        if fl <= 3:
                            p *= 0.93
                        trades.append({
                            "aptDong": "", "aptNm": c["aptNm"], "aptSeq": c["aptSeq"],
                            "buildYear": c["buildYear"], "cdealType": "O" if random.random() < 0.02 else "",
                            "dealAmount": won(p), "dealDay": str(random.randint(1, 28)),
                            "dealMonth": str(m), "dealYear": str(y),
                            "dealingGbn": "직거래" if random.random() < 0.05 else "중개거래",
                            "excluUseAr": f"{area:.2f}", "floor": str(fl), "jibun": c["jibun"],
                            "sggCd": lawd, "umdNm": c["umdNm"],
                        })
                    for _ in range(sum(1 for _ in range(3) if random.random() < 0.35)):
                        ratio = 0.62 - 0.12 * max(0, min(1, (t - 1.5) / 1.5)) + 0.06 * max(0, min(1, (t - 4.5) / 3))
                        p = c["base59"] * mult * idx * ratio * random.uniform(0.94, 1.06)
                        monthly = random.random() < 0.3
                        rents.append({
                            "aptNm": c["aptNm"], "buildYear": c["buildYear"],
                            "contractTerm": "", "contractType": random.choice(["신규", "갱신"]),
                            "dealDay": str(random.randint(1, 28)), "dealMonth": str(m), "dealYear": str(y),
                            "deposit": won(p * (0.5 if monthly else 1)), "monthlyRent": str(random.randint(80, 200) if monthly else 0),
                            "exclUseAr": f"{area:.2f}", "floor": str(random.randint(1, 20)),
                            "jibun": c["jibun"], "sggCd": lawd, "umdNm": c["umdNm"],
                        })
            ym = f"{y}{m:02d}"
            (OUT / "trade" / lawd / f"{ym}.json").write_text(json.dumps(trades, ensure_ascii=False), encoding="utf-8")
            (OUT / "rent" / lawd / f"{ym}.json").write_text(json.dumps(rents, ensure_ascii=False), encoding="utf-8")
            m += 1
            if m == 13:
                y, m = y + 1, 1
    print("테스트 데이터 생성 완료 →", OUT)


if __name__ == "__main__":
    main()
