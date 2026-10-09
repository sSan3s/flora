# flora — 꽃 도감 앱

꽃 사진 → 온디바이스 식별 → 도감 수집. 서버 없음, 데이터는 기기에만.
Flutter 앱 + PyTorch 학습 파이프라인을 한 레포에 둔 모노레포. CI/CD는 GitHub Actions.

## 구조

```
flora/
├── app/                      Flutter (tool/bootstrap.sh 가 flutter create 로 채움)
│   ├── lib/core/             theme, router, local db, 모델 로더
│   ├── lib/features/         camera / identify / codex / album / missions / settings
│   └── assets/models/        .gitignore 대상. CI 가 models.lock 기준으로 채움
├── ml/                       학습·평가·TFLite 변환 (Python)
│   ├── configs/              실험 설정 yaml
│   ├── data/                 GBIF 수집·split 스크립트, 종 목록 (이미지는 /srv/flora/data)
│   └── common.py train.py eval.py export_tflite.py
├── tool/
│   ├── bootstrap.sh          최초 1회 셋업
│   ├── fetch_models.sh       models.lock → GitHub Release → app/assets/models
│   └── templates/            ExportOptions.plist 등
├── models.lock               앱이 번들하는 모델 릴리스 태그
└── .github/
    ├── workflows/            app-ci / app-android / app-ios / ml-train
    └── actions/setup-flutter 공통 Flutter 셋업
```

## 처음 한 번 할 일 (순서대로)

1. `tool/bootstrap.sh com.yourname` — `flutter create` + 폴더 생성
2. `app/pubspec.yaml` 의 `environment.flutter` 를 정확한 버전(예 `3.24.3`)으로 고정. CI 가 이 값을 읽어 같은 버전을 설치함
3. 안드로이드 서명
   - `keytool -genkey -v -keystore upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload`
   - `app/android/app/build.gradle` 에 `key.properties` 를 읽는 `signingConfigs.release` 추가 (Flutter 문서 "Build and release an Android app" 그대로)
   - 아래 Secrets 표의 ANDROID_* 등록
4. Play Console 에 앱 생성. **첫 AAB 는 수동 업로드** (그 뒤부터 API 업로드가 열림). 서비스 계정 만들고 JSON 을 `PLAY_SERVICE_ACCOUNT_JSON` 에
5. iOS — App Store Connect 에 앱 레코드, 배포용 인증서(.p12) 와 App Store 프로비저닝 프로파일 발급. `tool/templates/ExportOptions.plist` 의 TEAM_ID / 번들 ID / 프로파일 이름 채우고 bootstrap 재실행(복사됨). App Store Connect API 키 발급 → ASC_*
6. 학습 PC(RTX 4060)에 self-hosted runner 등록 (Settings → Actions → Runners → New self-hosted runner). 라벨 `gpu` 추가. `gh` CLI, python3-venv, NVIDIA 드라이버 설치. `sudo ./svc.sh install && sudo ./svc.sh start` 로 서비스 등록해서 부팅 시 자동 시작
   - `sudo mkdir -p /srv/flora && sudo chown $USER /srv/flora` — venv / 데이터 / 학습 산출물 위치. checkout 이 workspace 를 매번 청소해서 밖에 둠
7. 데이터 준비 (학습 PC 에서 직접, 한 번)
   ```
   python3 -m venv /srv/flora/venv && /srv/flora/venv/bin/pip install -r ml/requirements.txt
   /srv/flora/venv/bin/python ml/data/fetch_gbif.py --species ml/data/species_kr.csv --data-dir /srv/flora/data
   /srv/flora/venv/bin/python ml/data/make_splits.py --data-dir /srv/flora/data
   ```
   그 다음 Actions 에서 **ml-train** 수동 실행 (version `0.1.0`) → Release `model-v0.1.0` 생김
8. `models.lock` 의 `release:` 를 `model-v0.1.0` 으로 바꾸는 PR. app-ci 가 받아서 빌드 확인

## 워크플로

| 파일 | 트리거 | 러너 | 하는 일 |
|---|---|---|---|
| app-ci.yml | PR (app/**, models.lock) | ubuntu | format · analyze · test. secrets 없음. 3분 목표 |
| app-android.yml | main push (app/**, models.lock) | ubuntu | 모델 fetch → AAB 빌드 → Play 내부 테스트 트랙 |
| app-ios.yml | `v*` 태그 | macos | 모델 fetch → IPA 빌드 → TestFlight |
| ml-train.yml | 수동 (config, version 입력) | self-hosted `gpu` | train → eval → tflite 변환 + 정합성 검증 → Release |
| ml-ci.yml | PR (ml/**) | ubuntu | ruff lint · format |

app-android 는 repo 변수 `ANDROID_PACKAGE_NAME`, app-ios 는 `IOS_ENABLED=true` 를 등록하기 전까지 skip 됨. 스토어 준비 전에 push 해도 빨간불 안 뜸.

app-ios 는 public 레포면 GitHub macOS 러너 무료 여부 확인 후 쓰고, 아니면 맥북에 runner 등록하고 `runs-on` 을 `[self-hosted, macOS]` 로 바꿈.

## Secrets

| 이름 | 내용 |
|---|---|
| ANDROID_KEYSTORE_BASE64 | `base64 -w0 upload-keystore.jks` |
| ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD | keystore 정보 |
| PLAY_SERVICE_ACCOUNT_JSON | Play Console 서비스 계정 JSON 원문 |
| IOS_CERT_P12_BASE64 / IOS_CERT_PASSWORD | 배포 인증서 |
| IOS_PROVISION_PROFILE_BASE64 | App Store 프로비저닝 프로파일 |
| ASC_ISSUER_ID / ASC_KEY_ID / ASC_KEY_P8 | App Store Connect API 키 (p8 은 원문) |

포크 PR 에는 secrets 가 안 넘어옴. app-ci 는 secrets 에 의존하지 않게 유지.

## 브랜치

trunk-based. `main` 보호 + app-ci 필수 체크. 기능 브랜치 → PR → 머지.
앱 버전은 `pubspec.yaml` 의 semver, 빌드 번호는 `github.run_number`. 스토어 릴리스는 `v1.2.0` 태그.

## 모델 배포 흐름

```
ml-train (학습 PC GPU)
  → GitHub Release model-vX.Y.Z  (flower_cls.tflite, flower_gate.tflite, classes.json, metrics.json)
  → models.lock 의 release 값 수정 PR
  → app-ci / app-android / app-ios 가 tool/fetch_models.sh 로 받아 app/assets/models 에 넣음
  → 앱 빌드에 번들. 모델 업데이트 = 앱 업데이트 (v1)
```

모델 바이너리는 커밋하지 않음. 레포 크기도 지키고, 모델과 앱의 수명이 분리됨.
