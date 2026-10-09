"""test split 평가 → RUN_DIR/metrics.json"""

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from common import FlowerDataset, build_transforms, key_index, load_checkpoint, load_taxonomy


@torch.no_grad()
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()

    run, data = Path(args.run), Path(args.data_dir)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, ckpt = load_checkpoint(run, device)
    cfg = ckpt["cfg"]
    taxonomy = load_taxonomy(data)
    n = len(taxonomy)

    ds = FlowerDataset(data, "test", key_index(taxonomy), build_transforms(cfg["img_size"], False))
    dl = DataLoader(ds, 64, num_workers=cfg["num_workers"])

    top1 = top5 = 0
    per_hit, per_total = torch.zeros(n), torch.zeros(n)
    k = min(5, n)
    for x, y in dl:
        logits = model(x.to(device)).cpu()
        pred = logits.topk(k, 1).indices
        hit1 = pred[:, 0] == y
        top1 += hit1.sum().item()
        top5 += (pred == y[:, None]).any(1).sum().item()
        per_total += torch.bincount(y, minlength=n).float()
        per_hit += torch.bincount(y[hit1], minlength=n).float()

    total = len(ds)
    per_acc = (per_hit / per_total.clamp(min=1)).tolist()
    worst = sorted(range(n), key=lambda i: per_acc[i])[:10]
    metrics = {
        "model": cfg["model"],
        "num_classes": n,
        "test_images": total,
        "best_epoch": ckpt["epoch"],
        "val_top1": round(ckpt["val_top1"], 4),
        "test_top1": round(top1 / total, 4),
        "test_top5": round(top5 / total, 4),
        "worst_classes": [
            {"korean": taxonomy[i]["korean"], "acc": round(per_acc[i], 3)} for i in worst
        ],
    }
    (run / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
