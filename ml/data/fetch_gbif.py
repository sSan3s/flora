"""GBIF 에서 종별 이미지와 분류 계층을 받아온다.

출력 ($DATA_DIR)
  images/<gbif_key>/<occurrence_id>_<n>.jpg   긴 변 512px
  manifests/<gbif_key>.json                   종 단위 체크포인트 (분류 + 이미지 목록)
  images.csv                                  path,key,occurrence_id,license,country
  taxonomy.json                               종별 계/문/강/목/과/속/종

사용
  python ml/data/fetch_gbif.py --species ml/data/species_kr.csv --data-dir /srv/flora/data

중간에 끊겨도 같은 명령을 다시 실행하면 이어서 받는다.
  - manifest 가 있는 종은 건너뜀
  - 이미 받은 이미지 파일은 다시 받지 않음
  - 한 종이 실패해도 다음 종으로 넘어가고, 끝에 실패 목록을 출력 (exit 1)
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
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

API = "https://api.gbif.org/v1"
RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
FIELDS = ["path", "key", "occurrence_id", "license", "country"]


def make_session(workers: int) -> requests.Session:
    # 연결 끊김(RemoteDisconnected), 타임아웃, 429/5xx 를 1, 2, 4, 8 ... 초 간격으로 재시도
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=max(10, workers * 2))
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers["User-Agent"] = "flora-dataset-builder"
    return s


SESSION = make_session(8)


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
            # 표본(압착 식물) 사진 제외. 현장 관찰 사진만
            "basisOfRecord": "HUMAN_OBSERVATION",
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
        # 임시 파일에 쓰고 이름 변경. 저장 중에 끊겨도 깨진 jpg 가 남지 않음
        tmp = dst.with_suffix(".part")
        im.save(tmp, format="JPEG", quality=90)
        tmp.replace(dst)
        return True
    except Exception:
        return False


def fetch_species(sp: dict, data: Path, licenses: list[str], args) -> dict | None:
    """한 종을 받아 manifest 내용을 돌려준다. 매칭 실패면 None."""
    m = match_species(sp["scientific_name"])
    if m is None:
        return None
    key = m["usageKey"]
    taxon = {
        "key": key,
        "scientific": m.get("canonicalName", sp["scientific_name"]),
        "korean": sp["korean_name"],
        **{r: m.get(r) for r in RANKS},
    }

    # 한국 관찰을 먼저, 모자라면 전 세계에서 채움
    jobs, seen = [], set()
    for country in ("KR", None):
        need = args.max_per_species - len(jobs)
        if need <= 0:
            break
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

    rows = [
        {
            "path": str(dst.relative_to(data)),
            "key": key,
            "occurrence_id": occ["key"],
            "license": occ.get("license", ""),
            "country": occ.get("countryCode", ""),
        }
        for (_, dst, occ), success in zip(jobs, ok, strict=True)
        if success
    ]
    return {"taxon": taxon, "rows": rows, "requested": len(jobs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--species", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--max-per-species", type=int, default=600)
    ap.add_argument("--allow-nc", action="store_true", help="CC BY-NC 이미지 포함")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--refresh", action="store_true", help="manifest 를 무시하고 전 종 다시 조회")
    args = ap.parse_args()

    data = Path(args.data_dir)
    manifests = data / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    licenses = ["CC0_1_0", "CC_BY_4_0"] + (["CC_BY_NC_4_0"] if args.allow_nc else [])

    with open(args.species, encoding="utf-8") as f:
        species = list(csv.DictReader(f))
    print(f"종 목록 {len(species)}개: {args.species}")

    # manifest 파일명은 GBIF key 라서, 학명 → manifest 대응표를 따로 둔다
    index_path = manifests / "_index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}

    done, skipped, failed = [], [], []
    for n, sp in enumerate(species, 1):
        name = sp["scientific_name"]
        prev = index.get(name)
        if prev and not args.refresh and (manifests / f"{prev}.json").exists():
            done.append(prev)
            continue
        try:
            result = fetch_species(sp, data, licenses, args)
        except Exception as e:
            # 재시도까지 다 실패한 경우. 다음 종으로 넘어가고 끝에 모아서 보고
            print(f"[fail] {n}/{len(species)} {sp['korean_name']} ({name}): {e}")
            failed.append(sp)
            continue
        if result is None:
            print(f"[skip] 매칭 실패: {name}")
            skipped.append(sp)
            continue
        key = result["taxon"]["key"]
        (manifests / f"{key}.json").write_text(json.dumps(result, ensure_ascii=False))
        index[name] = key
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
        done.append(key)
        print(f"[ok] {n}/{len(species)} {sp['korean_name']}: {len(result['rows'])}장")

    # 지금 종 목록에 있는 것만 모아서 최종 파일 생성 (목록에서 뺀 종의 manifest 는 무시)
    taxonomy, rows = [], []
    for key in dict.fromkeys(done):
        m = json.loads((manifests / f"{key}.json").read_text())
        taxonomy.append(m["taxon"])
        rows.extend(m["rows"])

    with open(data / "images.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    (data / "taxonomy.json").write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2))

    print(f"{len(taxonomy)}종, {len(rows)}장 → {data}")
    for sp in skipped:
        print(f"[skip] {sp['korean_name']} ({sp['scientific_name']})")
    if failed:
        print(f"실패 {len(failed)}종. 같은 명령을 다시 실행하면 이 종들만 이어서 받음:")
        for sp in failed:
            print(f"  {sp['korean_name']} ({sp['scientific_name']})")
        raise SystemExit(1)


if __name__ == "__main__":
    main()