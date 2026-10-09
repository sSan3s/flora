#!/usr/bin/env bash
# 최초 1회. 사용법: tool/bootstrap.sh com.yourname
set -euo pipefail
cd "$(dirname "$0")/.."

org="${1:?org 필요. 예 tool/bootstrap.sh com.taehyeon}"
command -v flutter >/dev/null || { echo "flutter 가 PATH 에 없음"; exit 1; }

flutter create --org "$org" --project-name flora --platforms android,ios app

mkdir -p app/lib/core
for f in camera identify codex album missions settings; do
  mkdir -p "app/lib/features/$f"
  touch "app/lib/features/$f/.gitkeep"
done
mkdir -p app/assets/models && touch app/assets/models/.gitkeep

if [[ -f tool/templates/ExportOptions.plist ]]; then
  cp tool/templates/ExportOptions.plist app/ios/ExportOptions.plist
fi

v=$(flutter --version --machine | python3 -c 'import sys,json;print(json.load(sys.stdin)["frameworkVersion"])')

cat <<MSG

다음 수동 작업
1. app/pubspec.yaml
   environment:
     flutter: $v          # 정확한 버전으로 고정. CI 가 읽음
   flutter:
     assets:
       - assets/models/
2. 의존성 (필요할 때 추가)
   cd app && flutter pub add camera geolocator geocoding tflite_flutter image \\
     flutter_riverpod go_router drift sqlite3_flutter_libs path_provider
   flutter pub add --dev drift_dev build_runner
3. android/app/build.gradle 에 release signingConfig (README 3번)
4. Xcode 에서 Runner 타깃 Signing 을 Manual + App Store 프로파일로 (README 5번)
MSG
