@echo off
echo Setting up DeepSeek + Compression...
echo.
echo [1/5] Adding API key...
set ENVFILE="%LOCALAPPDATA%\hermes\.env"
findstr /C:"DEEPSEEK_API_KEY=" %ENVFILE% >nul 2>&1
if %errorlevel%==0 (
    powershell -Command "(Get-Content %ENVFILE%) -replace 'DEEPSEEK_API_KEY=.*', 'DEEPSEEK_API_KEY=sk-9268abd85d054d2c80604fa4fa73c792' | Set-Content %ENVFILE%"
) else (
    echo DEEPSEEK_API_KEY=sk-9268abd85d054d2c80604fa4fa73c792 >> %ENVFILE%
)
echo Done.
echo.
echo [2/5] Model config...
hermes config set model.provider deepseek
hermes config set model.default deepseek-v4-flash
hermes config set model.base_url https://api.deepseek.com
echo.
echo [3/5] Compression config...
hermes config set compression.enabled true
hermes config set compression.threshold 0.4
hermes config set compression.target_ratio 0.15
hermes config set compression.protect_last_n 15
hermes config set compression.hygiene_hard_message_limit 300
echo.
echo [4/5] Auxiliary + delegation config...
hermes config set auxiliary.compression.provider deepseek
hermes config set auxiliary.compression.model deepseek-v4-flash
hermes config set auxiliary.title_generation.provider deepseek
hermes config set auxiliary.title_generation.model deepseek-v4-flash
hermes config set delegation.provider deepseek
hermes config set delegation.model deepseek-v4-flash
echo.
echo [5/5] Running doctor...
hermes doctor
echo.
echo DONE. Close this window and run: hermes
pause
