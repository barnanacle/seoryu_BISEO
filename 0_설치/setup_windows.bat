@echo off
chcp 65001 >nul
rem ============================================================
rem  지식창고(JARVIS) 도구 자동 설치 - Windows용
rem
rem  사용법: 이 파일을 더블클릭하면 됩니다. (0_설치 폴더 안에 둔 채로)
rem  하는 일:
rem    [1/3] Python 확인 + 도구 전용 작업 공간(venv) 만들기
rem    [2/3] 문서 변환 프로그램 설치 (markitdown, graphifyy, olefile)
rem    [3/3] 한글(HWP) 변환 도구 rhwp v0.7.17 내려받기
rem  이 파일은 여러 번 실행해도 안전합니다.
rem ============================================================

setlocal

rem --- 이 파일이 있는 폴더를 기준으로 설치 위치를 계산합니다 ---
rem     (한글 사용자명이나 공백이 있는 경로도 안전하도록 모든 경로를 따옴표로 감쌉니다)
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\2_도구") do set "TOOLS_DIR=%%~fI"

echo.
echo ==============================================
echo   지식창고 도구 설치를 시작합니다
echo ==============================================
echo.
echo   설치 위치 : %TOOLS_DIR%
echo   이 검은 창을 닫지 말고 기다려 주세요. 몇 분 걸릴 수 있습니다.
echo.

rem ------------------------------------------------------------
rem [1/3] Python 확인 + 작업 공간(venv) 만들기
rem ------------------------------------------------------------
echo [1/3] Python 확인 중...

set "PY_CMD="
python --version >nul 2>&1
if not errorlevel 1 set "PY_CMD=python"
if defined PY_CMD goto :python_found

rem python 명령이 없으면 py 런처(py -3)로 한 번 더 확인합니다
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY_CMD=py -3"
if defined PY_CMD goto :python_found

echo.
echo   [오류] 이 컴퓨터에서 Python을 찾지 못했습니다.
echo.
echo   아직 Python을 설치하지 않으셨다면:
echo     1. WINDOWS_설치.md 문서의 2번(Python 설치)을 먼저 진행해 주세요.
echo     2. 설치 화면 맨 아래 "Add python.exe to PATH" 체크를 반드시 켜 주세요.
echo     3. 설치가 끝나면 이 파일을 다시 더블클릭해 주세요.
echo.
echo   이미 설치했는데도 이 메시지가 나온다면:
echo     "Add python.exe to PATH" 체크를 빼먹었을 가능성이 큽니다.
echo     WINDOWS_설치.md 2번의 "체크를 깜빡하고 설치했다면" 부분대로 재설치해 주세요.
echo.
echo   더 자세한 해결법: 3_사용법/FAQ_문제해결.md
echo.
pause
exit /b 1

:python_found
rem Python 버전이 3.11 이상인지 확인합니다
%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto :python_ok

echo.
echo   [오류] 설치된 Python 버전이 낮습니다. 3.11 이상이 필요합니다.
echo   대처: python.org 에서 최신 버전을 설치한 뒤 이 파일을 다시 실행해 주세요.
echo   자세한 방법: WINDOWS_설치.md 2번, 3_사용법/FAQ_문제해결.md
echo.
pause
exit /b 1

:python_ok
echo        Python 확인 완료. 작업 공간을 만드는 중...

if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%"

rem venv = 이 지식창고 전용으로 분리된 Python 작업 공간 (다른 프로그램과 충돌 방지)
%PY_CMD% -m venv "%TOOLS_DIR%\venv"
if errorlevel 1 goto :venv_fail
if not exist "%TOOLS_DIR%\venv\Scripts\python.exe" goto :venv_fail
echo        [1/3] 완료.
echo.

rem ------------------------------------------------------------
rem [2/3] 문서 변환 프로그램 설치
rem ------------------------------------------------------------
echo [2/3] 문서 변환 프로그램 설치 중... 글자가 빠르게 올라가는 것이 정상입니다.
echo.

rem pip(설치 관리자)를 먼저 최신으로 올린 뒤, 변환 프로그램 3종을 설치합니다
"%TOOLS_DIR%\venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
"%TOOLS_DIR%\venv\Scripts\python.exe" -m pip install "markitdown[all]" graphifyy olefile
if errorlevel 1 goto :pip_fail
echo.
echo        [2/3] 완료.
echo.

rem ------------------------------------------------------------
rem [3/3] 한글(HWP) 변환 도구 rhwp 내려받기
rem ------------------------------------------------------------
echo [3/3] 한글(HWP) 변환 도구를 내려받는 중...

set "RHWP_URL=https://github.com/edwardkim/rhwp/releases/download/v0.7.17/rhwp-v0.7.17-windows-x86_64.zip"
set "RHWP_ZIP=%TEMP%\rhwp-v0.7.17.zip"

rem PowerShell로 압축 파일을 내려받습니다
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%RHWP_URL%' -OutFile '%RHWP_ZIP%'"
if errorlevel 1 goto :rhwp_fail
if not exist "%RHWP_ZIP%" goto :rhwp_fail

rem 내려받은 압축 파일을 2_도구\rhwp\ 폴더에 풉니다
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Expand-Archive -LiteralPath '%RHWP_ZIP%' -DestinationPath '%TOOLS_DIR%\rhwp' -Force"
if errorlevel 1 goto :rhwp_fail
if not exist "%TOOLS_DIR%\rhwp" goto :rhwp_fail

rem 압축이 한 겹 폴더째 풀린 경우(rhwp\rhwp-v0.7.17-...\rhwp.exe) 내용물을 rhwp\ 바로 아래로 평탄화
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r='%TOOLS_DIR%\rhwp'; if (-not (Test-Path (Join-Path $r 'rhwp.exe'))) { $sub = Get-ChildItem -LiteralPath $r -Directory | Select-Object -First 1; if ($sub) { Get-ChildItem -LiteralPath $sub.FullName -Force | Move-Item -Destination $r -Force; Remove-Item -LiteralPath $sub.FullName -Force -Recurse } }"

del "%RHWP_ZIP%" >nul 2>&1
echo        [3/3] 완료.
echo.

rem ------------------------------------------------------------
rem 완료
rem ------------------------------------------------------------
echo ==============================================
echo   ✅ 설치 완료
echo ==============================================
echo.
echo   - 작업 공간(venv)      : 준비됨
echo   - 문서 변환 프로그램    : markitdown, graphifyy, olefile 설치됨
echo   - 한글(HWP) 변환 도구  : %TOOLS_DIR%\rhwp
echo.
echo   이제 이 창을 닫으셔도 됩니다.
echo   다음 순서 : WINDOWS_설치.md 4번(성공 화면 확인), 그다음 0_설치/설치_점검표.md
echo.
pause
exit /b 0

rem ------------------------------------------------------------
rem 아래는 실패했을 때 안내 메시지입니다
rem ------------------------------------------------------------

:venv_fail
echo.
echo   [오류] 작업 공간(venv) 만들기에 실패했습니다.
echo   대처: Python을 다시 설치(WINDOWS_설치.md 2번)한 뒤 이 파일을 다시 실행해 주세요.
echo   계속 안 되면: 3_사용법/FAQ_문제해결.md
echo.
pause
exit /b 1

:pip_fail
echo.
echo   [오류] 문서 변환 프로그램 설치에 실패했습니다.
echo   대처: 인터넷 연결을 확인한 뒤 이 파일을 다시 더블클릭해 주세요. 여러 번 실행해도 안전합니다.
echo   계속 안 되면: 3_사용법/FAQ_문제해결.md
echo.
pause
exit /b 1

:rhwp_fail
echo.
echo   [오류] 한글(HWP) 변환 도구 내려받기에 실패했습니다.
echo   대처: 인터넷 연결을 확인한 뒤 이 파일을 다시 더블클릭해 주세요. 앞 단계는 이미 설치되어 그대로 이어집니다.
echo   계속 안 되면: 3_사용법/FAQ_문제해결.md
echo.
pause
exit /b 1
