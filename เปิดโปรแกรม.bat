@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem หา Python ที่ใช้เปิดหน้าต่างโปรแกรม (pythonw จะไม่มีหน้าต่างดำค้างไว้)
set "PY="
where pythonw.exe >nul 2>&1 && set "PY=pythonw.exe"
if not defined PY (
  where py.exe >nul 2>&1 && set "PY=py.exe -3 -w"
)
if not defined PY (
  where python.exe >nul 2>&1 && set "PY=python.exe"
)

if not defined PY (
  echo.
  echo ไม่พบ Python บนเครื่อง
  echo ติดตั้งจาก https://www.python.org/downloads/ แล้วเปิดไฟล์นี้อีกครั้ง
  echo ตอนติดตั้งอย่าลืมติ๊ก "Add python.exe to PATH"
  echo.
  pause
  exit /b 1
)

start "" %PY% "%~dp0MCServerLauncher.pyw"
