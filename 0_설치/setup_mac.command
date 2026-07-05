#!/bin/bash
# =============================================================
#  JARVIS 지식창고 설치 도우미 (Mac용)
#
#  - 이 파일을 더블클릭하면 자동으로 실행됩니다.
#  - 사용자가 직접 입력할 것은 없습니다. 화면 안내만 읽어 주세요.
#  - 문제가 생기면: 0_설치/MAC_설치.md 5단계 + 3_사용법/FAQ_문제해결.md
#
#  하는 일 (3단계):
#   [1/3] Python(파이썬) 설치 확인
#   [2/3] 자료 변환 도구 설치 (2_도구/venv + Python 패키지)
#   [3/3] 한글(HWP) 변환기 rhwp 내려받기 (2_도구/rhwp/)
#
#  주의: set -e 는 일부러 쓰지 않습니다.
#        각 단계의 실패를 직접 확인해서 친절한 안내를 보여 주고,
#        계속 진행할지 중단할지 단계별로 판단합니다.
# =============================================================

# ---- 창을 닫기 전에 사용자가 메시지를 읽을 수 있게 기다리는 함수 ----
wait_key_and_exit() {
    echo ""
    read -n 1 -s -r -p "아무 키나 누르면 창이 닫힙니다. "
    echo ""
    exit "$1"
}

# ---- 공통 준비: 이 스크립트(0_설치/) 위치 기준으로 패킷 폴더 찾기 ----
# 더블클릭으로 실행하면 현재 위치가 홈 폴더가 되므로,
# 반드시 스크립트 자신의 경로를 기준으로 잡아야 합니다.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$SCRIPT_DIR/../2_도구"
FAIL=0   # 실패한 단계가 하나라도 있으면 1

echo ""
echo "============================================"
echo "  JARVIS 지식창고 설치를 시작합니다"
echo "  (창을 닫지 말고 잠시 기다려 주세요)"
echo "============================================"
echo ""

# 2_도구 폴더가 없으면 클론 폴더 일부만 복사해 실행한 것 → 진행 불가 (클론 폴더 통째로 유지)
if [ ! -d "$TOOLS_DIR" ]; then
    echo "❌ '2_도구' 폴더를 찾지 못했습니다."
    echo "   install_JAARVIS 폴더 전체를 통째로 둔 상태에서,"
    echo "   그 안의 0_설치/setup_mac.command 를 실행해야 합니다."
    echo "   (도움말: 3_사용법/FAQ_문제해결.md)"
    wait_key_and_exit 1
fi

# -------------------------------------------------------------
# [1/3] Python 확인
# -------------------------------------------------------------
echo "[1/3] Python(파이썬)이 설치되어 있는지 확인합니다..."

# python.org 공식 인스톨러가 설치하는 위치를 먼저 찾고,
# 없으면 시스템에 등록된 python3 를 사용합니다.
PYTHON_BIN=""
for CAND in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
    # 3.11 이상을 통과한 후보만 채택 — 예전에 설치한 3.8/3.9가 글롭 사전순 마지막에 와도
    # (3.9 > 3.14) 구버전이 선택되는 일을 막는다.
    if [ -x "$CAND" ] && "$CAND" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        PYTHON_BIN="$CAND"
    fi
done
if [ -z "$PYTHON_BIN" ] && command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
fi

# Python 이 아예 없으면: 설치 방법을 안내하고 여기서 중단 (계속해도 의미 없음)
if [ -z "$PYTHON_BIN" ]; then
    echo ""
    echo "❌ Python 이 설치되어 있지 않습니다."
    echo "   아래 순서로 설치한 뒤, 이 파일을 다시 더블클릭해 주세요:"
    echo "   1) 브라우저에서 python.org 접속"
    echo "   2) Downloads → 'Download Python 3.x.x' 노란 버튼 클릭"
    echo "   3) 내려받은 파일을 더블클릭해 '계속'만 눌러 설치"
    echo "   (그림 설명: 0_설치/MAC_설치.md 2단계)"
    wait_key_and_exit 1
fi

# 버전이 3.11 이상인지 확인 (변환 도구가 3.11 이상을 요구)
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️  설치된 Python 버전이 오래되었습니다. (3.11 이상 필요)"
    echo "    python.org 에서 최신 버전을 설치한 뒤,"
    echo "    이 파일을 다시 더블클릭해 주세요."
    wait_key_and_exit 1
fi

echo "     ✔ Python 확인 완료: $("$PYTHON_BIN" --version 2>&1)"
echo ""

# -------------------------------------------------------------
# [2/3] 자료 변환 도구 설치 (venv + Python 패키지)
# -------------------------------------------------------------
echo "[2/3] 자료 변환 도구를 설치합니다... (몇 분 걸릴 수 있습니다)"

# venv = 이 지식창고 전용 Python 작업 공간.
# 컴퓨터의 다른 프로그램과 섞이지 않게 따로 방을 만드는 것입니다.
VENV_DIR="$TOOLS_DIR/venv"

if [ ! -x "$VENV_DIR/bin/python3" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if [ ! -x "$VENV_DIR/bin/python3" ]; then
    # venv 실패: 이 단계는 표시만 하고, 독립적인 3단계는 계속 진행
    echo ""
    echo "⚠️  전용 작업 공간(venv) 만들기에 실패했습니다."
    echo "    다음 단계는 계속 진행합니다."
    echo "    (나중에 이 파일을 다시 실행하거나, 3_사용법/FAQ_문제해결.md 참고)"
    FAIL=1
else
    # pip(패키지 설치 도구) 최신화 — 실패해도 치명적이지 않으므로 조용히 넘어감
    "$VENV_DIR/bin/python3" -m pip install --upgrade pip >/dev/null 2>&1

    # 변환 도구 3종 설치:
    #  - markitdown[all] : PDF·DOCX·XLSX·PPTX·이미지 → md 변환
    #  - graphifyy       : 지식그래프. 반드시 기본(base)만 설치 — 부가 기능(extras) 설치 금지
    #  - olefile         : HWP 파일 안의 이미지 추출
    "$VENV_DIR/bin/python3" -m pip install "markitdown[all]" graphifyy olefile
    if [ $? -ne 0 ]; then
        echo ""
        echo "⚠️  변환 도구(Python 패키지) 설치에 실패했습니다."
        echo "    인터넷 연결을 확인한 뒤 이 파일을 다시 더블클릭하면,"
        echo "    이미 설치된 부분은 건너뛰고 이어서 진행됩니다."
        echo "    다음 단계는 계속 진행합니다."
        FAIL=1
    else
        echo "     ✔ 변환 도구 설치 완료"
    fi
fi
echo ""

# -------------------------------------------------------------
# [3/3] 한글(HWP) 변환기 rhwp 내려받기
# -------------------------------------------------------------
echo "[3/3] 한글(HWP) 파일 변환기를 내려받습니다..."

RHWP_DIR="$TOOLS_DIR/rhwp"
RHWP_VER="v0.7.17"

# 이 Mac 의 칩 종류를 자동 판별합니다.
#  - arm64  = 애플실리콘 (M1~M4)
#  - 그 외  = 인텔 Mac
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
    RHWP_FILE="rhwp-${RHWP_VER}-macos-aarch64.tar.gz"
else
    RHWP_FILE="rhwp-${RHWP_VER}-macos-x86_64.tar.gz"
fi
RHWP_URL="https://github.com/edwardkim/rhwp/releases/download/${RHWP_VER}/${RHWP_FILE}"

mkdir -p "$RHWP_DIR"
TMP_TGZ="$TOOLS_DIR/.rhwp_download.tar.gz"

# 내려받기 (진행 막대 표시). 실패해도 다른 기능은 쓸 수 있으므로 중단하지 않음
curl -L --fail -# -o "$TMP_TGZ" "$RHWP_URL"
if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️  한글 변환기 내려받기에 실패했습니다."
    echo "    인터넷 연결을 확인한 뒤 이 파일을 다시 더블클릭해 주세요."
    echo "    (한글 파일 변환 외의 기능은 그대로 사용할 수 있습니다)"
    FAIL=1
else
    # 압축 풀기 → 2_도구/rhwp/ 에 배치
    tar -xzf "$TMP_TGZ" -C "$RHWP_DIR"
    if [ $? -ne 0 ]; then
        echo "⚠️  압축 풀기에 실패했습니다. (3_사용법/FAQ_문제해결.md 참고)"
        FAIL=1
    else
        # 압축 안에 폴더가 한 겹 더 들어 있는 경우, 내용물을 바로 위로 꺼냄.
        # 주의: 내부 폴더 이름도 'rhwp'라서 (v0.7.17 실측) -e 가 아니라 -f 로 판별해야 하고,
        #       이름 충돌을 피하려고 임시 이름으로 옮긴 뒤 내용물을 꺼낸다.
        if [ ! -f "$RHWP_DIR/rhwp" ]; then
            INNER_DIR="$(find "$RHWP_DIR" -mindepth 1 -maxdepth 1 -type d | head -1)"
            if [ -n "$INNER_DIR" ]; then
                mv "$INNER_DIR" "$RHWP_DIR/.inner_tmp"
                mv "$RHWP_DIR/.inner_tmp"/* "$RHWP_DIR"/ 2>/dev/null
                rmdir "$RHWP_DIR/.inner_tmp" 2>/dev/null
            fi
        fi
        # 실행 권한 부여 (압축 과정에서 빠질 수 있음)
        [ -f "$RHWP_DIR/rhwp" ] && chmod +x "$RHWP_DIR/rhwp"
        if [ ! -f "$RHWP_DIR/rhwp" ]; then
            echo "⚠️  한글 변환기 파일 배치가 예상과 다릅니다. (3_사용법/FAQ_문제해결.md 참고)"
            FAIL=1
        fi
        echo "     ✔ 한글 변환기 설치 완료: 2_도구/rhwp/"
    fi
    rm -f "$TMP_TGZ"
fi
echo ""

# -------------------------------------------------------------
#  마무리
# -------------------------------------------------------------
echo "============================================"
if [ "$FAIL" -eq 0 ]; then
    echo "  ✅ 설치 완료"
    echo ""
    echo "  다음 순서:"
    echo "  1) 0_설치/설치_점검표.md 로 설치 상태를 확인하세요."
    echo "  2) 1_시작/BOOTSTRAP.md 를 열어 지식창고를 만드세요."
else
    echo "  ⚠️  일부 단계가 실패했습니다."
    echo ""
    echo "  위쪽의 ⚠️ 표시된 안내를 확인해 주세요."
    echo "  이 파일을 다시 더블클릭하면 이어서 진행됩니다."
    echo "  (도움말: 3_사용법/FAQ_문제해결.md)"
fi
echo "============================================"

wait_key_and_exit 0
