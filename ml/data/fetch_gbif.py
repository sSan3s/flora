"""GBIF 에서 종별 이미지와 분류 계층을 받아온다.

출력 ($DATA_DIR)
  images/<gbif_key>/<occurrence_id>_<n>.jpg   긴 변 512px
  images.csv                                  path,key,occurrence_id,license,country
  taxonomy.json                               종별 계/문/강/목/과/속/종

사용
  python ml/data/fetch_gbif.py --species ml/data/species_kr.csv --data-dir /srv/flora/data
"""

import argparse
import csv
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image
from tqdm import tqdm

API = "https://api.gbif.org/v1"
RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "flora-dataset-builder"


def match_species(name: str) -> dict | None:
    r = SESSION.get(f"{API}/species/match", params={"name": name, "rank": "SPECIES"}, timeout=30)
    r.raise_for_status()
    m = r.json()
    if m.get("matchType") == "NONE" or m.get("confidence", 0) < 90 or m.get("rank") != "SPECIES":
        return None
    return m


def iter_occurrences(key: int, licenses: list[str], country: str | None, need: int):
    offset = 0
    while need > 0:
        params = {
            "taxonKey": key,
            "mediaType": "StillImage",
            "limit": 300,
            "offset": offset,
            "license": licenses,
        }
        if country:
            params["country"] = country
        r = SESSION.get(f"{API}/occurrence/search", params=params, timeout=60)
        r.raise_for_status()
        page = r.json()
        for occ in page["results"]:
            yield occ
            need -= 1
            if need <= 0:
                return
        if page.get("endOfRecords", True):
            return
        offset += 300
        time.sleep(0.3)


def media_urls(occ: dict) -> list[str]:
    urls = []
    for m in occ.get("media", []):
        if m.get("type") != "StillImage" or not m.get("identifier"):
            continue
        u = m["identifier"]
        # iNaturalist 원본은 수 MB. medium 으로 받아도 학습엔 충분
        if "inaturalist" in u and "/original." in u:
            u = u.replace("/original.", "/medium.")
        urls.append(u)
    return urls[:2]  # 한 관찰당 최대 2장. 같은 개체 사진이 과대표되는 걸 막음


def download(job: tuple[str, Path]) -> bool:
    url, dst = job
    if dst.exists():
        return True
    try:
        r = SESSION.get(url, timeout=30)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((512, 512))
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, quality=90)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--max-per-species", type=int, default=400)
    ap.add_argument("--allow-nc", action="store_true", help="CC BY-NC 이미지 포함")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    data = Path(args.data_dir)
    licenses = ["CC0_1_0", "CC_BY_4_0"] + (["CC_BY_NC_4_0"] if args.allow_nc else [])

    taxonomy, rows = [], []
    with open(args.species, encoding="utf-8") as f:
        species = list(csv.DictReader(f))

    for sp in species:
        m = match_species(sp["scientific_name"])
        if m is None:
            print(f"[skip] 매칭 실패: {sp['scientific_name']}")
            continue
        key = m["usageKey"]
        taxonomy.append(
            {
                "key": key,
                "scientific": m.get("canonicalName", sp["scientific_name"]),
                "korean": sp["korean_name"],
                **{r: m.get(r) for r in RANKS},
            }
        )

        # 한국 관찰을 먼저, 모자라면 전 세계에서 채움
        jobs, seen = [], set()
        for country in ("KR", None):
            need = args.max_per_species - len(jobs)
            for occ in iter_occurrences(key, licenses, country, need):
                if occ["key"] in seen:
                    continue
                seen.add(occ["key"])
                for i, u in enumerate(media_urls(occ)):
                    dst = data / "images" / str(key) / f"{occ['key']}_{i}.jpg"
                    jobs.append((u, dst, occ))
                if len(jobs) >= args.max_per_species:
                    break

        with ThreadPoolExecutor(args.workers) as ex:
            ok = list(
                tqdm(
                    ex.map(download, [(u, d) for u, d, _ in jobs]),
                    total=len(jobs),
                    desc=sp["korean_name"],
                )
            )
        for (_, dst, occ), success in zip(jobs, ok, strict=True):
            if success:
                rows.append(
                    {
                        "path": str(dst.relative_to(data)),
                        "key": key,
                        "occurrence_id": occ["key"],
                        "license": occ.get("license", ""),
                        "country": occ.get("countryCode", ""),
                    }
                )

    data.mkdir(parents=True, exist_ok=True)
    with open(data / "images.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "key", "occurrence_id", "license", "country"])
        w.writeheader()
        w.writerows(rows)
    (data / "taxonomy.json").write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2))
    print(f"{len(taxonomy)}종, {len(rows)}장 → {data}")


if __name__ == "__main__":
    main()
