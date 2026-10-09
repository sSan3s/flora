"""python ml/train.py --config ml/configs/baseline.yaml --data-dir /srv/flora/data --out RUN_DIR"""

import argparse
import csv
import math
import shutil
import time
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from common import (
    FlowerDataset,
    build_model,
    build_transforms,
    key_index,
    load_cfg,
    load_taxonomy,
    seed_all,
    write_classes_json,
)


def lr_at(epoch: float, cfg: dict) -> float:
    w, total = cfg["warmup_epochs"], cfg["epochs"]
    if epoch < w:
        return cfg["lr"] * epoch / w
    p = (epoch - w) / max(1, total - w)
    return cfg["lr"] * 0.5 * (1 + math.cos(math.pi * p))


@torch.no_grad()
def evaluate(model, loader, device) -> float:
    model.eval()
    correct = total = 0
    for x, y in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        correct += (model(x).argmax(1) == y).sum().item()
        total += y.numel()
    return correct / max(1, total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    cfg = load_cfg(args.config)
    data, run = Path(args.data_dir), Path(args.out)
    run.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.config, run / "config.yaml")
    seed_all(cfg["seed"])

    taxonomy = load_taxonomy(data)
    k2i = key_index(taxonomy)
    write_classes_json(run, taxonomy, cfg)

    size, bs, nw = cfg["img_size"], cfg["batch_size"], cfg["num_workers"]
    train_ds = FlowerDataset(data, "train", k2i, build_transforms(size, True))
    val_ds = FlowerDataset(data, "val", k2i, build_transforms(size, False))
    train_dl = DataLoader(
        train_ds, bs, shuffle=True, num_workers=nw, pin_memory=True, drop_last=True
    )
    val_dl = DataLoader(val_ds, bs * 2, num_workers=nw, pin_memory=True)
    print(f"classes={len(taxonomy)} train={len(train_ds)} val={len(val_ds)}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model(cfg, len(taxonomy)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    crit = nn.CrossEntropyLoss(label_smoothing=cfg["label_smoothing"])
    use_amp = cfg.get("amp", False) and device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    best, stale = 0.0, 0
    log = open(run / "train_log.csv", "w", newline="")
    w = csv.writer(log)
    w.writerow(["epoch", "loss", "val_top1", "lr", "sec"])

    steps = len(train_dl)
    for epoch in range(cfg["epochs"]):
        model.train()
        t0, running = time.time(), 0.0
        for i, (x, y) in enumerate(train_dl):
            for g in opt.param_groups:
                g["lr"] = lr_at(epoch + i / steps, cfg)
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                loss = crit(model(x), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            running += loss.item()

        acc = evaluate(model, val_dl, device)
        lr = opt.param_groups[0]["lr"]
        sec = time.time() - t0
        w.writerow([epoch, f"{running / steps:.4f}", f"{acc:.4f}", f"{lr:.2e}", f"{sec:.0f}"])
        log.flush()
        print(f"[{epoch:02d}] loss={running / steps:.4f} val_top1={acc:.4f} ({sec:.0f}s)")

        if acc > best:
            best, stale = acc, 0
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "cfg": cfg,
                    "num_classes": len(taxonomy),
                    "epoch": epoch,
                    "val_top1": acc,
                },
                run / "best.pt",
            )
        else:
            stale += 1
            if stale >= cfg["patience"]:
                print(f"early stop at {epoch}")
                break

    log.close()
    print(f"best val_top1={best:.4f}")


if __name__ == "__main__":
    main()
