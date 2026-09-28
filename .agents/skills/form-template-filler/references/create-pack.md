# 서식 꾸러미 만들기

새 업무에는 일회용 작성기 대신 `tools/form_packs/<id>/`를 만듭니다. `tools/form_packs/opinion_notice_11/`(서술형 붙임)과 `cosmetics_seller_registration/`(내부 목록형 붙임)을 실제 스키마 예시로 사용합니다.

1. 공식 빈 PDF와 작성요령을 사람이 확인합니다. 법령명·조문·별지 번호·시행 상태·확인일·출처를 `guide.md`와 `pack.json`에 기록합니다. 실제 사건 식별정보를 공개 저장소에 넣지 않습니다.
2. PDF를 `form/`에 **원본 그대로** 보존하고 SHA-256을 `form_sha256`에 적습니다. 각 쪽 크기와 칸 위치를 확인합니다. 원본이 바뀌면 이전 좌표를 재사용하지 않습니다.
3. `python3 tools/form_engine/bin/propose_boxes.py form/official_form.pdf --out-dir <임시 확인 폴더>`로 칸 후보 JSON과 쪽별 번호 PNG를 만듭니다. 이 후보는 자동 확정값이 아닙니다. PNG에서 라벨·기입 칸·유의사항을 직접 대조한 뒤 `pages[].fields`에 승인한 좌표만 넣습니다. 가림 `masks`는 실제 입력 칸 영역에만 쓰고 원본 문구나 선을 지우지 않습니다.
4. `fields`에 이름·유형·필수 여부를 정의하고, 필요한 보정은 `normalization`·`transforms`의 등록된 이름으로 지정합니다. `annexes`는 서술형 `narrative`, 목록형 `list`, 없음 `none` 중에서 고릅니다. 붙임의 공식 제출 여부는 `append_to_submission`에 명시합니다. 붙임 DOCX가 없으면 `font_docx`에 글꼴 내장용 빈 템플릿을 둡니다.
5. 가상 값만 넣은 `examples/fields.sample.json`으로 `python3 tools/form_engine/bin/build.py examples/fields.sample.json --pack <id> --no-open`을 실행합니다. 공개 꾸러미 예시의 산출물은 설치 제외되는 `tools/form_engine/산출/`에, 실제 사건 입력의 산출물은 입력 JSON 옆 `산출/`에 생깁니다. 실제 사건 입력 파일은 공개 꾸러미 폴더에 두지 않습니다.
6. PDF와 DOCX를 렌더링해 모든 쪽의 선·라벨·입력값·쪽 수·빈칸·겹침을 확인합니다. 바이트 해시, 오버레이 위치, 반복 변환 검증을 통과시킵니다. 꾸러미마다 적용 범위, 출처, 칸별 작성법, 붙임과 수동 검토 한계를 `guide.md`에 씁니다.
7. `runtime_manifest.json`에 신규 파일·폴더를 등록하고 깨끗한 빈 폴더에 설치한 뒤 `install_runtime.py --verify-only`를 통과시킵니다. 실제 신청·제출 전에 행정사가 원본·사실·서명·첨부를 최종 검토합니다.

기존 처분 사전통지 상담 흐름의 `tools/opinion_writer/bin/build_pdf.py`는 호환 명령으로 유지합니다. 새 신청 계열에 그 빌더의 소명 질문지나 별지 구조를 억지로 적용하지 않습니다.
