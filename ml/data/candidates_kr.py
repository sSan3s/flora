"""한국 사진 관찰 기록이 많은 꽃식물 후보를 GBIF 에서 뽑는다.

1) 후보 뽑기
  python ml/data/candidates_kr.py pick --out ml/data/candidates_kr.csv --top 300

  candidates_kr.csv 를 열어 keep 열을 0/1 로 고른다. 국명이 비어 있으면 채운다.
  상위 120 개는 keep=1 로 미리 표시됨 (--keep 으로 조정).

2) 학습용 종 목록으로 변환
  python ml/data/candidates_kr.py emit --src ml/data/candidates_kr.csv --out ml/data/species_kr.csv

count 는 한국 사진 관찰 건수(이미지 장수가 아님). 수집 때는 해외 관찰로 부족분을 채운다.
"""

import argparse
import csv
import sys
import time

import requests

API = "https://api.gbif.org/v1"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "flora-dataset-builder"

# 꽃 사진 식별 앱에 안 맞는 과. 풀·사초·골풀류, 꽃이 눈에 안 띄는 나무류
EXCLUDE_FAMILIES = {
    "Poaceae",
    "Cyperaceae",
    "Juncaceae",
    "Typhaceae",
    "Fagaceae",
    "Betulaceae",
    "Juglandaceae",
    "Ulmaceae",
    "Salicaceae",
    "Moraceae",
    "Platanaceae",
    "Cannabaceae",
    "Sapindaceae",
    "Pinaceae",
    "Cupressaceae",
}

FIELDS = [
    "keep",
    "rank",
    "kr_obs",
    "species_key",
    "scientific_name",
    "korean_name",
    "family",
    "order",
]


def get(path: str, **params) -> dict:
    for attempt in range(4):
        r = SESSION.get(f"{API}{path}", params=params, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2**attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def class_key(name: str) -> int:
    m = get("/species/match", name=name, rank="CLASS", kingdom="Plantae")
    if m.get("rank") != "CLASS" or "usageKey" not in m:
        sys.exit(f"분류 키를 못 찾음: {name}")
    return m["usageKey"]


def korean_name(key: int) -> str:
    names = get(f"/species/{key}/vernacularNames", limit=200).get("results", [])
    kor = [n["vernacularName"] for n in names if n.get("language") in ("kor", "ko")]
    # 같은 이름이 출처별로 중복되는 경우가 많아 가장 흔한 것을 고른다
    return max(set(kor), key=kor.count) if kor else ""


def pick(args):
    taxa = [class_key("Magnoliopsida"), class_key("Liliopsida")]
    facet = get(
        "/occurrence/search",
        country="KR",
        mediaType="StillImage",
        basisOfRecord="HUMAN_OBSERVATION",
        taxonKey=taxa,
        limit=0,
        facet="speciesKey",
        facetLimit=args.top * 2,
    )
    counts = facet["facets"][0]["counts"] if facet.get("facets") else []
    print(f"한국 관찰 상위 종 {len(counts)}개 조회, 상세 정보 수집 중")

    rows = []
    for c in counts:
        key = int(c["name"])
        sp = get(f"/species/{key}")
        if sp.get("rank") != "SPECIES" or sp.get("family") in EXCLUDE_FAMILIES:
            continue
        rows.append(
            {
                "kr_obs": c["count"],
                "species_key": key,
                "scientific_name": sp.get("canonicalName", sp.get("scientificName", "")),
                "korean_name": korean_name(key),
                "family": sp.get("family", ""),
                "order": sp.get("order", ""),
            }
        )
        time.sleep(0.1)
        if len(rows) >= args.top:
            break

    rows.sort(key=lambda r: r["kr_obs"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["keep"] = 1 if i <= args.keep else 0

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    missing = sum(1 for r in rows if not r["korean_name"])
    print(f"{len(rows)}종 → {args.out} (keep=1: {min(args.keep, len(rows))}, 국명 빈칸: {missing})")


def emit(args):
    with open(args.src, encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["keep"].strip() == "1"]

    blank = [r["scientific_name"] for r in rows if not r["korean_name"].strip()]
    if blank and not args.allow_blank:
        print("국명이 빈 종이 있음. 채우거나 keep=0 으로 바꾼 뒤 다시 실행:")
        for name in blank:
            print(f"  {name}")
        sys.exit(1)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scientific_name", "korean_name"])
        for r in rows:
            w.writerow([r["scientific_name"], r["korean_name"].strip() or r["scientific_name"]])
    print(f"{len(rows)}종 → {args.out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pick")
    p.add_argument("--out", default="ml/data/candidates_kr.csv")
    p.add_argument("--top", type=int, default=300)
    p.add_argument("--keep", type=int, default=120)
    p.set_defaults(func=pick)

    e = sub.add_parser("emit")
    e.add_argument("--src", default="ml/data/candidates_kr.csv")
    e.add_argument("--out", default="ml/data/species_kr.csv")
    e.add_argument("--allow-blank", action="store_true", help="국명 빈칸이면 학명으로 대체")
    e.set_defaults(func=emit)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
