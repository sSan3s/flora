"""train / eval / export 공용."""

import csv
import json
import random
from pathlib import Path

import numpy as np
import timm
import torch
import yaml
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms as T

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def load_cfg(path: str | Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def seed_all(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_taxonomy(data_dir: Path) -> list[dict]:
    return json.loads((data_dir / "splits" / "taxonomy.json").read_text())


def build_transforms(size: int, train: bool):
    if train:
        # 꽃은 색이 종 구분 단서라 hue 는 건드리지 않음
        return T.Compose(
            [
                T.RandomResizedCrop(size, scale=(0.4, 1.0)),
                T.RandomHorizontalFlip(),
                T.RandomRotation(15),
                T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
                T.ToTensor(),
                T.Normalize(MEAN, STD),
            ]
        )
    return T.Compose(
        [
            T.Resize(int(size * 1.14)),
            T.CenterCrop(size),
            T.ToTensor(),
            T.Normalize(MEAN, STD),
        ]
    )


class FlowerDataset(Dataset):
    def __init__(self, data_dir: Path, split: str, key2idx: dict[str, int], transform):
        self.data_dir = data_dir
        self.transform = transform
        with open(data_dir / "splits" / f"{split}.csv", encoding="utf-8") as f:
            self.items = [(r["path"], key2idx[r["key"]]) for r in csv.DictReader(f)]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        path, label = self.items[i]
        img = Image.open(self.data_dir / path).convert("RGB")
        return self.transform(img), label


def build_model(cfg: dict, num_classes: int, pretrained: bool | None = None):
    pre = cfg.get("pretrained", True) if pretrained is None else pretrained
    return timm.create_model(cfg["model"], pretrained=pre, num_classes=num_classes)


def key_index(taxonomy: list[dict]) -> dict[str, int]:
    return {str(t["key"]): i for i, t in enumerate(taxonomy)}


def load_checkpoint(run: Path, device="cpu"):
    ckpt = torch.load(run / "best.pt", map_location=device, weights_only=False)
    model = build_model(ckpt["cfg"], ckpt["num_classes"], pretrained=False)
    model.load_state_dict(ckpt["state_dict"])
    return model.to(device).eval(), ckpt


def write_classes_json(run: Path, taxonomy: list[dict], cfg: dict):
    """앱이 읽는 메타. 입력 규격 + 인덱스별 학명/국명/분류 계층."""
    ranks = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
    doc = {
        "input": {"size": cfg["img_size"], "layout": "NHWC", "dtype": "float32", "range": "0-255"},
        "output": "softmax",
        "classes": [
            {
                "index": i,
                "key": t["key"],
                "scientific": t["scientific"],
                "korean": t["korean"],
                "taxonomy": {r: t.get(r) for r in ranks},
            }
            for i, t in enumerate(taxonomy)
        ],
    }
    (run / "classes.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
