@echo off
REM 将 v3.8 更新文件拷贝到 .claude/ 目录
REM 在 D:\MyPrj\ai-dev-flow 目录下运行此脚本

echo === 拷贝 v3.8 更新文件到 .claude/ ===

copy /Y "v3.8-updates\status.md" ".claude\status.md"
if %errorlevel% neq 0 (echo [FAIL] status.md & exit /b 1)

if not exist ".claude\plans" mkdir ".claude\plans"
copy /Y "v3.8-updates\implementation-tracker.md" ".claude\plans\implementation-tracker.md"
if %errorlevel% neq 0 (echo [FAIL] implementation-tracker.md & exit /b 1)

copy /Y "v3.8-updates\v3.8-controllability.md" ".claude\plans\v3.8-controllability.md"
if %errorlevel% neq 0 (echo [FAIL] v3.8-controllability.md & exit /b 1)

echo === 全部拷贝完成 ===
echo 请手动验证 .claude\status.md 和 .claude\plans\ 目录
pause
