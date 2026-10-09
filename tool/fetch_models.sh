#!/usr/bin/env bash
# models.lock 의 release 태그에서 tflite + classes.json 을 app/assets/models 로 받음.
# 로컬에서는 `gh auth login` 후 실행. CI 에서는 GH_TOKEN 환경변수 사용.
set -euo pipefail
cd "$(dirname "$0")/.."

tag=$(grep -E '^release:' models.lock | awk '{print $2}')
dest=app/assets/models

if [[ -z "$tag" || "$tag" == "none" ]]; then
  echo "models.lock: release=none → 모델 없이 진행"
  exit 0
fi

echo "fetching $tag → $dest"
find "$dest" -type f ! -name .gitkeep -delete
gh release download "$tag" -D "$dest" -p '*.tflite' -p 'classes.json'
ls -lh "$dest"
