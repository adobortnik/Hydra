@echo off
REM Grant storage permissions to all Instagram apps on all connected devices
REM This prevents permission dialogs during profile picture changes

echo ========================================
echo Granting Storage Permissions
echo ========================================
echo.

REM Get list of connected devices
for /f "skip=1 tokens=1" %%D in ('adb devices') do (
    if not "%%D"=="" (
        echo.
        echo Device: %%D
        echo ----------------------------------------

        REM Grant permissions for original Instagram
        echo   Granting to com.instagram.android...
        adb -s %%D shell pm grant com.instagram.android android.permission.READ_EXTERNAL_STORAGE 2>nul
        adb -s %%D shell pm grant com.instagram.android android.permission.WRITE_EXTERNAL_STORAGE 2>nul

        REM Grant permissions for Instagram clones (e through p)
        for %%P in (e f g h i j k l m n o p) do (
            echo   Granting to com.instagram.android%%P...
            adb -s %%D shell pm grant com.instagram.android%%P android.permission.READ_EXTERNAL_STORAGE 2>nul
            adb -s %%D shell pm grant com.instagram.android%%P android.permission.WRITE_EXTERNAL_STORAGE 2>nul
        )

        echo   Done!
    )
)

echo.
echo ========================================
echo Permissions granted successfully!
echo ========================================
echo.
echo You can now run profile automation without permission dialogs.
echo.
pause
