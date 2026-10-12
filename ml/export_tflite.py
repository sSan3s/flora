"""best.pt → flower_cls.tflite + 정합성 검증.

앱 쪽 전처리를 없애려고 정규화/레이아웃 변환을 모델 안에 넣는다.
  입력  [1, S, S, 3] float32, 0~255 RGB (NHWC, 이미지 픽셀 그대로)
  출력  [1, C] softmax
검증 실패(top-1 일치율 미달, 용량 초과) 시 exit 1 → 워크플로 중단, Release 안 만들어짐.
"""

import argparse
import json
import sys
from pathlib import Path

import litert_torch
import numpy as np
import torch
from torch import nn
from torchvision import transforms as T

from common import MEAN, STD, FlowerDataset, key_index, load_checkpoint, load_taxonomy


class Deploy(nn.Module):
    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1) * 255.0)
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1) * 255.0)

    def forward(self, x):
        x = x.permute(0, 3, 1, 2)
        x = (x - self.mean) / self.std
        return torch.softmax(self.model(x), dim=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--data-dir", required=True)
    args = ap.parse_args()

    run, data = Path(args.run), Path(args.data_dir)
    model, ckpt = load_checkpoint(run, "cpu")
    cfg, ex = ckpt["cfg"], ckpt["cfg"]["export"]
    size = cfg["img_size"]

    deploy = Deploy(model).eval()
    sample = (torch.zeros(1, size, size, 3),)
    edge = litert_torch.convert(deploy, sample)
    out = run / "flower_cls.tflite"
    edge.export(str(out))
    mb = out.stat().st_size / 1e6

    # 검증용 입력은 앱과 동일하게 0~255 NHWC (정규화 없이 리사이즈/크롭만)
    raw_tf = T.Compose([T.Resize(int(size * 1.14)), T.CenterCrop(size), T.PILToTensor()])
    ds = FlowerDataset(data, "val", key_index(load_taxonomy(data)), raw_tf)
    idx = np.random.default_rng(0).permutation(len(ds))[: ex["verify_samples"]]

    agree, max_diff = 0, 0.0
    with torch.no_grad():
        for i in idx:
            x = ds[int(i)][0].permute(1, 2, 0).unsqueeze(0).float()
            p_torch = deploy(x).numpy()
            p_edge = np.asarray(edge(x))
            agree += int(p_torch.argmax() == p_edge.argmax())
            max_diff = max(max_diff, float(np.abs(p_torch - p_edge).max()))
    agreement = agree / len(idx)

    metrics_path = run / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    metrics["tflite"] = {
        "size_mb": round(mb, 2),
        "top1_agreement": round(agreement, 4),
        "max_prob_diff": round(max_diff, 5),
        "verified_on": len(idx),
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2))

    notes = [
        f"- model: `{cfg['model']}`  classes: {metrics.get('num_classes')}",
        f"- test top-1 / top-5: {metrics.get('test_top1')} / {metrics.get('test_top5')}",
        f"- tflite: {mb:.1f} MB, torch 대비 top-1 일치율 {agreement:.4f}",
    ]
    (run / "release_notes.md").write_text("\n".join(notes) + "\n")
    print("\n".join(notes))

    failed = []
    if agreement < ex["min_agreement"]:
        failed.append(f"top-1 일치율 {agreement:.4f} < {ex['min_agreement']}")
    if mb > ex["max_mb"]:
        failed.append(f"용량 {mb:.1f}MB > {ex['max_mb']}MB")
    if failed:
        print("검증 실패: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
