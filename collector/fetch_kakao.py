"""(선택) 카카오 지도 API로 단지 위치, 가까운 초등학교, 가까운 지하철역을 찾아 data/kakao.json 에 저장.

- 인증키: 환경변수 KAKAO_REST_KEY (developers.kakao.com 의 REST API 키, '카카오맵' 사용 설정 필요)
- 한 번 찾은 단지는 다시 찾지 않아요 (새 단지만 찾음).
- 키가 없으면 건너뛰고, 사이트는 초품아를 '확인 전'으로 둬요.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "kakao.json"
API = "https://dapi.kakao.com/v2/local/"


def get(path, params, key):
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # 키 오류·카카오맵 미설정 등은 이유를 보여줌
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")


def nearest(key, x, y, code, radius, name_has=None):
    d = get("search/category.json", {"category_group_code": code, "x": x, "y": y, "radius": radius, "sort": "distance", "size": 15}, key)
    for p in d.get("documents", []):
        if name_has and name_has not in p.get("place_name", ""):
            continue
        return {"name": p.get("place_name"), "m": int(p.get("distance") or 0)}
    return None


def count_places(key, x, y, code, radius):
    d = get("search/category.json", {"category_group_code": code, "x": x, "y": y, "radius": radius, "size": 1}, key)
    return int(d.get("meta", {}).get("total_count") or 0)


def main():
    key = os.environ.get("KAKAO_REST_KEY", "").strip()
    if not key:
        print("KAKAO_REST_KEY 없음 · 초품아·역 거리 찾기는 건너뜀")
        return
    kapt_p = ROOT / "data" / "kapt.json"
    if not kapt_p.exists():
        print("단지 정보(kapt.json)가 없어 건너뜀")
        return
    kapt = json.loads(kapt_p.read_text(encoding="utf-8"))
    kapt.pop("__fetched__", None)
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    done = errors = 0
    for code, k in kapt.items():
        if code in out:
            o = out[code]
            # 예전에 찾은 단지에 학원 수가 없으면 학원 수만 추가로 셈
            if o.get("x") and "academies" not in o:
                try:
                    o["academies"] = count_places(key, o["x"], o["y"], "AC5", 1000)
                    done += 1
                except Exception as e:
                    errors += 1
                    if errors >= 5 and done == 0:
                        print(f"카카오 API 사용 불가 ({e})")
                        break
                time.sleep(0.03)
            continue
        addr = k.get("doroJuso") or k.get("kaptAddr")
        if not addr:
            continue
        try:
            g = get("search/address.json", {"query": addr, "size": 1}, key).get("documents", [])
            if not g:
                out[code] = {"found": False}
                continue
            x, y = g[0]["x"], g[0]["y"]
            out[code] = {
                "x": x, "y": y,
                "elementary": nearest(key, x, y, "SC4", 1000, "초등학교"),
                "station": nearest(key, x, y, "SW8", 1500),
                "academies": count_places(key, x, y, "AC5", 1000),
            }
            done += 1
        except Exception as e:
            errors += 1
            if errors >= 5 and done == 0:
                print(f"카카오 API 사용 불가 ({e}) · 키와 '카카오맵' 사용 설정을 확인해 주세요")
                break
        time.sleep(0.05)
        if done and done % 100 == 0:
            OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"카카오 위치 정보 {done}개 새로 저장 · 전체 {len(out)}개 · 오류 {errors}건")


if __name__ == "__main__":
    main()
