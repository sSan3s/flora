# app

이 폴더는 `tool/bootstrap.sh` 가 `flutter create` 로 채움. 수동으로 만들지 말 것.

폴더 규칙
- `lib/core/` — theme, router, local db(drift), 모델 로더(tflite_flutter), 공용 위젯
- `lib/features/<기능>/` — 한 기능의 view / state / data 를 한 폴더에
  - camera, identify, codex(도감), album, missions, settings
- `assets/models/` — CI 가 채움. 로컬 개발은 `tool/fetch_models.sh`

`pubspec.yaml` 의 `environment.flutter` 는 정확한 버전으로 고정 (CI 가 읽음).
