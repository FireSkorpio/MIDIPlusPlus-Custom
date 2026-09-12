from pathlib import Path

ROOT = Path("MIDIPlusPlus-1.0.4.R5_Rel")
UI = ROOT / "MIDI++.cpp"
NOTES = Path("UPDATE_NOTES.md")


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


text = read(UI)
marker = "// -----------------------------------------------------------------------------\n// Main Entry Point\n// -----------------------------------------------------------------------------\n"
if marker not in text:
    raise RuntimeError("Main Entry Point marker not found in MIDI++.cpp")

prefix, _old_tail = text.split(marker, 1)
new_tail = r'''// -----------------------------------------------------------------------------
// Startup splash / diagnostics
// -----------------------------------------------------------------------------
static std::filesystem::path StartupErrorPath() {
    wchar_t exePath[32768]{};
    const DWORD len = GetModuleFileNameW(nullptr, exePath, static_cast<DWORD>(std::size(exePath)));
    if (len > 0 && len < std::size(exePath))
        return std::filesystem::path(exePath).parent_path() / L"startup_error.txt";
    return std::filesystem::path(L"startup_error.txt");
}

static void ClearStartupErrorFile() noexcept {
    try {
        std::error_code ec;
        std::filesystem::remove(StartupErrorPath(), ec);
    }
    catch (...) {}
}

static HWND CreateStartupSplash(HINSTANCE hInstance) {
    constexpr int width = 470;
    constexpr int height = 150;
    const int x = std::max(0, (GetSystemMetrics(SM_CXSCREEN) - width) / 2);
    const int y = std::max(0, (GetSystemMetrics(SM_CYSCREEN) - height) / 2);

    HWND splash = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        L"STATIC",
        L"MIDI++ Custom Build\r\n\r\nStarting...",
        WS_POPUP | WS_BORDER | SS_CENTER | SS_CENTERIMAGE,
        x, y, width, height,
        nullptr, nullptr, hInstance, nullptr);

    if (splash) {
        SendMessageW(splash, WM_SETFONT,
            reinterpret_cast<WPARAM>(GetStockObject(DEFAULT_GUI_FONT)), TRUE);
        ShowWindow(splash, SW_SHOW);
        UpdateWindow(splash);
    }
    return splash;
}

static void SetStartupStatus(HWND splash, const wchar_t* status) noexcept {
    if (!splash)
        return;
    std::wstring text = L"MIDI++ Custom Build\r\n\r\n";
    text += status;
    SetWindowTextW(splash, text.c_str());
    UpdateWindow(splash);
}

static int ReportStartupFailure(HWND splash, const std::string& stage, const std::string& detail) noexcept {
    std::string message = "MIDI++ could not finish starting.\n\nStage: " + stage +
        "\nError: " + detail +
        "\n\nA copy of this error was written to startup_error.txt beside MIDI++.exe.";

    try {
        std::ofstream file(StartupErrorPath(), std::ios::trunc);
        if (file) {
            SYSTEMTIME st{};
            GetLocalTime(&st);
            file << "MIDI++ startup failure\n";
            file << "Time: "
                 << st.wYear << '-' << st.wMonth << '-' << st.wDay << ' '
                 << st.wHour << ':' << st.wMinute << ':' << st.wSecond << "\n";
            file << "Stage: " << stage << "\n";
            file << "Error: " << detail << "\n";
        }
    }
    catch (...) {}

    if (splash && IsWindow(splash))
        DestroyWindow(splash);
    MessageBoxA(nullptr, message.c_str(), "MIDI++ Startup Error", MB_OK | MB_ICONERROR);
    return -1;
}

// -----------------------------------------------------------------------------
// Main Entry Point
// -----------------------------------------------------------------------------
int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE, PWSTR, int) {
    srand(static_cast<unsigned int>(time(NULL)));
    g_hInst = hInstance;
    ClearStartupErrorFile();

    UniqueHandle singleInstanceMutex(CreateMutexW(nullptr, TRUE, L"Global\\MIDI++_On_Top"));
    g_hSingleInstanceMutex = singleInstanceMutex;
    if (!singleInstanceMutex.handle) {
        return ReportStartupFailure(nullptr, "single-instance setup",
            "CreateMutexW failed with Windows error " + std::to_string(GetLastError()));
    }
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        HWND existingWindow = FindWindowW(L"MIDI++", L"MIDI++ Custom Build");
        if (existingWindow) {
            if (IsIconic(existingWindow))
                ShowWindow(existingWindow, SW_RESTORE);
            SetForegroundWindow(existingWindow);
        }
        else {
            MessageBoxA(nullptr,
                "Another MIDI++ instance appears to be running, but its window could not be found.\n\n"
                "Open Task Manager and end MIDI++.exe, then try again.",
                "MIDI++ Already Running", MB_OK | MB_ICONWARNING);
        }
        return 0;
    }

    HWND startupSplash = CreateStartupSplash(hInstance);
    SetStartupStatus(startupSplash, L"Initializing graphics...");

    GdiplusTokenWrapper gdiplusToken;
    Gdiplus::GdiplusStartupInput gdiplusStartupInput;
    if (Gdiplus::GdiplusStartup(&gdiplusToken.token, &gdiplusStartupInput, nullptr) != Gdiplus::Ok) {
        return ReportStartupFailure(startupSplash, "graphics initialization", "GDI+ failed to initialize.");
    }

    SetStartupStatus(startupSplash, L"Loading configuration and playback engine...");
    std::unique_ptr<VirtualPianoPlayer> player;
    try {
        player = std::make_unique<VirtualPianoPlayer>();
        g_player = player.get();
    }
    catch (const std::exception& ex) {
        return ReportStartupFailure(startupSplash, "playback engine initialization", ex.what());
    }
    catch (...) {
        return ReportStartupFailure(startupSplash, "playback engine initialization", "Unknown exception.");
    }

    RedirectCout();
    auto& cfg = midi::Config::getInstance();

    std::cout << " ===== MIDI++ Custom Build | Based on v1.0.4.R5 by Zeph, Tested by Gene =====\n";
    std::cout << "Hotkeys:\n";
    std::cout << "  Play/Pause:     " << getReadableKey(cfg.hotkeys.PLAY_PAUSE_KEY) << "\n";
    std::cout << "  Rewind:         " << getReadableKey(cfg.hotkeys.REWIND_KEY) << "\n";
    std::cout << "  Skip:           " << getReadableKey(cfg.hotkeys.SKIP_KEY) << "\n";
    std::cout << "  Panic/Release:  " << getReadableKey(cfg.hotkeys.PANIC_KEY) << "\n";

    SetStartupStatus(startupSplash, L"Loading application resources...");
    HICON hIcon = LoadIconW(hInstance, MAKEINTRESOURCEW(IDI_APP_ICON));
    HICON hIconSmall = LoadIconW(hInstance, MAKEINTRESOURCEW(IDI_APP_ICON_SMALL));
    if (!hIcon || !hIconSmall) {
        return ReportStartupFailure(startupSplash, "resource loading",
            "Application icons could not be loaded. Windows error " + std::to_string(GetLastError()));
    }

    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
    wc.lpszClassName = L"MIDI++";
    wc.hIcon = hIcon;
    wc.hIconSm = hIconSmall;
    if (!RegisterClassExW(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        return ReportStartupFailure(startupSplash, "window registration",
            "RegisterClassExW failed with Windows error " + std::to_string(GetLastError()));
    }

    // WM_CREATE populates the controls and enumerates MIDI input devices. If
    // that step is slow or blocked, the splash remains visible with this exact
    // status instead of making MIDI++ appear to do nothing.
    SetStartupStatus(startupSplash, L"Building interface and scanning MIDI devices...");
    SetLastError(ERROR_SUCCESS);
    g_hMainWnd = CreateWindowExW(WS_EX_NOACTIVATE | WS_EX_APPWINDOW | WS_EX_LAYERED,
        wc.lpszClassName,
        L"MIDI++ Custom Build",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT,
        Layout::WIN_W, Layout::WIN_H,
        nullptr,
        nullptr,
        hInstance,
        nullptr);
    if (!g_hMainWnd) {
        return ReportStartupFailure(startupSplash, "main window creation",
            "CreateWindowExW failed with Windows error " + std::to_string(GetLastError()));
    }

    if (!SetLayeredWindowAttributes(g_hMainWnd, 0,
            static_cast<BYTE>(std::clamp(cfg.ui.opacity, 100, 255)), LWA_ALPHA)) {
        std::cout << "[Startup] Warning: SetLayeredWindowAttributes failed with Windows error "
                  << GetLastError() << ".\n";
    }

    ShowWindow(g_hMainWnd, SW_SHOW);
    UpdateWindow(g_hMainWnd);
    if (startupSplash && IsWindow(startupSplash))
        DestroyWindow(startupSplash);
    ClearStartupErrorFile();

    MSG msg{};
    while (GetMessage(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    return static_cast<int>(msg.wParam);
}
'''

write(UI, prefix + new_tail)
print(f"[ok] {UI}: startup splash and diagnostics")

notes = read(NOTES)
section = r'''

## Startup diagnostics (Humanizer 2.0 test branch)

- MIDI++ now shows a small startup window immediately so a slow launch no longer looks like nothing happened.
- The startup window reports the current stage, including graphics, playback/config initialization, resources, and interface/MIDI-device enumeration.
- Startup exceptions are caught and shown in a message box instead of terminating silently.
- Startup failures are also written to `startup_error.txt` beside `MIDI++.exe` for easy troubleshooting.
- If the single-instance mutex exists but the previous MIDI++ window cannot be found, MIDI++ now explains that another background instance may still be running.
'''
if "## Startup diagnostics (Humanizer 2.0 test branch)" not in notes:
    write(NOTES, notes.rstrip() + section + "\n")
    print(f"[ok] {NOTES}")

print("Startup diagnostics patch complete.")
