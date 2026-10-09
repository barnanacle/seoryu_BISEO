# 개발·설치 검증

이 폴더는 수강생 운영 프로젝트에 설치하지 않습니다. 이전 루트 `tests/`의 내용을 `dev/tests/`로 옮겼습니다.

저장소 루트에서 실행합니다.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 dev/tests/test_runtime_install.py
PYTHONDONTWRITEBYTECODE=1 python3 dev/tests/test_pii_rules.py
```

Windows에서는 실행 가능한 Python 3 명령(`py -3` 또는 `python`)을 사용합니다. 테스트는 임시 폴더의 합성 자료만 사용하고, 설치 파일 대조·기존 파일 보존·문서/개발 자료 제외·개인 자료 읽기 제외를 확인합니다.

의견서 작성기와 서식 엔진의 자체 테스트는 각 도구의 내부에 유지했습니다. 도구별 실제 실행 환경 점검·회귀 검증에 쓰이며, 루트 설치 테스트와는 역할이 다릅니다.

기존 수강생 폴더를 삭제하거나 덮어쓰지 않습니다. 폴더 정리는 저장소 구조 변경이며, 설치된 운영 파일의 위치는 그대로입니다.
