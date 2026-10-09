"""images.csv → splits/{train,val,test}.csv

관찰(occurrence) 단위로 나눈다. 같은 관찰의 사진이 train/test 에 갈라지면 점수가 부풀려짐.
이미지가 min-images 미만인 종은 제외하고 splits/taxonomy.json 에 남은 종만 기록.
"""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--min-images", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    data = Path(args.data_dir)
    rng = random.Random(args.seed)

    by_key: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    with open(data / "images.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_key[row["key"]][row["occurrence_id"]].append(row)

    taxonomy = {str(t["key"]): t for t in json.loads((data / "taxonomy.json").read_text())}
    splits = {"train": [], "val": [], "test": []}
    kept, dropped = [], []

    for key, occs in by_key.items():
        n = sum(len(v) for v in occs.values())
        if n < args.min_images:
            dropped.append((taxonomy[key]["korean"], n))
            continue
        kept.append(taxonomy[key])
        groups = list(occs.values())
        rng.shuffle(groups)
        cut1, cut2 = int(len(groups) * 0.8), int(len(groups) * 0.9)
        for name, part in (
            ("train", groups[:cut1]),
            ("val", groups[cut1:cut2]),
            ("test", groups[cut2:]),
        ):
            for g in part:
                splits[name].extend(g)

    out = data / "splits"
    out.mkdir(exist_ok=True)
    for name, rows in splits.items():
        with open(out / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["path", "key"])
            w.writeheader()
            w.writerows({"path": r["path"], "key": r["key"]} for r in rows)
    kept.sort(key=lambda t: t["key"])
    (out / "taxonomy.json").write_text(json.dumps(kept, ensure_ascii=False, indent=2))

    print({k: len(v) for k, v in splits.items()}, f"종 {len(kept)}개 사용")
    for name, n in dropped:
        print(f"[drop] {name}: {n}장")


if __name__ == "__main__":
    main()
