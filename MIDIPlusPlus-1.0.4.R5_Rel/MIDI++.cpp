// never writing any UI in C++ ever again

#include "PlaybackSystem.hpp"
#include "TrackControl.hpp"
#include "VelocityCurveEditor.hpp"
#include "MIDI2Key.hpp"
#include "MIDIConnect.hpp"
#include "MIDIDeviceUI.hpp"
#include "resource.h"

#include <CommCtrl.h>
#include <GdiPlus.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <ctime>     
#include <filesystem>
#include <fstream>
#include <future>
#include <functional>
#include <iostream>
#include <locale>
#include <mutex>
#include <regex>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <algorithm>
#include <iomanip>
#include <cwchar>
#include <windowsx.h>
#include <shellapi.h>
#include <commdlg.h>

#pragma comment(lib, "Comctl32.lib")
#pragma comment(lib, "Gdiplus.lib")
#pragma comment(lib, "Shell32.lib")
#pragma comment(lib, "Comdlg32.lib")

// -----------------------------------------------------------------------------
// RAII wrappers for HANDLE and GDI+ token
// -----------------------------------------------------------------------------
struct UniqueHandle {
    HANDLE handle;
    UniqueHandle(HANDLE h = nullptr) : handle(h) {}
    ~UniqueHandle() {
        if (handle && handle != INVALID_HANDLE_VALUE) {
            CloseHandle(handle);
        }
    }
    UniqueHandle(const UniqueHandle&) = delete;
    UniqueHandle& operator=(const UniqueHandle&) = delete;
    operator HANDLE() const { return handle; }
};

struct GdiplusTokenWrapper {
    ULONG_PTR token;
    GdiplusTokenWrapper() : token(0) {}
    ~GdiplusTokenWrapper() {
        if (token != 0)
            Gdiplus::GdiplusShutdown(token);
    }
};

// -----------------------------------------------------------------------------
// Global objects and variables
// -----------------------------------------------------------------------------
class VirtualPianoPlayer* g_player = nullptr;
static std::unique_ptr<MIDI2Key>   g_midi2key;
static std::unique_ptr<MIDIConnect> g_midiConnect;
static TrackControl g_trackControl;
int g_sustainCutoff = 64;
static int g_selectedMidiDevice = 0;    // device index
static int g_selectedMidiChannel = -1;    // -1 means “All channels”

// Global handles and states
static HINSTANCE    g_hInst = nullptr;
static HWND         g_hMainWnd = nullptr;
static HANDLE       g_hSingleInstanceMutex = nullptr;

static std::mutex        g_logMutex;
static std::string       g_logBuffer;
static std::atomic<bool> g_guiReady{ false };

static std::chrono::steady_clock::time_point g_lastTimeUpdate;
static constexpr auto TIME_UPDATE_INTERVAL = std::chrono::milliseconds(500);

static const std::regex g_ansiPattern("\x1B\\[[0-9;]*[A-Za-z]");

static std::unordered_map<int, bool> g_toggleStates;

static bool g_randomSongEnabled = false;
static std::wstring g_currentLoadedMidiPath;
static bool g_seekDragging = false;
static HWND g_hToolTip = nullptr;

// -----------------------------------------------------------------------------
// Control layout constants
// -----------------------------------------------------------------------------
namespace Layout {
    // Window dimensions
    static const int WIN_W = 880;
    static const int WIN_H = 865;

    // MIDI Files group
    static const int FILES_X = 10;
    static const int FILES_Y = 10;
    static const int FILES_W = 240;
    static const int FILES_H = 405;

    // Playback (Basic) group
    static const int PBASIC_X = 260;
    static const int PBASIC_Y = 10;
    static const int PBASIC_W = 600;
    static const int PBASIC_H = 175;
    static const int PB_ROW1_Y = PBASIC_Y + 25;
    static const int PB_ROW2_Y = PBASIC_Y + 25 + 28 + 8;
    static const int PB_BTN_WIDTH = 80;
    static const int PB_BTN_HEIGHT = 28;
    static const int PB_BTN_GAP = 10;
    static const int PB_MIDI_QWERTY_X = PBASIC_X + 340;
    static const int PB_MIDI_QWERTY_Y = PB_ROW1_Y;
    static const int PB_STATIC_TIME_X = PBASIC_X + 470;
    static const int PB_STATIC_TIME_Y = PBASIC_Y + 28;
    static const int PB_STATIC_TIME_W = 120;
    static const int PB_STATIC_TIME_H = 25;

    // Advanced group
    static const int PADV_X = 260;
    static const int PADV_Y = PBASIC_Y + PBASIC_H + 5;
    static const int PADV_W = 600;
    static const int PADV_H = 130;

    // Config group
    static const int CFG_X = 260;
    static const int CFG_Y = PADV_Y + PADV_H + 5;
    static const int CFG_W = 600;
    static const int CFG_H = 60;

    // Details group
    static const int DET_X = 260;
    static const int DET_Y = CFG_Y + CFG_H + 5;
    static const int DET_W = 600;
    static const int DET_H = 130;

    // Tracks group
    static const int TRK_X = 10;
    static const int TRK_Y = DET_Y + DET_H + 10;
    static const int TRK_W = 850;
    static const int TRK_H = 120;

    // Log group
    static const int LOG_X = 10;
    static const int LOG_Y = TRK_Y + TRK_H + 10;
    static const int LOG_W = 850;
    static const int LOG_H = 150;
}

// Global sustain cutoff value box (edit control)
static HWND g_hSustainCutoffValueBox = nullptr;

// Global listbox for MIDI files (now showing folders & files) and other UI elements
static HWND g_lbMidi = nullptr;
static HWND g_editDetails = nullptr;
static HWND g_editTracks = nullptr;
static HWND g_hOpacityIndicatorBox = nullptr;
static HWND g_hHumanizerWnd = nullptr;
static HWND g_hHelpWnd = nullptr;

// -----------------------------------------------------------------------------
// Control IDs
// -----------------------------------------------------------------------------
enum ControlID {
    // ListBox and ComboBoxes
    ID_CB_SORT = 101,
    ID_BTN_REFRESH,
    ID_LB_MIDI,
    ID_CB_RECENT,
    ID_EDIT_MIDI_SEARCH,

    // Basic Playback Group
    ID_GRP_PLAY,
    ID_BTN_LOAD,
    ID_BTN_PLAY,
    ID_BTN_STOP,
    ID_BTN_SKIP,
    ID_BTN_REW,
    ID_BTN_SPEEDUP,
    ID_BTN_SPEEDDN,
    ID_BTN_RESTART,
    ID_BTN_RELOAD,
    ID_BTN_RESET_PLAYBACK,

    // MIDI -> QWERTY and device controls
    ID_BTN_MIDI2QWERTY,
    ID_CB_MIDIDEV,
    ID_CB_MIDICH,
    ID_BTN_MIDICONNECT,

    // Advanced / Extra
    ID_GRP_ADV,
    ID_BTN_88KEY,
    ID_BTN_VOLADJ,
    ID_BTN_VELOCITY,
    ID_BTN_SUSTAIN,
    ID_BTN_TRANSPOSE,
    ID_BTN_TRANSPOSEOUT,
    ID_BTN_HUMANIZER,
    ID_BTN_PLAYABILITY,
    ID_BTN_HELP,
    ID_CB_VELOCITY_CURVE,
    ID_SLIDER_SUSTAIN_CUTOFF,
    ID_STATIC_SUSTAIN_LABEL,

    // Config
    ID_GRP_CONFIG,
    ID_CHK_TOP,
    ID_CHK_RANDOM_SONG,   
    ID_SLIDER_OPACITY, 

    // Details
    ID_GRP_DETAILS,
    ID_EDIT_DETAILS,

    // Tracks
    ID_GRP_TRACKS,
    ID_EDIT_TRACKS,

    // Log
    ID_GRP_LOG,
    ID_BTN_REFRESH_VCURVE,
    ID_EDIT_LOG,
    ID_BTN_CLEARLOG,
    ID_BTN_REFRESH_MIDI,
    ID_BTN_VLCURVE,

    // Custom messages and timers
    WM_UPDATE_LOG = WM_APP + 101,
    IDT_TIMELEFT_TIMER,
    ID_STATIC_TIME,
    ID_SLIDER_SEEK,
    ID_STATIC_SPEED,
    ID_STATIC_TRANSPOSE,
    ID_STATIC_STATUS,

    // Track Mute/Solo button bases
    ID_TRACK_MUTE_BASE = 2000,
    ID_TRACK_SOLO_BASE = 2500,
    ID_BTN_PREV_SONG = 3000,
    ID_BTN_NEXT_SONG = 3001
};

static bool IsToggleButtonID(int id) {
    switch (id) {
    case ID_BTN_88KEY:
    case ID_BTN_VOLADJ:
    case ID_BTN_VELOCITY:
    case ID_BTN_SUSTAIN:
    case ID_BTN_TRANSPOSEOUT:
    case ID_BTN_PLAYABILITY:
    case ID_BTN_MIDI2QWERTY:
    case ID_BTN_MIDICONNECT:
        return true;
    default:
        return false;
    }
}

// -----------------------------------------------------------------------------
// MIDI Folder Scanning and Sorting (with folder exploration)
// -----------------------------------------------------------------------------

struct MidiItem {
    std::wstring name;
    std::wstring fullPath;
    bool isFolder;
    std::time_t lastWrite; 
};

static std::vector<MidiItem> g_midiItems;
static std::filesystem::path g_currentMidiDir = L"midi";
// bunch of kids
std::string getReadableKey(const std::string& key) {
    const std::string prefix = "VK_";
    if (key.compare(0, prefix.size(), prefix) == 0) {
        return key.substr(prefix.size());
    }
    return key;
}
static void ScanMidiFolder() {
    g_midiItems.clear();
    std::filesystem::path currentDir = g_currentMidiDir;
    if (!std::filesystem::exists(currentDir) || !std::filesystem::is_directory(currentDir)) {
        std::wcout << L"[Scan] '" << currentDir.wstring() << L"' not found.\n";
        return;
    }
  
    if (!std::filesystem::equivalent(currentDir, midi::Config::resolvePath("midi"))) {
        MidiItem parentItem;
        parentItem.name = L"..";
        parentItem.fullPath = currentDir.parent_path().wstring();
        parentItem.isFolder = true;
        parentItem.lastWrite = 0;
        g_midiItems.push_back(parentItem);
    }
    for (const auto& entry : std::filesystem::directory_iterator(currentDir)) {
        MidiItem item;
        item.name = entry.path().filename().wstring();
        item.fullPath = entry.path().wstring();
        item.isFolder = entry.is_directory();
        if (!item.isFolder) {
            auto ext = entry.path().extension().wstring();
            std::wstring lw(ext.size(), L'\0');
            std::transform(ext.begin(), ext.end(), lw.begin(), ::towlower);
            if (lw != L".mid" && lw != L".midi")
                continue; // skip non-midi files
            auto ftime = std::filesystem::last_write_time(entry.path());
            auto sctp = std::chrono::time_point_cast<std::chrono::system_clock::duration>(
                ftime - std::filesystem::file_time_type::clock::now() + std::chrono::system_clock::now()
            );
            item.lastWrite = std::chrono::system_clock::to_time_t(sctp);
        }
        else {
            item.lastWrite = 0;
        }
        g_midiItems.push_back(item);
    }
}


static std::wstring GetMidiBrowserSearchText() {
    HWND edit = g_hMainWnd ? GetDlgItem(g_hMainWnd, ID_EDIT_MIDI_SEARCH) : nullptr;
    if (!edit)
        return L"";
    const int len = GetWindowTextLengthW(edit);
    std::wstring value(static_cast<size_t>(std::max(0, len)), L'\0');
    if (len > 0)
        GetWindowTextW(edit, value.data(), len + 1);
    return value;
}

static void ScanMidiSearchResults(const std::wstring& queryText) {
    if (queryText.empty()) {
        ScanMidiFolder();
        return;
    }

    g_midiItems.clear();
    const std::filesystem::path root = midi::Config::resolvePath("midi");
    if (!std::filesystem::exists(root) || !std::filesystem::is_directory(root))
        return;

    std::wstring query = queryText;
    std::transform(query.begin(), query.end(), query.begin(), ::towlower);

    std::error_code iterError;
    std::filesystem::recursive_directory_iterator it(
        root, std::filesystem::directory_options::skip_permission_denied, iterError);
    const std::filesystem::recursive_directory_iterator end;
    for (; it != end; it.increment(iterError)) {
        if (iterError) {
            iterError.clear();
            continue;
        }
        const auto& entry = *it;
        if (!entry.is_regular_file(iterError)) {
            iterError.clear();
            continue;
        }
        auto ext = entry.path().extension().wstring();
        std::transform(ext.begin(), ext.end(), ext.begin(), ::towlower);
        if (ext != L".mid" && ext != L".midi")
            continue;

        std::error_code relError;
        auto relative = std::filesystem::relative(entry.path(), root, relError);
        if (relError)
            relative = entry.path().filename();
        std::wstring haystack = relative.wstring();
        std::transform(haystack.begin(), haystack.end(), haystack.begin(), ::towlower);
        if (haystack.find(query) == std::wstring::npos)
            continue;

        MidiItem item;
        item.name = relative.wstring();
        item.fullPath = entry.path().wstring();
        item.isFolder = false;
        auto ftime = std::filesystem::last_write_time(entry.path(), iterError);
        if (!iterError) {
            auto sctp = std::chrono::time_point_cast<std::chrono::system_clock::duration>(
                ftime - std::filesystem::file_time_type::clock::now() + std::chrono::system_clock::now());
            item.lastWrite = std::chrono::system_clock::to_time_t(sctp);
        }
        else {
            iterError.clear();
            item.lastWrite = 0;
        }
        g_midiItems.push_back(std::move(item));
    }
}

static int GetSortMode() {
    HWND cbSort = GetDlgItem(g_hMainWnd, ID_CB_SORT);
    if (!cbSort)
        return 0; // default to "Name (A-Z)"
    return static_cast<int>(SendMessage(cbSort, CB_GETCURSEL, 0, 0));
}

static void SortMidiItems() {
    int sortMode = GetSortMode();

    std::vector<MidiItem> parentItems;
    std::vector<MidiItem> folders;
    std::vector<MidiItem> files;

    for (const auto& item : g_midiItems) {
        if (item.name == L"..")
            parentItems.push_back(item);
        else if (item.isFolder)
            folders.push_back(item);
        else
            files.push_back(item);
    }

    // Sorting function for folders.
    auto folderSort = [sortMode](const MidiItem& a, const MidiItem& b) -> bool {
        // Folders don’t have a valid date, so we sort them by name.
        switch (sortMode) {
        case 0: // Name (A-Z)
            return _wcsicmp(a.name.c_str(), b.name.c_str()) < 0;
        case 1: // Name (Z-A)
            return _wcsicmp(a.name.c_str(), b.name.c_str()) > 0;
        default:
            return _wcsicmp(a.name.c_str(), b.name.c_str()) < 0;
        }
        };

    auto fileSort = [sortMode](const MidiItem& a, const MidiItem& b) -> bool {
        bool aFav = (std::filesystem::path(a.fullPath).parent_path().filename() == L"favorite");
        bool bFav = (std::filesystem::path(b.fullPath).parent_path().filename() == L"favorite");
        if (aFav != bFav)
            return aFav; 

        switch (sortMode) {
        case 0: // Name (A-Z)
            return _wcsicmp(a.name.c_str(), b.name.c_str()) < 0;
        case 1: // Name (Z-A)
            return _wcsicmp(a.name.c_str(), b.name.c_str()) > 0;
        case 2: // Date (Old-New)
            return a.lastWrite < b.lastWrite;
        case 3: // Date (New-Old)
            return a.lastWrite > b.lastWrite;
        default:
            return _wcsicmp(a.name.c_str(), b.name.c_str()) < 0;
        }
        };

    std::sort(folders.begin(), folders.end(), folderSort);
    std::sort(files.begin(), files.end(), fileSort);

    g_midiItems.clear();
    for (const auto& p : parentItems)
        g_midiItems.push_back(p);
    for (const auto& f : folders)
        g_midiItems.push_back(f);
    for (const auto& f : files)
        g_midiItems.push_back(f);
}

static void RefreshVelocityCurveCombo(HWND hWnd) {
    HWND cbVelocity = GetDlgItem(hWnd, ID_CB_VELOCITY_CURVE);
    SendMessage(cbVelocity, CB_RESETCONTENT, 0, 0);

    SendMessageW(cbVelocity, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Linear Coarse"));
    SendMessageW(cbVelocity, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Linear Fine"));
    SendMessageW(cbVelocity, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Improved Low Volume"));
    SendMessageW(cbVelocity, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Logarithmic"));
    SendMessageW(cbVelocity, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Exponential"));

    const auto& customCurves = midi::Config::getInstance().playback.customVelocityCurves;
    for (const auto& curve : customCurves) {
        std::wstring wCurveName(curve.name.begin(), curve.name.end());
        SendMessageW(cbVelocity, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(wCurveName.c_str()));
    }

    SendMessage(cbVelocity, CB_SETCURSEL, 0, 0);
}

static void PopulateMidiList() {
    if (!g_lbMidi)
        return; // Guard against a NULL listbox handle

    SendMessage(g_lbMidi, LB_RESETCONTENT, 0, 0);
    int maxWidth = 0;
    HDC hdc = GetDC(g_lbMidi);
    HFONT hFont = reinterpret_cast<HFONT>(SendMessage(g_lbMidi, WM_GETFONT, 0, 0));
    if (hFont)
        SelectObject(hdc, hFont);

    for (const auto& item : g_midiItems) {
        std::wstring displayName;
        if (item.name == L"..") {
            displayName = L".. (Back)";
        }
        else if (item.isFolder) {
            displayName = item.name + L"\\";
        }
        else {
            displayName = item.name;
            std::filesystem::path filePath(item.fullPath);
            std::filesystem::path favFolder = midi::Config::resolvePath("midi") / L"favorite";
            std::filesystem::path favFile = favFolder / filePath.filename();
            if (std::filesystem::exists(favFile))
                displayName = L"★ " + displayName;
        }
        SendMessageW(g_lbMidi, LB_ADDSTRING, 0, reinterpret_cast<LPARAM>(displayName.c_str()));

        SIZE textSize;
        GetTextExtentPoint32W(hdc, displayName.c_str(), static_cast<int>(displayName.size()), &textSize);
        if (textSize.cx > maxWidth)
            maxWidth = textSize.cx;
    }

    ReleaseDC(g_lbMidi, hdc);
    SendMessage(g_lbMidi, LB_SETHORIZONTALEXTENT, maxWidth, 0);
    if (SendMessage(g_lbMidi, LB_GETCOUNT, 0, 0) > 0)
        SendMessage(g_lbMidi, LB_SETCURSEL, 0, 0);
}

static std::wstring GetSelectedMidiFullPath() {
    int sel = static_cast<int>(SendMessage(g_lbMidi, LB_GETCURSEL, 0, 0));
    if (sel == LB_ERR || sel < 0 || sel >= static_cast<int>(g_midiItems.size()))
        return L"";
    const MidiItem& item = g_midiItems[sel];
    if (item.isFolder)
        return L""; 
    return item.fullPath;
}

static std::string WideToUtf8(const std::wstring& value) {
    if (value.empty()) return {};
    int len = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), nullptr, 0, nullptr, nullptr);
    std::string result(len, '\0');
    if (len > 0)
        WideCharToMultiByte(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), result.data(), len, nullptr, nullptr);
    return result;
}

static std::wstring Utf8ToWide(const std::string& value) {
    if (value.empty()) return {};
    int len = MultiByteToWideChar(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), nullptr, 0);
    std::wstring result(len, L'\0');
    if (len > 0)
        MultiByteToWideChar(CP_UTF8, 0, value.c_str(), static_cast<int>(value.size()), result.data(), len);
    return result;
}

static void RefreshRecentMidiCombo(HWND hWnd) {
    HWND combo = GetDlgItem(hWnd, ID_CB_RECENT);
    if (!combo) return;
    SendMessage(combo, CB_RESETCONTENT, 0, 0);
    const auto& recent = midi::Config::getInstance().ui.recentMidiFiles;
    for (const auto& pathText : recent) {
        std::filesystem::path p(Utf8ToWide(pathText));
        const std::wstring display = p.filename().empty() ? Utf8ToWide(pathText) : p.filename().wstring();
        SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(display.c_str()));
    }
    SendMessage(combo, CB_SETCURSEL, -1, 0);
}

static void RememberRecentMidi(HWND hWnd, const std::wstring& path) {
    auto& cfg = midi::Config::getInstance();
    std::wstring absolutePath = path;
    try { absolutePath = std::filesystem::absolute(std::filesystem::path(path)).wstring(); } catch (...) {}
    const std::string utf8 = WideToUtf8(absolutePath);
    auto& recent = cfg.ui.recentMidiFiles;
    recent.erase(std::remove(recent.begin(), recent.end(), utf8), recent.end());
    recent.insert(recent.begin(), utf8);
    if (recent.size() > 5) recent.resize(5);
    try { cfg.saveToFile("config.json"); } catch (...) {}
    RefreshRecentMidiCombo(hWnd);
}

static void AddToolTip(HWND parent, int controlId, const wchar_t* textValue) {
    HWND control = GetDlgItem(parent, controlId);
    if (!control) return;
    if (!g_hToolTip) {
        g_hToolTip = CreateWindowExW(WS_EX_TOPMOST, TOOLTIPS_CLASSW, nullptr,
            WS_POPUP | TTS_ALWAYSTIP | TTS_NOPREFIX,
            CW_USEDEFAULT, CW_USEDEFAULT, CW_USEDEFAULT, CW_USEDEFAULT,
            parent, nullptr, g_hInst, nullptr);
        SetWindowPos(g_hToolTip, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        SendMessage(g_hToolTip, TTM_SETMAXTIPWIDTH, 0, 420);
    }
    TOOLINFOW ti{};
    ti.cbSize = sizeof(ti);
    ti.uFlags = TTF_IDISHWND | TTF_SUBCLASS;
    ti.hwnd = parent;
    ti.uId = reinterpret_cast<UINT_PTR>(control);
    ti.lpszText = const_cast<LPWSTR>(textValue);
    SendMessageW(g_hToolTip, TTM_ADDTOOLW, 0, reinterpret_cast<LPARAM>(&ti));
}

// -----------------------------------------------------------------------------
// Logging (Redirect std::cout)
// -----------------------------------------------------------------------------
static std::streambuf* g_oldCoutBuf = nullptr;

static std::string GetTimeStamp() {
    SYSTEMTIME st;
    GetLocalTime(&st);
    char buf[32];
    sprintf_s(buf, "[%02d:%02d:%02d] ", st.wHour, st.wMinute, st.wSecond);
    return buf;
}

class LogBuf : public std::streambuf {
    static constexpr size_t BUFFER_SIZE = 8192;
    char buffer[BUFFER_SIZE];
    bool startOfLine = true;
    std::string timestampCache;
    void updateTimestampCache() {
        SYSTEMTIME st;
        GetLocalTime(&st);
        char buf[32];
        sprintf_s(buf, "[%02d:%02d:%02d] ", st.wHour, st.wMinute, st.wSecond);
        timestampCache = buf;
    }
protected:
    std::streamsize xsputn(const char* s, std::streamsize n) override {
        if (n <= 0)
            return 0;
        std::string chunk;
        chunk.reserve(n + (n / 20) * timestampCache.size());
        size_t start = 0;
        for (size_t i = 0; i < static_cast<size_t>(n); ++i) {
            if (startOfLine) {
                if (timestampCache.empty()) updateTimestampCache();
                chunk.append(timestampCache);
                startOfLine = false;
            }
            if (s[i] == '\n') {
                chunk.append(s + start, i - start + 1);
                start = i + 1;
                startOfLine = true;
            }
        }
        if (start < static_cast<size_t>(n))
            chunk.append(s + start, n - start);
        chunk = std::regex_replace(chunk, g_ansiPattern, "");
        {
            std::lock_guard<std::mutex> lk(g_logMutex);
            g_logBuffer += chunk;
        }
        if (g_guiReady.load(std::memory_order_acquire))
            PostMessage(g_hMainWnd, WM_UPDATE_LOG, 0, 0);
        return n;
    }
    int overflow(int c = EOF) override {
        if (c == EOF) return c;
        char ch = static_cast<char>(c);
        return xsputn(&ch, 1);
    }
};

static LogBuf g_logBuf;

static void RedirectCout() {
    if (!g_oldCoutBuf)
        g_oldCoutBuf = std::cout.rdbuf(&g_logBuf);
}

static void RestoreCout() {
    if (g_oldCoutBuf) {
        std::cout.rdbuf(g_oldCoutBuf);
        g_oldCoutBuf = nullptr;
    }
}

// -----------------------------------------------------------------------------
// UI Helper Functions
// -----------------------------------------------------------------------------
static void SetAlwaysOnTop(HWND hwnd, bool top) {
    SetWindowPos(hwnd, (top ? HWND_TOPMOST : HWND_NOTOPMOST),
        0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE);
}
static void UpdateWindowFocusability() {
    if (!g_hMainWnd) return;
    bool shouldBeNoActivate = false;
    if ((g_midiConnect && g_midiConnect->IsActive()) ||
        (g_midi2key && g_midi2key->IsActive()) ||
        (g_player && g_player->midiFileSelected.load(std::memory_order_acquire) && !g_player->paused.load(std::memory_order_relaxed)))
    {
        shouldBeNoActivate = true;
    }
    LONG exStyle = GetWindowLong(g_hMainWnd, GWL_EXSTYLE);
    bool currentNoActivate = (exStyle & WS_EX_NOACTIVATE) != 0;
    if (shouldBeNoActivate != currentNoActivate) {
        if (shouldBeNoActivate)
            exStyle |= WS_EX_NOACTIVATE;
        else
            exStyle &= ~WS_EX_NOACTIVATE;
        SetWindowLong(g_hMainWnd, GWL_EXSTYLE, exStyle);
        SetWindowPos(g_hMainWnd, nullptr, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED | SWP_NOACTIVATE);
    }
}

static COLORREF g_colorOn = RGB(100, 255, 100);
static COLORREF g_colorOff = RGB(220, 220, 220);
static COLORREF g_colorHover = RGB(180, 180, 250);
static COLORREF g_colorPush = RGB(160, 160, 255);
static COLORREF g_colorText = RGB(0, 0, 0);

static void DrawFancyButton(const DRAWITEMSTRUCT* dis) {
    if (dis->CtlType != ODT_BUTTON)
        return;

    int ctrlID = static_cast<int>(dis->CtlID);
    bool togglable = IsToggleButtonID(ctrlID);
    bool toggled = togglable ? g_toggleStates[ctrlID] : false;

    HDC hdc = dis->hDC;
    RECT rc = dis->rcItem;
    bool isHot = (dis->itemState & ODS_HOTLIGHT) != 0;
    bool isPressed = (dis->itemState & ODS_SELECTED) != 0;
    bool isFocused = (dis->itemState & ODS_FOCUS) != 0;

    COLORREF fill = g_colorOff;
    if (ctrlID == ID_BTN_SUSTAIN && g_player != nullptr) {
        switch (g_player->currentSustainMode) {
        case SustainMode::IG:
            fill = RGB(220, 220, 220);
            break;
        case SustainMode::SPACE_DOWN:
            fill = RGB(100, 255, 100);
            break;
        case SustainMode::SPACE_UP:
            fill = RGB(100, 100, 255);
            break;
        }
    }
    else if (togglable && toggled) {
        fill = g_colorOn;
    }
    if (isPressed)
        fill = g_colorPush;
    else if (isHot)
        fill = g_colorHover;

    HBRUSH br = CreateSolidBrush(fill);
    FillRect(hdc, &rc, br);
    DeleteObject(br);

    FrameRect(hdc, &rc, reinterpret_cast<HBRUSH>(GetStockObject(BLACK_BRUSH)));

    wchar_t text[128] = { 0 };
    GetWindowTextW(dis->hwndItem, text, 128);

    SetTextColor(hdc, g_colorText);
    SetBkMode(hdc, TRANSPARENT);

    static HFONT s_hRegularFont = nullptr;
    static HFONT s_hBoldFont = nullptr;
    if (!s_hRegularFont) {
        s_hRegularFont = reinterpret_cast<HFONT>(GetStockObject(DEFAULT_GUI_FONT));
        LOGFONT lf = {};
        GetObject(s_hRegularFont, sizeof(lf), &lf);
        lf.lfWeight = FW_BOLD;
        s_hBoldFont = CreateFontIndirect(&lf);
    }
    HFONT hFontToUse = (togglable && toggled) ? s_hBoldFont : s_hRegularFont;
    HFONT hOldFont = reinterpret_cast<HFONT>(SelectObject(hdc, hFontToUse));
    DrawTextW(hdc, text, -1, &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    if (isFocused) {
        RECT frc = rc;
        InflateRect(&frc, -3, -3);
        DrawFocusRect(hdc, &frc);
    }
    SelectObject(hdc, hOldFont);
}

// -----------------------------------------------------------------------------
// MIDI Details and Tracks Update Functions
// -----------------------------------------------------------------------------
static const char* GM_NAMES[128] = {
    "Acoustic Grand Piano","Bright Acoustic Piano","Electric Grand Piano","Honky-tonk Piano","Electric Piano 1","Electric Piano 2","Harpsichord","Clavi","Celesta","Glockenspiel","Music Box","Vibraphone","Marimba","Xylophone","Tubular Bells","Dulcimer",
    "Drawbar Organ","Percussive Organ","Rock Organ","Church Organ","Reed Organ","Accordion","Harmonica","Tango Accordion","Acoustic Guitar (nylon)","Acoustic Guitar (steel)","Electric Guitar (jazz)","Electric Guitar (clean)","Electric Guitar (muted)","Overdriven Guitar","Distortion Guitar","Guitar harmonics",
    "Acoustic Bass","Electric Bass (finger)","Electric Bass (pick)","Fretless Bass","Slap Bass 1","Slap Bass 2","Synth Bass 1","Synth Bass 2","Violin","Viola","Cello","Contrabass","Tremolo Strings","Pizzicato Strings","Orchestral Harp","Timpani",
    "String Ensemble 1","String Ensemble 2","SynthStrings 1","SynthStrings 2","Choir Aahs","Voice Oohs","Synth Voice","Orchestra Hit","Trumpet","Trombone","Tuba","Muted Trumpet","French Horn","Brass Section","SynthBrass 1","SynthBrass 2",
    "Soprano Sax","Alto Sax","Tenor Sax","Baritone Sax","Oboe","English Horn","Bassoon","Clarinet","Piccolo","Flute","Recorder","Pan Flute","Blown Bottle","Shakuhachi","Whistle","Ocarina",
    "Lead 1 (square)","Lead 2 (sawtooth)","Lead 3 (calliope)","Lead 4 (chiff)","Lead 5 (charang)","Lead 6 (voice)","Lead 7 (fifths)","Lead 8 (bass + lead)","Pad 1 (new age)","Pad 2 (warm)","Pad 3 (polysynth)","Pad 4 (choir)","Pad 5 (bowed)","Pad 6 (metallic)","Pad 7 (halo)","Pad 8 (sweep)",
    "FX 1 (rain)","FX 2 (soundtrack)","FX 3 (crystal)","FX 4 (atmosphere)","FX 5 (brightness)","FX 6 (goblins)","FX 7 (echoes)","FX 8 (sci-fi)","Sitar","Banjo","Shamisen","Koto","Kalimba","Bag pipe","Fiddle","Shanai",
    "Tinkle Bell","Agogo","Steel Drums","Woodblock","Taiko Drum","Melodic Tom","Synth Drum","Reverse Cymbal","Guitar Fret Noise","Breath Noise","Seashore","Bird Tweet","Telephone Ring","Helicopter","Applause","Gunshot"
};

static void UpdateMidiDetails() {
    if (!g_player)
        return;
    MidiFile& mf = g_player->midi_file;
    SetWindowTextW(g_editDetails, L"");

    auto appendLine = [&](const std::wstring& line) {
        std::wstring s = line + L"\r\n";
        SendMessageW(g_editDetails, EM_REPLACESEL, FALSE, reinterpret_cast<LPARAM>(s.c_str()));
        };

    std::wstring wpath = !g_currentLoadedMidiPath.empty() ? g_currentLoadedMidiPath : GetSelectedMidiFullPath();
    if (!wpath.empty()) {
        std::filesystem::path p(wpath);
        appendLine(L"File: " + p.filename().wstring());
    }

    std::wostringstream oss;
    oss << std::left;
    oss.str(L"");
    oss << "Format: " << mf.format;
    switch (mf.format) {
    case 0: oss << " (single)"; break;
    case 1: oss << " (multi)"; break;
    case 2: oss << " (multi-song)"; break;
    }
    appendLine(oss.str());

    int activeTracks = 0;
    for (const auto& track : mf.tracks) {
        if (!track.events.empty())
            ++activeTracks;
    }
    oss.str(L"");
    oss << "Tracks: " << activeTracks << "/" << mf.numTracks;
    int totalNotes = 0;
    for (const auto& track : mf.tracks) {
        for (const auto& evt : track.events) {
            if ((evt.status & 0xF0) == 0x90 && evt.data2 > 0)
                ++totalNotes;
        }
    }
    oss << " (" << totalNotes << " notes)";
    appendLine(oss.str());

    int minPitch = 128, maxPitch = -1, sustainEvents = 0;
    for (const auto& track : mf.tracks) {
        for (const auto& evt : track.events) {
            if ((evt.status & 0xF0) == 0x90 && evt.data2 > 0) {
                minPitch = std::min(minPitch, static_cast<int>(evt.data1));
                maxPitch = std::max(maxPitch, static_cast<int>(evt.data1));
            }
            if ((evt.status & 0xF0) == 0xB0 && evt.data1 == 64)
                ++sustainEvents;
        }
    }
    auto noteLabel = [](int midiNote) {
        static const wchar_t* names[] = { L"C",L"C#",L"D",L"D#",L"E",L"F",L"F#",L"G",L"G#",L"A",L"A#",L"B" };
        if (midiNote < 0 || midiNote > 127) return std::wstring(L"-");
        std::wostringstream n;
        n << names[midiNote % 12] << (midiNote / 12 - 1);
        return n.str();
    };
    if (minPitch <= maxPitch) {
        oss.str(L"");
        oss << L"Pitch Range: " << noteLabel(minPitch) << L" - " << noteLabel(maxPitch);
        appendLine(oss.str());
    }
    oss.str(L"");
    oss << L"Duration: " << static_cast<int>(g_totalSongSeconds) / 60 << L":"
        << std::setw(2) << std::setfill(L'0') << static_cast<int>(g_totalSongSeconds) % 60
        << L"   Sustain Events: " << sustainEvents;
    appendLine(oss.str());
    oss << std::setfill(L' ');

    int peakPolyphony = 0, activePolyphony = 0;
    for (const auto& evt : g_player->note_events) {
        if (evt.note_or_control == "sustain") continue;
        if (evt.action == EventType::Press)
            peakPolyphony = std::max(peakPolyphony, ++activePolyphony);
        else
            activePolyphony = std::max(0, activePolyphony - 1);
    }
    oss.str(L"");
    oss << L"Peak Polyphony: " << peakPolyphony;
    appendLine(oss.str());

    if (!mf.tempoChanges.empty()) {
        double initialTempo = mf.tempoChanges[0].microsecondsPerQuarter;
        double bpm = 60000000.0 / initialTempo;
        oss.str(L"");
        oss << "Tempo: " << std::fixed << std::setprecision(1) << bpm << " BPM";
        if (mf.tempoChanges.size() > 1)
            oss << " (" << (mf.tempoChanges.size() - 1) << " changes)";
        appendLine(oss.str());
    }
    if (!mf.timeSignatures.empty()) {
        auto& ts = mf.timeSignatures[0];
        oss.str(L"");
        oss << "Time Sig: " << static_cast<int>(ts.numerator) << "/" << static_cast<int>(ts.denominator);
        if (mf.timeSignatures.size() > 1)
            oss << " (" << (mf.timeSignatures.size() - 1) << " changes)";
        appendLine(oss.str());
    }
    std::string modeStr;
    switch (midi::Config::getInstance().playback.noteHandlingMode) {
    case midi::NoteHandlingMode::FIFO: modeStr = "FIFO"; break;
    case midi::NoteHandlingMode::LIFO: modeStr = "LIFO"; break;
    default: modeStr = "None"; break;
    }
    std::string lastLine = "Note Mode: " + modeStr;
    bool humanizer = midi::Config::getInstance().humanizer.ENABLED;
    bool filterDrums = midi::Config::getInstance().midi.FILTER_DRUMS;
    lastLine += (humanizer ? " (Humanizer: On)" : " (Humanizer: Off)");
    if (humanizer)
        lastLine += " (Preset: " + midi::Config::getInstance().activeHumanizerPreset + ")";
    lastLine += (filterDrums ? " (Ch10 Filter: On)" : " (Ch10 Filter: Off)");
    lastLine += (midi::Config::getInstance().playability.ENABLED ? " (Optimizer: On)" : " (Optimizer: Off)");
    SendMessageA(g_editDetails, EM_REPLACESEL, FALSE, reinterpret_cast<LPARAM>(lastLine.c_str()));
}
static void UpdateTrackInfo() {
    if (!g_player) {
        std::vector<TrackControl::TrackInfo> empty;
        g_trackControl.SetTracks(empty);
        return;
    }
    MidiFile& mf = g_player->midi_file;
    std::vector<TrackControl::TrackInfo> tracks;
    for (size_t trackIndex = 0; trackIndex < mf.tracks.size(); ++trackIndex) {
        TrackControl::TrackInfo info;
        info.isMuted = false;
        info.isSoloed = false;
        info.isDrums = false; // initialize flag

        if (trackIndex < g_player->trackMuted.size() && g_player->trackMuted[trackIndex])
            info.isMuted = g_player->trackMuted[trackIndex]->load(std::memory_order_acquire);
        if (trackIndex < g_player->trackSoloed.size() && g_player->trackSoloed[trackIndex])
            info.isSoloed = g_player->trackSoloed[trackIndex]->load(std::memory_order_acquire);

        const auto& track = mf.tracks[trackIndex];
        int noteCount = 0;
        std::unordered_map<int, int> channelCounts;
        std::string trackName;
        for (const auto& evt : track.events) {
            if ((evt.status & 0xF0) == 0x90 && evt.data2 > 0) {
                ++noteCount;
                channelCounts[evt.status & 0x0F]++;
            }
            if ((evt.status & 0xF0) == 0xC0)
                info.programNumber = evt.data1 & 0x7F;
            if (evt.status == 0xFF && evt.data1 == 0x03)
                trackName = std::string(evt.metaData.begin(), evt.metaData.end());
        }
        if (!channelCounts.empty()) {
            info.channel = std::max_element(channelCounts.begin(), channelCounts.end(),
                [](const auto& p1, const auto& p2) {
                    return p1.second < p2.second;
                })->first;
        }
        info.noteCount = noteCount;
        info.trackName = trackName.empty() ? ("Track " + std::to_string(trackIndex + 1)) : trackName;
        if (info.programNumber >= 0 && info.programNumber < 128) {
            info.instrumentName = GM_NAMES[info.programNumber];
            if (g_player->drum_flags.size() > trackIndex && g_player->drum_flags[trackIndex]) {
                info.instrumentName += " (Drums)";
                info.isDrums = true;
            }
        }
        else {
            info.instrumentName = "Unknown";
        }
        tracks.push_back(info);
    }
    g_trackControl.SetTracks(tracks);
}
static void FocusRobloxWindowInternal() {
    HWND hRb = FindWindowW(nullptr, L"Roblox");
    if (!hRb) {
        std::cerr << "[WARNING] Could not find Roblox window.\n";
        return;
    }
    if (!IsWindow(hRb)) {
        std::cerr << "[ERROR] Found handle is not a valid window.\n";
        return;
    }
    DWORD_PTR dwResult = 0;
    if (SendMessageTimeout(hRb, WM_NULL, 0, 0, SMTO_ABORTIFHUNG, 500, &dwResult) == 0) {
        std::cerr << "[WARNING] Roblox window is not responding; skipping focus.\n";
        return;
    }
    if (!IsWindowVisible(hRb)) {
        std::cerr << "[WARNING] Roblox window is not visible; skipping focus to avoid invasive changes.\n";
        return;
    }
    if (IsIconic(hRb)) {
        ShowWindow(hRb, SW_RESTORE);
    }
    else {
        ShowWindow(hRb, SW_SHOWNA);
    }
    if (!SetForegroundWindow(hRb)) {
        std::cerr << "[ERROR] Failed to bring Roblox window to foreground. Error code: " << GetLastError() << "\n";
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
}

static void FocusRobloxWindow() {
    std::thread(FocusRobloxWindowInternal).detach();
}

static void ClearLog(HWND editLog) {
    if (!editLog) return;
    {
        std::lock_guard<std::mutex> lk(g_logMutex);
        g_logBuffer.clear();
    }
    if (!SetWindowTextW(editLog, L"")) {
        DWORD error = GetLastError();
        std::cerr << "Failed to clear log. Error code: " << error << std::endl;
    }
}

static void ToggleFavorite(int index) {
    if (index < 0 || index >= static_cast<int>(g_midiItems.size()))
        return;
    MidiItem& item = g_midiItems[index];
    if (item.isFolder)
        return;

    std::filesystem::path filePath(item.fullPath);
    std::error_code ec;
    if (filePath.parent_path().filename() == L"favorite") {
        std::filesystem::remove(filePath, ec);
        if (!ec) {
            std::filesystem::path origPath = std::filesystem::path(L"midi") / filePath.filename();
            item.fullPath = origPath.wstring();
        }
    }
    else {
        std::filesystem::path destFolder = std::filesystem::path(L"midi") / L"favorite";
        if (!std::filesystem::exists(destFolder)) {
            std::filesystem::create_directories(destFolder, ec);
            if (ec)
                return; // silently fail if folder creation fails
        }
        std::filesystem::path destFile = destFolder / filePath.filename();
        std::filesystem::copy_file(filePath, destFile, std::filesystem::copy_options::overwrite_existing, ec);
        if (!ec) {
            item.fullPath = destFile.wstring();
        }
    }

    if (g_lbMidi) {
        std::wstring displayName;
        if (item.name == L"..") {
            displayName = L".. (Back)";
        }
        else if (item.isFolder) {
            displayName = item.name + L"\\";
        }
        else {
            displayName = item.name;
            std::filesystem::path p(item.fullPath);
            if (p.parent_path().filename() == L"favorite")
                displayName = L"★ " + displayName;
        }
        SendMessageW(g_lbMidi, LB_DELETESTRING, index, 0);
        SendMessageW(g_lbMidi, LB_INSERTSTRING, index, reinterpret_cast<LPARAM>(displayName.c_str()));
    }
}

static LRESULT CALLBACK MidiListSubclassProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam, UINT_PTR uIdSubclass, DWORD_PTR dwRefData)
{
    switch (msg)
    {
    case WM_RBUTTONDOWN:
    {
        POINT pt;
        pt.x = GET_X_LPARAM(lParam);
        pt.y = GET_Y_LPARAM(lParam);
        int index = static_cast<int>(SendMessage(hwnd, LB_ITEMFROMPOINT, 0, MAKELPARAM(pt.x, pt.y)));
        if (index != LB_ERR) {
            ToggleFavorite(index);
        }
        return 0;
    }
    default:
        return DefSubclassProc(hwnd, msg, wParam, lParam);
    }
}

static bool LoadMidiFilePath(HWND owner, const std::wstring& wpath, bool preserveSession) {
    if (!g_player || wpath.empty())
        return false;

    std::vector<bool> previousMuted;
    std::vector<bool> previousSoloed;
    const double previousSpeed = g_player->current_speed;
    if (preserveSession) {
        previousMuted.reserve(g_player->trackMuted.size());
        previousSoloed.reserve(g_player->trackSoloed.size());
        for (const auto& value : g_player->trackMuted)
            previousMuted.push_back(value && value->load(std::memory_order_acquire));
        for (const auto& value : g_player->trackSoloed)
            previousSoloed.push_back(value && value->load(std::memory_order_acquire));
    }

    try {
        std::cout << (preserveSession ? "[Reload] Rebuilding current MIDI...\n" : "[Load] Initiating load process...\n");
        g_player->should_stop.store(true, std::memory_order_release);
        SetEvent(g_player->command_event);
        {
            std::lock_guard<std::mutex> lock(g_player->playback_cv_mutex);
            g_player->playback_cv.notify_all();
        }
        if (g_player->playback_thread && g_player->playback_thread->joinable())
            g_player->playback_thread->join();
        g_player->playback_thread.reset();

        g_player->paused.store(true, std::memory_order_release);
        g_player->release_all_keys();
        g_player->midiFileSelected.store(false, std::memory_order_release);
        g_player->note_events.clear();
        g_player->tempo_changes.clear();
        g_player->timeSignatures.clear();
        g_player->trackMuted.clear();
        g_player->trackSoloed.clear();

        const std::string path = WideToUtf8(wpath);
        MidiParser parser;
        g_player->midi_file = parser.parse(path);
        g_player->process_tracks(g_player->midi_file);
        g_player->midiFileSelected.store(true, std::memory_order_release);

        g_player->should_stop.store(false, std::memory_order_release);
        g_player->paused.store(true, std::memory_order_release);
        g_player->playback_started.store(false, std::memory_order_release);
        constexpr auto initialBuffer = std::chrono::milliseconds(50);
        g_player->total_adjusted_time = -initialBuffer;
        g_player->current_speed = preserveSession ? previousSpeed : 1.0;
        g_player->buffer_index.store(0, std::memory_order_release);
        const unsigned long long nowTsc = __rdtsc();
        g_player->playback_start_time = nowTsc;
        g_player->last_resume_tsc = nowTsc;

        const size_t trackCount = g_player->midi_file.tracks.size();
        g_player->trackMuted.resize(trackCount);
        g_player->trackSoloed.resize(trackCount);
        for (size_t i = 0; i < trackCount; ++i) {
            const bool muted = preserveSession && i < previousMuted.size() ? previousMuted[i] : false;
            const bool soloed = preserveSession && i < previousSoloed.size() ? previousSoloed[i] : false;
            g_player->trackMuted[i] = std::make_shared<std::atomic<bool>>(muted);
            g_player->trackSoloed[i] = std::make_shared<std::atomic<bool>>(soloed);
        }

        g_totalSongSeconds = 0.0;
        if (!g_player->note_events.empty()) {
            auto lastEvent = std::max_element(g_player->note_events.begin(), g_player->note_events.end(),
                [](const auto& a, const auto& b) { return a.time < b.time; });
            if (lastEvent != g_player->note_events.end())
                g_totalSongSeconds = static_cast<double>(lastEvent->time.count()) / 1e9 + 0.5;
        }

        g_currentLoadedMidiPath = wpath;
        RememberRecentMidi(owner, wpath);

        wchar_t timeStr[32];
        const int totalMins = static_cast<int>(g_totalSongSeconds) / 60;
        const int totalSecs = static_cast<int>(g_totalSongSeconds) % 60;
        swprintf_s(timeStr, L"0:00 / %d:%02d", totalMins, totalSecs);
        SetWindowTextW(GetDlgItem(owner, ID_STATIC_TIME), timeStr);
        if (HWND seek = GetDlgItem(owner, ID_SLIDER_SEEK))
            SendMessage(seek, TBM_SETPOS, TRUE, 0);

        UpdateMidiDetails();
        UpdateTrackInfo();
        if (g_toggleStates[ID_BTN_VOLADJ]) {
            FocusRobloxWindow();
            g_player->calibrate_volume();
        }
        std::cout << (preserveSession ? "[Reload] Rebuilt: " : "[Load] Loaded: ") << path << "\n";
        return true;
    }
    catch (const std::exception& e) {
        std::cout << "[Load] Error: " << e.what() << "\n";
        SetWindowTextW(GetDlgItem(owner, ID_STATIC_TIME), L"0:00 / 0:00");
        UpdateMidiDetails();
        UpdateTrackInfo();
        return false;
    }
}

static bool ReloadCurrentMidi(HWND owner) {
    if (g_currentLoadedMidiPath.empty() || !std::filesystem::exists(std::filesystem::path(g_currentLoadedMidiPath))) {
        std::cout << "[Reload] No currently loaded MIDI file is available.\n";
        return false;
    }
    return LoadMidiFilePath(owner, g_currentLoadedMidiPath, true);
}

// -----------------------------------------------------------------------------
// Humanizer / Help popups
// -----------------------------------------------------------------------------
enum HumanizerPopupID {
    ID_HUM_ENABLED = 4101,
    ID_HUM_PRESET,
    ID_HUM_PRESET_NAME,
    ID_HUM_DESCRIPTION,
    ID_HUM_CHORD_WINDOW,
    ID_HUM_PRESS_MIN,
    ID_HUM_PRESS_MAX,
    ID_HUM_RELEASE_MIN,
    ID_HUM_RELEASE_MAX,
    ID_HUM_SIMULTANEOUS,
    ID_HUM_SEQ_ENABLED,
    ID_HUM_SEQ_TRIGGER,
    ID_HUM_SEQ_MIN,
    ID_HUM_SEQ_MAX,
    ID_HUM_REPEATED_GAP,
    ID_HUM_RANDOMIZE,
    ID_HUM_SEED,
    ID_HUM_NEW_PERFORMANCE,
    ID_HUM_APPLY,
    ID_HUM_RESET,
    ID_HUM_SAVE_AS,
    ID_HUM_UPDATE,
    ID_HUM_DELETE,
    ID_HUM_DUPLICATE,
    ID_HUM_EXPORT,
    ID_HUM_IMPORT,
    ID_HUM_CLOSE
};

static void SetDefaultGuiFont(HWND control) {
    if (control)
        SendMessage(control, WM_SETFONT, reinterpret_cast<WPARAM>(GetStockObject(DEFAULT_GUI_FONT)), TRUE);
}

static HWND CreatePopupLabel(HWND parent, const wchar_t* textValue, int x, int y, int w = 260) {
    HWND h = CreateWindowW(L"static", textValue, WS_CHILD | WS_VISIBLE,
        x, y, w, 20, parent, nullptr, g_hInst, nullptr);
    SetDefaultGuiFont(h);
    return h;
}

static HWND CreatePopupEdit(HWND parent, int id, int value, int x, int y, int w = 90) {
    wchar_t buffer[32];
    swprintf_s(buffer, L"%d", value);
    HWND h = CreateWindowExW(WS_EX_CLIENTEDGE, L"edit", buffer,
        WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_NUMBER | ES_RIGHT,
        x, y, w, 22, parent, reinterpret_cast<HMENU>(id), g_hInst, nullptr);
    SetDefaultGuiFont(h);
    return h;
}

static HWND CreatePopupCheck(HWND parent, int id, const wchar_t* textValue, bool checked, int x, int y, int w = 250) {
    HWND h = CreateWindowW(L"button", textValue,
        WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
        x, y, w, 22, parent, reinterpret_cast<HMENU>(id), g_hInst, nullptr);
    SendMessage(h, BM_SETCHECK, checked ? BST_CHECKED : BST_UNCHECKED, 0);
    SetDefaultGuiFont(h);
    return h;
}

static int ReadPopupInt(HWND hwnd, int id, int fallback, int maxValue) {
    wchar_t buffer[64]{};
    GetWindowTextW(GetDlgItem(hwnd, id), buffer, 64);
    wchar_t* end = nullptr;
    long value = wcstol(buffer, &end, 10);
    if (end == buffer)
        value = fallback;
    value = std::clamp<long>(value, 0, maxValue);
    return static_cast<int>(value);
}

static void CenterPopup(HWND popup, HWND owner) {
    RECT pr{}, orc{};
    GetWindowRect(popup, &pr);
    if (owner && GetWindowRect(owner, &orc)) {
        const int x = orc.left + ((orc.right - orc.left) - (pr.right - pr.left)) / 2;
        const int y = orc.top + ((orc.bottom - orc.top) - (pr.bottom - pr.top)) / 2;
        SetWindowPos(popup, nullptr, std::max(0, x), std::max(0, y), 0, 0,
            SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
}

static midi::HumanizerSettings BuiltInHumanizerPreset(const std::string& name, std::uint64_t seed) {
    midi::HumanizerSettings h{};
    h.ENABLED = true;
    h.SEQUENTIAL_ARTICULATION = true;
    h.RANDOMIZE_EACH_PLAY = false;
    h.PERFORMANCE_SEED = seed;
    if (name == "Professional") {
        h.CHORD_DETECTION_WINDOW_MS = 20;
        h.CHORD_PRESS_MIN_SPREAD_MS = 12;
        h.CHORD_PRESS_MAX_SPREAD_MS = 35;
        h.CHORD_RELEASE_MIN_SPREAD_MS = 8;
        h.CHORD_RELEASE_MAX_SPREAD_MS = 25;
        h.SIMULTANEOUS_FINGER_CHANCE_PERCENT = 18;
        h.SEQUENTIAL_TRIGGER_WINDOW_MS = 170;
        h.SEQUENTIAL_MIN_GAP_MS = 8;
        h.SEQUENTIAL_MAX_GAP_MS = 25;
    }
    else if (name == "Intermediate") {
        h.CHORD_DETECTION_WINDOW_MS = 35;
        h.CHORD_PRESS_MIN_SPREAD_MS = 25;
        h.CHORD_PRESS_MAX_SPREAD_MS = 60;
        h.CHORD_RELEASE_MIN_SPREAD_MS = 18;
        h.CHORD_RELEASE_MAX_SPREAD_MS = 45;
        h.SIMULTANEOUS_FINGER_CHANCE_PERCENT = 12;
        h.SEQUENTIAL_TRIGGER_WINDOW_MS = 200;
        h.SEQUENTIAL_MIN_GAP_MS = 20;
        h.SEQUENTIAL_MAX_GAP_MS = 55;
    }
    else {
        h.CHORD_DETECTION_WINDOW_MS = 50;
        h.CHORD_PRESS_MIN_SPREAD_MS = 32;
        h.CHORD_PRESS_MAX_SPREAD_MS = 78;
        h.CHORD_RELEASE_MIN_SPREAD_MS = 25;
        h.CHORD_RELEASE_MAX_SPREAD_MS = 64;
        h.SIMULTANEOUS_FINGER_CHANCE_PERCENT = 10;
        h.SEQUENTIAL_TRIGGER_WINDOW_MS = 200;
        h.SEQUENTIAL_MIN_GAP_MS = 40;
        h.SEQUENTIAL_MAX_GAP_MS = 100;
    }
    return h;
}

static bool HumanizerTimingEqual(const midi::HumanizerSettings& a, const midi::HumanizerSettings& b) {
    return a.ENABLED == b.ENABLED &&
        a.CHORD_DETECTION_WINDOW_MS == b.CHORD_DETECTION_WINDOW_MS &&
        a.CHORD_PRESS_MIN_SPREAD_MS == b.CHORD_PRESS_MIN_SPREAD_MS &&
        a.CHORD_PRESS_MAX_SPREAD_MS == b.CHORD_PRESS_MAX_SPREAD_MS &&
        a.CHORD_RELEASE_MIN_SPREAD_MS == b.CHORD_RELEASE_MIN_SPREAD_MS &&
        a.CHORD_RELEASE_MAX_SPREAD_MS == b.CHORD_RELEASE_MAX_SPREAD_MS &&
        a.SIMULTANEOUS_FINGER_CHANCE_PERCENT == b.SIMULTANEOUS_FINGER_CHANCE_PERCENT &&
        a.SEQUENTIAL_ARTICULATION == b.SEQUENTIAL_ARTICULATION &&
        a.SEQUENTIAL_TRIGGER_WINDOW_MS == b.SEQUENTIAL_TRIGGER_WINDOW_MS &&
        a.SEQUENTIAL_MIN_GAP_MS == b.SEQUENTIAL_MIN_GAP_MS &&
        a.SEQUENTIAL_MAX_GAP_MS == b.SEQUENTIAL_MAX_GAP_MS &&
        a.RANDOMIZE_EACH_PLAY == b.RANDOMIZE_EACH_PLAY;
}

static bool IsBuiltInPresetName(const std::string& name) {
    return name == "Professional" || name == "Intermediate" || name == "Casual";
}

static bool FindHumanizerPreset(const std::string& name, midi::HumanizerSettings& out) {
    auto& cfg = midi::Config::getInstance();
    if (IsBuiltInPresetName(name)) {
        out = BuiltInHumanizerPreset(name, cfg.humanizer.PERFORMANCE_SEED);
        return true;
    }
    for (const auto& preset : cfg.customHumanizerPresets) {
        if (preset.name == name) {
            out = preset.settings;
            return true;
        }
    }
    return false;
}

static std::string HumanizerPresetDescription(const std::string& name) {
    if (name == "Professional") return "Tight, polished timing with subtle natural finger variation.";
    if (name == "Intermediate") return "Controlled hobby-player timing with clearly visible finger separation.";
    if (name == "Casual") return "Looser, visible articulation based on the tested Roblox settings.";
    if (name == "Custom (Modified)") return "Current values differ from the selected saved preset.";
    return "Saved custom Humanizer preset.";
}

static std::string GetComboText(HWND combo) {
    int sel = static_cast<int>(SendMessage(combo, CB_GETCURSEL, 0, 0));
    if (sel == CB_ERR) return {};
    int len = static_cast<int>(SendMessage(combo, CB_GETLBTEXTLEN, sel, 0));
    std::wstring value(static_cast<size_t>(len) + 1, L'\0');
    SendMessageW(combo, CB_GETLBTEXT, sel, reinterpret_cast<LPARAM>(value.data()));
    value.resize(static_cast<size_t>(len));
    return WideToUtf8(value);
}

static void SetHumanizerDescription(HWND hwnd, const std::string& name) {
    std::string description = HumanizerPresetDescription(name);
    SetWindowTextW(GetDlgItem(hwnd, ID_HUM_DESCRIPTION), Utf8ToWide(description).c_str());
}

static void RefreshHumanizerPresetCombo(HWND hwnd) {
    auto& cfg = midi::Config::getInstance();
    HWND combo = GetDlgItem(hwnd, ID_HUM_PRESET);
    SendMessage(combo, CB_RESETCONTENT, 0, 0);
    const wchar_t* builtIns[] = { L"Professional", L"Intermediate", L"Casual" };
    for (const auto* value : builtIns)
        SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(value));
    for (const auto& preset : cfg.customHumanizerPresets) {
        const std::wstring name = Utf8ToWide(preset.name);
        SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(name.c_str()));
    }
    bool found = false;
    const int count = static_cast<int>(SendMessage(combo, CB_GETCOUNT, 0, 0));
    for (int i = 0; i < count; ++i) {
        SendMessage(combo, CB_SETCURSEL, i, 0);
        if (GetComboText(combo) == cfg.activeHumanizerPreset) {
            found = true;
            break;
        }
    }
    if (!found) {
        SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Custom (Modified)"));
        SendMessage(combo, CB_SETCURSEL, count, 0);
    }
    SetHumanizerDescription(hwnd, cfg.activeHumanizerPreset);
}

static void PopulateHumanizerPopup(HWND hwnd) {
    const auto& cfg = midi::Config::getInstance();
    const auto& h = cfg.humanizer;
    RefreshHumanizerPresetCombo(hwnd);
    SendMessage(GetDlgItem(hwnd, ID_HUM_ENABLED), BM_SETCHECK, h.ENABLED ? BST_CHECKED : BST_UNCHECKED, 0);
    SendMessage(GetDlgItem(hwnd, ID_HUM_SEQ_ENABLED), BM_SETCHECK, h.SEQUENTIAL_ARTICULATION ? BST_CHECKED : BST_UNCHECKED, 0);
    SendMessage(GetDlgItem(hwnd, ID_HUM_RANDOMIZE), BM_SETCHECK, h.RANDOMIZE_EACH_PLAY ? BST_CHECKED : BST_UNCHECKED, 0);
    const struct { int id; int value; } values[] = {
        {ID_HUM_CHORD_WINDOW, h.CHORD_DETECTION_WINDOW_MS}, {ID_HUM_PRESS_MIN, h.CHORD_PRESS_MIN_SPREAD_MS},
        {ID_HUM_PRESS_MAX, h.CHORD_PRESS_MAX_SPREAD_MS}, {ID_HUM_RELEASE_MIN, h.CHORD_RELEASE_MIN_SPREAD_MS},
        {ID_HUM_RELEASE_MAX, h.CHORD_RELEASE_MAX_SPREAD_MS}, {ID_HUM_SIMULTANEOUS, h.SIMULTANEOUS_FINGER_CHANCE_PERCENT},
        {ID_HUM_SEQ_TRIGGER, h.SEQUENTIAL_TRIGGER_WINDOW_MS}, {ID_HUM_SEQ_MIN, h.SEQUENTIAL_MIN_GAP_MS},
        {ID_HUM_SEQ_MAX, h.SEQUENTIAL_MAX_GAP_MS}, {ID_HUM_REPEATED_GAP, cfg.playback.REPEATED_NOTE_GAP_MS}
    };
    for (const auto& item : values) {
        wchar_t buffer[32]; swprintf_s(buffer, L"%d", item.value); SetWindowTextW(GetDlgItem(hwnd, item.id), buffer);
    }
    wchar_t seedBuffer[32];
    swprintf_s(seedBuffer, L"%016llX", static_cast<unsigned long long>(h.PERFORMANCE_SEED));
    SetWindowTextW(GetDlgItem(hwnd, ID_HUM_SEED), seedBuffer);
    const std::string current = cfg.activeHumanizerPreset;
    if (!IsBuiltInPresetName(current) && current != "Custom (Modified)")
        SetWindowTextW(GetDlgItem(hwnd, ID_HUM_PRESET_NAME), Utf8ToWide(current).c_str());
    else
        SetWindowTextW(GetDlgItem(hwnd, ID_HUM_PRESET_NAME), L"");
}

static midi::HumanizerSettings ReadHumanizerPopup(HWND hwnd) {
    auto h = midi::Config::getInstance().humanizer;
    h.ENABLED = SendMessage(GetDlgItem(hwnd, ID_HUM_ENABLED), BM_GETCHECK, 0, 0) == BST_CHECKED;
    h.SEQUENTIAL_ARTICULATION = SendMessage(GetDlgItem(hwnd, ID_HUM_SEQ_ENABLED), BM_GETCHECK, 0, 0) == BST_CHECKED;
    h.RANDOMIZE_EACH_PLAY = SendMessage(GetDlgItem(hwnd, ID_HUM_RANDOMIZE), BM_GETCHECK, 0, 0) == BST_CHECKED;
    h.CHORD_DETECTION_WINDOW_MS = ReadPopupInt(hwnd, ID_HUM_CHORD_WINDOW, h.CHORD_DETECTION_WINDOW_MS, 1000);
    h.CHORD_PRESS_MIN_SPREAD_MS = ReadPopupInt(hwnd, ID_HUM_PRESS_MIN, h.CHORD_PRESS_MIN_SPREAD_MS, 1000);
    h.CHORD_PRESS_MAX_SPREAD_MS = ReadPopupInt(hwnd, ID_HUM_PRESS_MAX, h.CHORD_PRESS_MAX_SPREAD_MS, 1000);
    h.CHORD_RELEASE_MIN_SPREAD_MS = ReadPopupInt(hwnd, ID_HUM_RELEASE_MIN, h.CHORD_RELEASE_MIN_SPREAD_MS, 1000);
    h.CHORD_RELEASE_MAX_SPREAD_MS = ReadPopupInt(hwnd, ID_HUM_RELEASE_MAX, h.CHORD_RELEASE_MAX_SPREAD_MS, 1000);
    h.SIMULTANEOUS_FINGER_CHANCE_PERCENT = ReadPopupInt(hwnd, ID_HUM_SIMULTANEOUS, h.SIMULTANEOUS_FINGER_CHANCE_PERCENT, 100);
    h.SEQUENTIAL_TRIGGER_WINDOW_MS = ReadPopupInt(hwnd, ID_HUM_SEQ_TRIGGER, h.SEQUENTIAL_TRIGGER_WINDOW_MS, 1000);
    h.SEQUENTIAL_MIN_GAP_MS = ReadPopupInt(hwnd, ID_HUM_SEQ_MIN, h.SEQUENTIAL_MIN_GAP_MS, 1000);
    h.SEQUENTIAL_MAX_GAP_MS = ReadPopupInt(hwnd, ID_HUM_SEQ_MAX, h.SEQUENTIAL_MAX_GAP_MS, 1000);
    if (h.CHORD_PRESS_MIN_SPREAD_MS > h.CHORD_PRESS_MAX_SPREAD_MS) std::swap(h.CHORD_PRESS_MIN_SPREAD_MS, h.CHORD_PRESS_MAX_SPREAD_MS);
    if (h.CHORD_RELEASE_MIN_SPREAD_MS > h.CHORD_RELEASE_MAX_SPREAD_MS) std::swap(h.CHORD_RELEASE_MIN_SPREAD_MS, h.CHORD_RELEASE_MAX_SPREAD_MS);
    if (h.SEQUENTIAL_MIN_GAP_MS > h.SEQUENTIAL_MAX_GAP_MS) std::swap(h.SEQUENTIAL_MIN_GAP_MS, h.SEQUENTIAL_MAX_GAP_MS);
    h.validate();
    return h;
}

static void SaveAndRebuildHumanizer(HWND hwnd, const std::string& statusText) {
    auto& cfg = midi::Config::getInstance();
    cfg.validate();
    cfg.saveToFile("config.json");
    PopulateHumanizerPopup(hwnd);
    std::cout << "[Humanizer] " << statusText << "\n";
    if (g_player && g_player->midiFileSelected.load(std::memory_order_acquire))
        ReloadCurrentMidi(g_hMainWnd);
    UpdateMidiDetails();
}

static bool ApplyHumanizerPopup(HWND hwnd) {
    auto& cfg = midi::Config::getInstance();
    try {
        cfg.humanizer = ReadHumanizerPopup(hwnd);
        cfg.playback.REPEATED_NOTE_GAP_MS = ReadPopupInt(hwnd, ID_HUM_REPEATED_GAP, cfg.playback.REPEATED_NOTE_GAP_MS, 1000);
        const std::string selected = GetComboText(GetDlgItem(hwnd, ID_HUM_PRESET));
        midi::HumanizerSettings presetSettings;
        if (FindHumanizerPreset(selected, presetSettings) && HumanizerTimingEqual(cfg.humanizer, presetSettings))
            cfg.activeHumanizerPreset = selected;
        else
            cfg.activeHumanizerPreset = "Custom (Modified)";
        SaveAndRebuildHumanizer(hwnd, "Settings applied; current MIDI rebuilt automatically.");
        return true;
    }
    catch (const std::exception& ex) {
        std::wstring message = L"Could not apply Humanizer settings:\n" + Utf8ToWide(ex.what());
        MessageBoxW(hwnd, message.c_str(), L"Humanizer Error", MB_OK | MB_ICONERROR);
        return false;
    }
}

static int FindCustomPresetIndex(const std::string& name) {
    const auto& presets = midi::Config::getInstance().customHumanizerPresets;
    for (size_t i = 0; i < presets.size(); ++i) if (presets[i].name == name) return static_cast<int>(i);
    return -1;
}

static std::string ReadPresetNameEdit(HWND hwnd) {
    wchar_t buffer[128]{}; GetWindowTextW(GetDlgItem(hwnd, ID_HUM_PRESET_NAME), buffer, 128);
    std::wstring value(buffer);
    while (!value.empty() && iswspace(value.front())) value.erase(value.begin());
    while (!value.empty() && iswspace(value.back())) value.pop_back();
    return WideToUtf8(value);
}


static std::string MakeUniqueCustomPresetName(std::string base) {
    if (base.empty())
        base = "Imported Preset";
    if (IsBuiltInPresetName(base) || base == "Custom (Modified)")
        base += " Copy";
    if (FindCustomPresetIndex(base) < 0 && !IsBuiltInPresetName(base))
        return base;

    for (int suffix = 2; suffix < 1000; ++suffix) {
        const std::string candidate = base + " " + std::to_string(suffix);
        if (FindCustomPresetIndex(candidate) < 0 && !IsBuiltInPresetName(candidate))
            return candidate;
    }
    return base + " Copy";
}

static bool ExportHumanizerPreset(HWND hwnd) {
    const std::string selected = GetComboText(GetDlgItem(hwnd, ID_HUM_PRESET));
    midi::HumanizerSettings settings;
    std::string exportName = selected;
    try {
        if (!FindHumanizerPreset(selected, settings)) {
            if (selected != "Custom (Modified)") {
                MessageBoxW(hwnd, L"Select a preset to export.", L"Humanizer Export", MB_OK | MB_ICONINFORMATION);
                return false;
            }
            settings = ReadHumanizerPopup(hwnd);
            exportName = "Custom Humanizer";
        }

        std::wstring suggested = Utf8ToWide(exportName + ".humanizer.json");
        wchar_t fileName[MAX_PATH]{};
        wcsncpy_s(fileName, suggested.c_str(), _TRUNCATE);
        OPENFILENAMEW ofn{};
        ofn.lStructSize = sizeof(ofn);
        ofn.hwndOwner = hwnd;
        ofn.lpstrFilter = L"MIDI++ Humanizer Preset (*.json)\0*.json\0All Files (*.*)\0*.*\0";
        ofn.lpstrFile = fileName;
        ofn.nMaxFile = MAX_PATH;
        ofn.lpstrDefExt = L"json";
        ofn.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST;
        if (!GetSaveFileNameW(&ofn))
            return false;

        nlohmann::json j;
        j["format"] = "MIDI++ Humanizer Preset";
        j["version"] = 1;
        j["name"] = exportName;
        j["settings"] = settings;
        std::ofstream file{ std::filesystem::path(fileName), std::ios::trunc };
        if (!file)
            throw std::runtime_error("Could not open the selected export file.");
        file << j.dump(4);
        std::cout << "[Humanizer] Exported preset " << exportName << ".\n";
        return true;
    }
    catch (const std::exception& ex) {
        MessageBoxW(hwnd, Utf8ToWide(ex.what()).c_str(), L"Humanizer Export Error", MB_OK | MB_ICONERROR);
        return false;
    }
}

static bool ImportHumanizerPreset(HWND hwnd) {
    auto& cfg = midi::Config::getInstance();
    if (cfg.customHumanizerPresets.size() >= midi::Config::MAX_CUSTOM_HUMANIZER_PRESETS) {
        MessageBoxW(hwnd, L"You already have 5 custom presets. Delete one before importing.", L"Humanizer Import", MB_OK | MB_ICONWARNING);
        return false;
    }

    wchar_t fileName[MAX_PATH]{};
    OPENFILENAMEW ofn{};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = hwnd;
    ofn.lpstrFilter = L"MIDI++ Humanizer Preset (*.json)\0*.json\0All Files (*.*)\0*.*\0";
    ofn.lpstrFile = fileName;
    ofn.nMaxFile = MAX_PATH;
    ofn.lpstrDefExt = L"json";
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&ofn))
        return false;

    try {
        std::ifstream file{ std::filesystem::path(fileName) };
        if (!file)
            throw std::runtime_error("Could not open the selected preset file.");
        nlohmann::json j;
        file >> j;
        if (!j.contains("settings"))
            throw std::runtime_error("This file does not contain a Humanizer settings block.");

        midi::HumanizerSettings imported = j.at("settings").get<midi::HumanizerSettings>();
        imported.validate();
        std::string importedName;
        if (j.contains("name") && j.at("name").is_string())
            importedName = j.at("name").get<std::string>();
        if (importedName.empty())
            importedName = WideToUtf8(std::filesystem::path(fileName).stem().wstring());
        importedName = MakeUniqueCustomPresetName(importedName);

        cfg.customHumanizerPresets.push_back({ importedName, imported });
        cfg.humanizer = imported;
        cfg.activeHumanizerPreset = importedName;
        SaveAndRebuildHumanizer(hwnd, "Imported preset " + importedName + ".");
        return true;
    }
    catch (const std::exception& ex) {
        MessageBoxW(hwnd, Utf8ToWide(ex.what()).c_str(), L"Humanizer Import Error", MB_OK | MB_ICONERROR);
        return false;
    }
}

static LRESULT CALLBACK HumanizerWndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_CREATE:
    {
        const auto& cfg = midi::Config::getInstance(); const auto& h = cfg.humanizer;
        CreatePopupLabel(hwnd, L"Preset:", 18, 15, 55);
        HWND presetCombo = CreateWindowW(L"combobox", nullptr, WS_CHILD | WS_VISIBLE | WS_TABSTOP | CBS_DROPDOWNLIST,
            75, 12, 190, 240, hwnd, reinterpret_cast<HMENU>(ID_HUM_PRESET), g_hInst, nullptr); SetDefaultGuiFont(presetCombo);
        CreatePopupLabel(hwnd, L"Custom name:", 278, 15, 90);
        HWND nameEdit = CreateWindowExW(WS_EX_CLIENTEDGE, L"edit", L"", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            365, 12, 170, 22, hwnd, reinterpret_cast<HMENU>(ID_HUM_PRESET_NAME), g_hInst, nullptr); SetDefaultGuiFont(nameEdit);
        HWND saveAs = CreateWindowW(L"button", L"Save As", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 18, 43, 82, 25, hwnd, reinterpret_cast<HMENU>(ID_HUM_SAVE_AS), g_hInst, nullptr);
        HWND update = CreateWindowW(L"button", L"Update/Rename", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 106, 43, 105, 25, hwnd, reinterpret_cast<HMENU>(ID_HUM_UPDATE), g_hInst, nullptr);
        HWND del = CreateWindowW(L"button", L"Delete", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 217, 43, 70, 25, hwnd, reinterpret_cast<HMENU>(ID_HUM_DELETE), g_hInst, nullptr);
        SetDefaultGuiFont(saveAs); SetDefaultGuiFont(update); SetDefaultGuiFont(del);
        HWND desc = CreateWindowW(L"static", L"", WS_CHILD | WS_VISIBLE, 300, 45, 300, 38, hwnd, reinterpret_cast<HMENU>(ID_HUM_DESCRIPTION), g_hInst, nullptr); SetDefaultGuiFont(desc);
        CreatePopupCheck(hwnd, ID_HUM_ENABLED, L"Enable Humanizer", h.ENABLED, 18, 82, 170);
        CreatePopupCheck(hwnd, ID_HUM_SEQ_ENABLED, L"Sequential articulation", h.SEQUENTIAL_ARTICULATION, 195, 82, 180);
        CreatePopupCheck(hwnd, ID_HUM_RANDOMIZE, L"Different timing each play", h.RANDOMIZE_EACH_PLAY, 380, 82, 190);
        const int labelX = 18, editX = 350; int y = 118; const int row = 29;
        CreatePopupLabel(hwnd, L"Chord detection window (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_CHORD_WINDOW, h.CHORD_DETECTION_WINDOW_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Chord press minimum spread (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_PRESS_MIN, h.CHORD_PRESS_MIN_SPREAD_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Chord press maximum spread (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_PRESS_MAX, h.CHORD_PRESS_MAX_SPREAD_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Chord release minimum spread (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_RELEASE_MIN, h.CHORD_RELEASE_MIN_SPREAD_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Chord release maximum spread (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_RELEASE_MAX, h.CHORD_RELEASE_MAX_SPREAD_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Simultaneous finger chance (%)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_SIMULTANEOUS, h.SIMULTANEOUS_FINGER_CHANCE_PERCENT, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Sequential trigger window (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_SEQ_TRIGGER, h.SEQUENTIAL_TRIGGER_WINDOW_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Sequential minimum gap (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_SEQ_MIN, h.SEQUENTIAL_MIN_GAP_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Sequential maximum gap (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_SEQ_MAX, h.SEQUENTIAL_MAX_GAP_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Repeated same-note gap (ms)", labelX, y); CreatePopupEdit(hwnd, ID_HUM_REPEATED_GAP, cfg.playback.REPEATED_NOTE_GAP_MS, editX, y - 2); y += row;
        CreatePopupLabel(hwnd, L"Performance seed", labelX, y, 130);
        HWND seed = CreateWindowExW(WS_EX_CLIENTEDGE, L"edit", L"", WS_CHILD | WS_VISIBLE | ES_READONLY | ES_CENTER, 150, y - 2, 170, 22, hwnd, reinterpret_cast<HMENU>(ID_HUM_SEED), g_hInst, nullptr); SetDefaultGuiFont(seed);
        HWND newPerformance = CreateWindowW(L"button", L"New Performance", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 330, y - 3, 120, 25, hwnd, reinterpret_cast<HMENU>(ID_HUM_NEW_PERFORMANCE), g_hInst, nullptr); SetDefaultGuiFont(newPerformance); y += 33;
        HWND hint = CreateWindowW(L"static", L"Preset changes rebuild the loaded MIDI immediately. Manual edits rebuild when Apply is pressed.", WS_CHILD | WS_VISIBLE, 18, y, 565, 20, hwnd, nullptr, g_hInst, nullptr); SetDefaultGuiFont(hint);
        HWND duplicate = CreateWindowW(L"button", L"Duplicate", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 145, y + 28, 90, 26, hwnd, reinterpret_cast<HMENU>(ID_HUM_DUPLICATE), g_hInst, nullptr);
        HWND exportBtn = CreateWindowW(L"button", L"Export", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 245, y + 28, 90, 26, hwnd, reinterpret_cast<HMENU>(ID_HUM_EXPORT), g_hInst, nullptr);
        HWND importBtn = CreateWindowW(L"button", L"Import", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 345, y + 28, 90, 26, hwnd, reinterpret_cast<HMENU>(ID_HUM_IMPORT), g_hInst, nullptr);
        HWND apply = CreateWindowW(L"button", L"Apply", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON, 160, y + 62, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_APPLY), g_hInst, nullptr);
        HWND reset = CreateWindowW(L"button", L"Reset to Preset", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 258, y + 62, 115, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_RESET), g_hInst, nullptr);
        HWND close = CreateWindowW(L"button", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 381, y + 62, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_CLOSE), g_hInst, nullptr);
        SetDefaultGuiFont(duplicate); SetDefaultGuiFont(exportBtn); SetDefaultGuiFont(importBtn);
        SetDefaultGuiFont(apply); SetDefaultGuiFont(reset); SetDefaultGuiFont(close); PopulateHumanizerPopup(hwnd); return 0;
    }
    case WM_COMMAND:
    {
        const int id = LOWORD(wParam); const int code = HIWORD(wParam);
        if (id == ID_HUM_PRESET && code == CBN_SELCHANGE) {
            const std::string selected = GetComboText(GetDlgItem(hwnd, ID_HUM_PRESET)); midi::HumanizerSettings chosen;
            if (FindHumanizerPreset(selected, chosen)) { auto& cfg = midi::Config::getInstance(); cfg.humanizer = chosen; cfg.activeHumanizerPreset = selected; try { SaveAndRebuildHumanizer(hwnd, "Preset changed to " + selected + "."); } catch (const std::exception& ex) { MessageBoxW(hwnd, Utf8ToWide(ex.what()).c_str(), L"Humanizer Error", MB_OK | MB_ICONERROR); } }
            return 0;
        }
        if (code != BN_CLICKED) break;
        switch (id) {
        case ID_HUM_APPLY: ApplyHumanizerPopup(hwnd); return 0;
        case ID_HUM_RESET:
        { const std::string selected = GetComboText(GetDlgItem(hwnd, ID_HUM_PRESET)); midi::HumanizerSettings chosen; if (!FindHumanizerPreset(selected, chosen)) { MessageBoxW(hwnd, L"Select a built-in or saved preset first.", L"Humanizer", MB_OK | MB_ICONINFORMATION); return 0; } auto& cfg = midi::Config::getInstance(); cfg.humanizer = chosen; cfg.activeHumanizerPreset = selected; SaveAndRebuildHumanizer(hwnd, "Reset to preset " + selected + "."); return 0; }
        case ID_HUM_SAVE_AS:
        { auto& cfg = midi::Config::getInstance(); const std::string name = ReadPresetNameEdit(hwnd); if (name.empty() || IsBuiltInPresetName(name) || name == "Custom (Modified)") { MessageBoxW(hwnd, L"Enter a unique custom preset name.", L"Humanizer", MB_OK | MB_ICONWARNING); return 0; } if (FindCustomPresetIndex(name) >= 0) { MessageBoxW(hwnd, L"That preset already exists. Select it and use Update/Rename.", L"Humanizer", MB_OK | MB_ICONWARNING); return 0; } if (cfg.customHumanizerPresets.size() >= midi::Config::MAX_CUSTOM_HUMANIZER_PRESETS) { MessageBoxW(hwnd, L"You already have 5 custom presets. Delete or update one first.", L"Humanizer", MB_OK | MB_ICONWARNING); return 0; } try { cfg.humanizer = ReadHumanizerPopup(hwnd); cfg.playback.REPEATED_NOTE_GAP_MS = ReadPopupInt(hwnd, ID_HUM_REPEATED_GAP, cfg.playback.REPEATED_NOTE_GAP_MS, 1000); cfg.customHumanizerPresets.push_back({ name, cfg.humanizer }); cfg.activeHumanizerPreset = name; SaveAndRebuildHumanizer(hwnd, "Saved custom preset " + name + "."); } catch (const std::exception& ex) { MessageBoxW(hwnd, Utf8ToWide(ex.what()).c_str(), L"Humanizer Error", MB_OK | MB_ICONERROR); } return 0; }
        case ID_HUM_UPDATE:
        { auto& cfg = midi::Config::getInstance(); const std::string selected = GetComboText(GetDlgItem(hwnd, ID_HUM_PRESET)); const int index = FindCustomPresetIndex(selected); if (index < 0) { MessageBoxW(hwnd, L"Only custom presets can be updated or renamed.", L"Humanizer", MB_OK | MB_ICONINFORMATION); return 0; } std::string newName = ReadPresetNameEdit(hwnd); if (newName.empty()) newName = selected; if (IsBuiltInPresetName(newName) || newName == "Custom (Modified)") { MessageBoxW(hwnd, L"That name is reserved for a built-in preset.", L"Humanizer", MB_OK | MB_ICONWARNING); return 0; } const int duplicate = FindCustomPresetIndex(newName); if (duplicate >= 0 && duplicate != index) { MessageBoxW(hwnd, L"Another custom preset already uses that name.", L"Humanizer", MB_OK | MB_ICONWARNING); return 0; } try { cfg.humanizer = ReadHumanizerPopup(hwnd); cfg.playback.REPEATED_NOTE_GAP_MS = ReadPopupInt(hwnd, ID_HUM_REPEATED_GAP, cfg.playback.REPEATED_NOTE_GAP_MS, 1000); cfg.customHumanizerPresets[static_cast<size_t>(index)].name = newName; cfg.customHumanizerPresets[static_cast<size_t>(index)].settings = cfg.humanizer; cfg.activeHumanizerPreset = newName; SaveAndRebuildHumanizer(hwnd, "Updated custom preset " + newName + "."); } catch (const std::exception& ex) { MessageBoxW(hwnd, Utf8ToWide(ex.what()).c_str(), L"Humanizer Error", MB_OK | MB_ICONERROR); } return 0; }
        case ID_HUM_DUPLICATE:
        {
            auto& cfg = midi::Config::getInstance();
            if (cfg.customHumanizerPresets.size() >= midi::Config::MAX_CUSTOM_HUMANIZER_PRESETS) {
                MessageBoxW(hwnd, L"You already have 5 custom presets. Delete one before duplicating.", L"Humanizer", MB_OK | MB_ICONWARNING);
                return 0;
            }
            const std::string selected = GetComboText(GetDlgItem(hwnd, ID_HUM_PRESET));
            midi::HumanizerSettings source;
            if (!FindHumanizerPreset(selected, source)) {
                MessageBoxW(hwnd, L"Select a built-in or saved preset to duplicate.", L"Humanizer", MB_OK | MB_ICONINFORMATION);
                return 0;
            }
            std::string requested = ReadPresetNameEdit(hwnd);
            if (requested.empty() || requested == selected)
                requested = selected + " Copy";
            const std::string duplicateName = MakeUniqueCustomPresetName(requested);
            cfg.customHumanizerPresets.push_back({ duplicateName, source });
            cfg.humanizer = source;
            cfg.activeHumanizerPreset = duplicateName;
            cfg.saveToFile("config.json");
            PopulateHumanizerPopup(hwnd);
            std::cout << "[Humanizer] Duplicated " << selected << " as " << duplicateName << ".\n";
            return 0;
        }
        case ID_HUM_EXPORT: ExportHumanizerPreset(hwnd); return 0;
        case ID_HUM_IMPORT: ImportHumanizerPreset(hwnd); return 0;
        case ID_HUM_DELETE:
        { auto& cfg = midi::Config::getInstance(); const std::string selected = GetComboText(GetDlgItem(hwnd, ID_HUM_PRESET)); const int index = FindCustomPresetIndex(selected); if (index < 0) { MessageBoxW(hwnd, L"Built-in presets cannot be deleted.", L"Humanizer", MB_OK | MB_ICONINFORMATION); return 0; } cfg.customHumanizerPresets.erase(cfg.customHumanizerPresets.begin() + index); cfg.activeHumanizerPreset = "Custom (Modified)"; cfg.saveToFile("config.json"); PopulateHumanizerPopup(hwnd); std::cout << "[Humanizer] Deleted custom preset " << selected << ".\n"; return 0; }
        case ID_HUM_NEW_PERFORMANCE:
        { auto& cfg = midi::Config::getInstance(); std::uint64_t seed = static_cast<std::uint64_t>(std::chrono::high_resolution_clock::now().time_since_epoch().count()); seed ^= static_cast<std::uint64_t>(GetTickCount64()) << 17; if (seed == 0) seed = 0x6d6964692b2b4831ULL; cfg.humanizer.PERFORMANCE_SEED = seed; SaveAndRebuildHumanizer(hwnd, "Generated a new repeatable performance seed."); return 0; }
        case ID_HUM_CLOSE: DestroyWindow(hwnd); return 0;
        }
        break;
    }
    case WM_CLOSE: DestroyWindow(hwnd); return 0;
    case WM_DESTROY: g_hHumanizerWnd = nullptr; return 0;
    }
    return DefWindowProcW(hwnd, msg, wParam, lParam);
}

static void ShowHumanizerPopup(HWND owner) {
    if (g_hHumanizerWnd && IsWindow(g_hHumanizerWnd)) { ShowWindow(g_hHumanizerWnd, SW_SHOWNORMAL); SetForegroundWindow(g_hHumanizerWnd); return; }
    static bool registered = false;
    if (!registered) { WNDCLASSEXW wc{}; wc.cbSize = sizeof(wc); wc.lpfnWndProc = HumanizerWndProc; wc.hInstance = g_hInst; wc.hCursor = LoadCursor(nullptr, IDC_ARROW); wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_BTNFACE + 1); wc.lpszClassName = L"MIDIPlusPlusHumanizerPopup"; RegisterClassExW(&wc); registered = true; }
    g_hHumanizerWnd = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_DLGMODALFRAME, L"MIDIPlusPlusHumanizerPopup", L"MIDI++ Custom Build - Humanizer", WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU, CW_USEDEFAULT, CW_USEDEFAULT, 625, 580, owner, nullptr, g_hInst, nullptr);
    if (g_hHumanizerWnd) { CenterPopup(g_hHumanizerWnd, owner); ShowWindow(g_hHumanizerWnd, SW_SHOW); SetForegroundWindow(g_hHumanizerWnd); }
}

static const wchar_t* kHelpText =
    L"MIDI++ Custom Build - Quick Help\r\n"
    L"================================\r\n\r\n"
    L"GETTING STARTED\r\n"
    L"1. Put .mid/.midi files in the midi folder beside MIDI++.exe.\r\n"
    L"2. Select a file or folder on the left and press Load.\r\n"
    L"3. Press Play/Pause (F1) to start or pause. F2 rewinds, F3 skips, F4 panics/releases all notes without closing MIDI++.\r\n\r\n"
    L"PLAYBACK (BASIC)\r\n"
    L"Load: Parses the selected MIDI.  Restart: returns to the beginning.\r\n"
    L"Skip+10 / Rew-10: moves through the song. Speed++ / Speed-- changes playback speed.\r\n"
    L"Midi2Key: maps a physical MIDI keyboard to QWERTY keys. MidiConnect is the alternate MIDI connection mode.\r\n\r\n"
    L"ADVANCED\r\n"
    L"88-Key: uses the full configured keyboard range instead of the limited layout.\r\n"
    L"AutoVol: enables automatic velocity/volume handling. Velocity: enables velocity-aware playback.\r\n"
    L"Sustain: enables MIDI sustain behavior. Transpose / OutRange: controls transposition and out-of-range handling.\r\n"
    L"Sustain Cutoff: threshold used for sustain handling. VelCurve: selects how MIDI velocity maps to output volume.\r\n\r\n"
    L"HUMANIZER\r\n"
    L"Enable Humanizer: turns human timing simulation on/off.\r\n"
    L"Chord detection window: how close Note Ons may be and still count as one chord/hand gesture.\r\n"
    L"Chord press min/max spread: total time across fingers landing on a 2-5 note chord.\r\n"
    L"Chord release min/max spread: how unevenly chord fingers lift. At least one may stay to the MIDI's original Note Off.\r\n"
    L"Simultaneous finger chance: chance that neighboring simulated finger actions share the same timestamp.\r\n"
    L"Sequential articulation: humanizes ordinary note-to-note movement, not only chords.\r\n"
    L"Sequential trigger window: next same-hand gesture must begin within this distance of the current note's original end.\r\n"
    L"Sequential min/max gap: desired key-up space before the next same-hand note. The next note is never intentionally delayed.\r\n"
    L"Repeated same-note gap: hard minimum release gap for repetitions such as A-A-A when timing allows.\r\n"
    L"Different timing each play: off = repeatable timing; on = a new micro-performance each load/play.\r\n"
    L"Duplicate/Export/Import: copy presets locally or move a Humanizer preset between MIDI++ installs.\r\n\r\n"
    L"TIMING\r\n"
    L"1000 ms = 1 second. Values from 0-1000 ms are accepted. Large values can intentionally create exaggerated/sloppy playing.\r\n"
    L"The Humanizer never starts a note earlier than the MIDI and never extends a note past its original Note Off.\r\n"
    L"If a requested timing value is impossible for a very short note, MIDI++ uses as much as physically fits.\r\n\r\n"
    L"HUMANIZER 2.0 ADVANCED CONFIG\r\n"
    L"Better hand inference is enabled by default and tracks left/right staff clues plus recent hand position.\r\n"
    L"Tempo-aware timing, melody-priority timing, and velocity humanization are config-only and disabled by default.\r\n"
    L"Velocity Humanizer modes: BALANCED, MELODY_FOCUS, CHORD_FOCUS.\r\n"
    L"Playability is the visible optional toggle; it limits simultaneous physical attacks, not sustain-held sounding notes.\r\n\r\n"
    L"CONFIG SAFETY\r\n"
    L"If config.json cannot be loaded, MIDI++ no longer overwrites it. It uses defaults for that launch and creates config.invalid.backup.json plus config_error.txt.\r\n";

static LRESULT CALLBACK HelpWndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
    case WM_CREATE:
    {
        HWND edit = CreateWindowExW(WS_EX_CLIENTEDGE, L"edit", kHelpText,
            WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL,
            10, 10, 650, 430, hwnd, nullptr, g_hInst, nullptr);
        SetDefaultGuiFont(edit);
        HWND close = CreateWindowW(L"button", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
            570, 450, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_CLOSE), g_hInst, nullptr);
        SetDefaultGuiFont(close);
        return 0;
    }
    case WM_COMMAND:
        if (LOWORD(wParam) == ID_HUM_CLOSE && HIWORD(wParam) == BN_CLICKED) {
            DestroyWindow(hwnd);
            return 0;
        }
        break;
    case WM_CLOSE:
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        g_hHelpWnd = nullptr;
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wParam, lParam);
}

static void ShowHelpPopup(HWND owner) {
    if (g_hHelpWnd && IsWindow(g_hHelpWnd)) {
        ShowWindow(g_hHelpWnd, SW_SHOWNORMAL);
        SetForegroundWindow(g_hHelpWnd);
        return;
    }

    static bool registered = false;
    if (!registered) {
        WNDCLASSEXW wc{};
        wc.cbSize = sizeof(wc);
        wc.lpfnWndProc = HelpWndProc;
        wc.hInstance = g_hInst;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_BTNFACE + 1);
        wc.lpszClassName = L"MIDIPlusPlusHelpPopup";
        RegisterClassExW(&wc);
        registered = true;
    }

    g_hHelpWnd = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_DLGMODALFRAME,
        L"MIDIPlusPlusHelpPopup", L"MIDI++ Custom Build - Help",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU,
        CW_USEDEFAULT, CW_USEDEFAULT, 685, 525,
        owner, nullptr, g_hInst, nullptr);
    if (g_hHelpWnd) {
        CenterPopup(g_hHelpWnd, owner);
        ShowWindow(g_hHelpWnd, SW_SHOW);
        SetForegroundWindow(g_hHelpWnd);
    }
}

static LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        // temporary fix: this shit
    case WM_NCLBUTTONDOWN:
    {
        if (g_player &&
            g_player->midiFileSelected.load(std::memory_order_acquire) &&
            !g_player->paused.load(std::memory_order_acquire) &&
            g_player->playback_started.load(std::memory_order_acquire) &&
            (g_player->buffer_index.load(std::memory_order_acquire) < g_player->note_buffer.size()) &&
            wParam == HTCAPTION)
        {
            return 0;
        }
        return DefWindowProc(hWnd, msg, wParam, lParam);
    }


    case WM_CREATE:
    {
        INITCOMMONCONTROLSEX icex = {};
        icex.dwSize = sizeof(icex);
        icex.dwICC = ICC_BAR_CLASSES;
        InitCommonControlsEx(&icex);

        // MIDI Files Group
        CreateWindowW(L"button", L"MIDI Files",
            WS_CHILD | WS_VISIBLE | BS_GROUPBOX,
            Layout::FILES_X, Layout::FILES_Y, Layout::FILES_W, Layout::FILES_H,
            hWnd, reinterpret_cast<HMENU>(1), g_hInst, nullptr);

        HWND cbSort = CreateWindowW(L"combobox", nullptr,
            WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
            Layout::FILES_X + 10, Layout::FILES_Y + 20, 130, 110,
            hWnd, reinterpret_cast<HMENU>(ID_CB_SORT), g_hInst, nullptr);
        SendMessageW(cbSort, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Name (A-Z)"));
        SendMessageW(cbSort, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Name (Z-A)"));
        SendMessageW(cbSort, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Date (Old-New)"));
        SendMessageW(cbSort, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"Date (New-Old)"));
        SendMessageW(cbSort, CB_SETCURSEL, 0, 0);
        CreateWindowW(L"button", L"Refresh",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::FILES_X + 150, Layout::FILES_Y + 20, 70, 25,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_REFRESH), g_hInst, nullptr);
        HWND searchEdit = CreateWindowExW(WS_EX_CLIENTEDGE, L"edit", L"",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL,
            Layout::FILES_X + 10, Layout::FILES_Y + 50, 210, 23,
            hWnd, reinterpret_cast<HMENU>(ID_EDIT_MIDI_SEARCH), g_hInst, nullptr);
        SetDefaultGuiFont(searchEdit);
        SendMessageW(searchEdit, EM_SETCUEBANNER, TRUE, reinterpret_cast<LPARAM>(L"Search all MIDI folders..."));
        g_lbMidi = CreateWindowW(L"listbox", nullptr,
            WS_CHILD | WS_VISIBLE | LBS_NOTIFY | WS_VSCROLL | WS_HSCROLL | WS_BORDER | LBS_NOINTEGRALHEIGHT,
            Layout::FILES_X + 10, Layout::FILES_Y + 78, 210, 282,
            hWnd, reinterpret_cast<HMENU>(ID_LB_MIDI), g_hInst, nullptr);
        SetWindowSubclass(g_lbMidi, MidiListSubclassProc, 0, 0);
        CreateWindowW(L"static", L"Recent:", WS_CHILD | WS_VISIBLE,
            Layout::FILES_X + 10, Layout::FILES_Y + 365, 48, 20, hWnd, nullptr, g_hInst, nullptr);
        HWND recentCombo = CreateWindowW(L"combobox", nullptr, WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
            Layout::FILES_X + 60, Layout::FILES_Y + 362, 160, 130,
            hWnd, reinterpret_cast<HMENU>(ID_CB_RECENT), g_hInst, nullptr);
        SetDefaultGuiFont(recentCombo);

        // Playback (Basic) Group
        CreateWindowW(L"button", L"Playback (Basic)",
            WS_CHILD | WS_VISIBLE | BS_GROUPBOX,
            Layout::PBASIC_X, Layout::PBASIC_Y, Layout::PBASIC_W, Layout::PBASIC_H,
            hWnd, reinterpret_cast<HMENU>(ID_GRP_PLAY), g_hInst, nullptr);
        int bx = Layout::PBASIC_X + 20;
        CreateWindowW(L"button", L"Load",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_LOAD), g_hInst, nullptr);
        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        CreateWindowW(L"button", L"Play/Pause",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_PLAY), g_hInst, nullptr);
        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        CreateWindowW(L"button", L"Restart",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_RESTART), g_hInst, nullptr);
        bx = Layout::PBASIC_X + 20;
        CreateWindowW(L"button", L"Skip+10",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW2_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_SKIP), g_hInst, nullptr);
        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        CreateWindowW(L"button", L"Rew-10",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW2_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_REW), g_hInst, nullptr);
        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        CreateWindowW(L"button", L"Speed++",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW2_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_SPEEDUP), g_hInst, nullptr);
        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        CreateWindowW(L"button", L"Speed--",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW2_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_SPEEDDN), g_hInst, nullptr);
        CreateWindowW(L"button", L"Midi2Key",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::PB_MIDI_QWERTY_X + 35, Layout::PB_MIDI_QWERTY_Y, 80, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_MIDI2QWERTY), g_hInst, nullptr);
        CreateWindowW(L"button", L"MidiConnect",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_MIDICONNECT), g_hInst, nullptr);
        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        HWND cbMidiDev = CreateWindowW(L"combobox", nullptr,
            WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
            Layout::PB_MIDI_QWERTY_X + 120, Layout::PB_MIDI_QWERTY_Y, 130, 200,
            hWnd, reinterpret_cast<HMENU>(ID_CB_MIDIDEV), g_hInst, nullptr);
        MIDIDeviceUI::PopulateMidiInDevices(cbMidiDev, g_selectedMidiDevice);
        HWND cbMidiCh = CreateWindowW(L"combobox", nullptr,
            WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
            Layout::PB_MIDI_QWERTY_X + 120, Layout::PB_ROW2_Y, 130, 200,
            hWnd, reinterpret_cast<HMENU>(ID_CB_MIDICH), g_hInst, nullptr);
        MIDIDeviceUI::PopulateChannelList(cbMidiCh, g_selectedMidiChannel);
        HWND seekSlider = CreateWindowExW(0, TRACKBAR_CLASSW, L"",
            WS_CHILD | WS_VISIBLE | TBS_NOTICKS,
            Layout::PBASIC_X + 15, Layout::PBASIC_Y + 96, 465, 25,
            hWnd, reinterpret_cast<HMENU>(ID_SLIDER_SEEK), g_hInst, nullptr);
        SendMessage(seekSlider, TBM_SETRANGE, TRUE, MAKELPARAM(0, 10000));
        SendMessage(seekSlider, TBM_SETPOS, TRUE, 0);
        CreateWindowW(L"static", L"0:00 / 0:00",
            WS_CHILD | WS_VISIBLE | SS_CENTER,
            Layout::PBASIC_X + 485, Layout::PBASIC_Y + 99, 105, 20,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_TIME), g_hInst, nullptr);
        CreateWindowW(L"button", L"Reload", WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::PBASIC_X + 15, Layout::PBASIC_Y + 132, 70, 26,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_RELOAD), g_hInst, nullptr);
        CreateWindowW(L"button", L"Reset Playback", WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::PBASIC_X + 90, Layout::PBASIC_Y + 132, 100, 26,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_RESET_PLAYBACK), g_hInst, nullptr);
        CreateWindowW(L"static", L"Ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
            Layout::PBASIC_X + 200, Layout::PBASIC_Y + 137, 145, 20,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_STATUS), g_hInst, nullptr);
        CreateWindowW(L"static", L"Speed: 1.00x", WS_CHILD | WS_VISIBLE | SS_CENTER,
            Layout::PBASIC_X + 350, Layout::PBASIC_Y + 137, 100, 20,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_SPEED), g_hInst, nullptr);
        CreateWindowW(L"static", L"Transpose: +0", WS_CHILD | WS_VISIBLE | SS_CENTER,
            Layout::PBASIC_X + 455, Layout::PBASIC_Y + 137, 125, 20,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_TRANSPOSE), g_hInst, nullptr);

        // Advanced Group
        CreateWindowW(L"button", L"Advanced",
            WS_CHILD | WS_VISIBLE | BS_GROUPBOX,
            Layout::PADV_X, Layout::PADV_Y, Layout::PADV_W, Layout::PADV_H,
            hWnd, reinterpret_cast<HMENU>(ID_GRP_ADV), g_hInst, nullptr);
        int advx = Layout::PADV_X + 15;
        int advy = Layout::PADV_Y + 25;
        const int advBw = 80, advBh = 28, advGap = 5;
        CreateWindowW(L"button", L"88-Key",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            advx, advy, advBw, advBh,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_88KEY), g_hInst, nullptr);
        advx += (advBw + advGap);
        CreateWindowW(L"button", L"AutoVol",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            advx, advy, advBw, advBh,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_VOLADJ), g_hInst, nullptr);
        advx += (advBw + advGap);
        CreateWindowW(L"button", L"Velocity",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            advx, advy, advBw, advBh,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_VELOCITY), g_hInst, nullptr);
        advx += (advBw + advGap);
        CreateWindowW(L"button", L"Sustain",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            advx, advy, advBw, advBh,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_SUSTAIN), g_hInst, nullptr);
        advx += (advBw + advGap);
        CreateWindowW(L"button", L"Transpose",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            advx, advy, advBw + 20, advBh,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_TRANSPOSE), g_hInst, nullptr);
        advx += (advBw + 20 + advGap);
        CreateWindowW(L"button", L"OutRange",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            advx, advy, advBw + 15, advBh,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_TRANSPOSEOUT), g_hInst, nullptr);
        // Humanizer and Help are configuration popups. Keep them in the
        // Advanced group so timing can be tuned without editing JSON by hand.
        CreateWindowW(L"button", L"Humanizer",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::PADV_X + 15, Layout::PADV_Y + 62, 95, 27,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_HUMANIZER), g_hInst, nullptr);
        CreateWindowW(L"button", L"Help",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::PADV_X + 115, Layout::PADV_Y + 62, 60, 27,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_HELP), g_hInst, nullptr);

        {
            HWND hStaticSustainLbl = CreateWindowW(L"static", L"Sustain:",
                WS_CHILD | WS_VISIBLE,
                Layout::PADV_X + 185, Layout::PADV_Y + 68,
                55, 20,
                hWnd, reinterpret_cast<HMENU>(ID_STATIC_SUSTAIN_LABEL), g_hInst, nullptr);
            HWND hSustainSlider = CreateWindowExW(0, TRACKBAR_CLASSW, L"",
                WS_CHILD | WS_VISIBLE | TBS_AUTOTICKS,
                Layout::PADV_X + 240, Layout::PADV_Y + 61,
                105, 30,
                hWnd, reinterpret_cast<HMENU>(ID_SLIDER_SUSTAIN_CUTOFF), g_hInst, nullptr);
            SendMessage(hSustainSlider, TBM_SETRANGE, TRUE, MAKELPARAM(0, 127));
            SendMessage(hSustainSlider, TBM_SETTICFREQ, 16, 0);
            SendMessage(hSustainSlider, TBM_SETPOS, TRUE, g_sustainCutoff);
            g_hSustainCutoffValueBox = CreateWindowExW(WS_EX_CLIENTEDGE,
                L"edit", L"64",
                WS_CHILD | WS_VISIBLE | ES_READONLY | ES_CENTER,
                Layout::PADV_X + 350, Layout::PADV_Y + 65,
                35, 20,
                hWnd, nullptr, g_hInst, nullptr);
        }
        HWND hStaticVelLbl = CreateWindowW(L"static", L"Vel:",
            WS_CHILD | WS_VISIBLE,
            Layout::PADV_X + 395, Layout::PADV_Y + 68, 30, 20,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_SUSTAIN_LABEL), g_hInst, nullptr);
        CreateWindowW(L"combobox", nullptr,
            WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
            Layout::PADV_X + 425, Layout::PADV_Y + 62, 155, 200,
            hWnd, reinterpret_cast<HMENU>(ID_CB_VELOCITY_CURVE), g_hInst, nullptr);
        RefreshVelocityCurveCombo(hWnd);

        CreateWindowW(L"button", L"Playability",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::PADV_X + 15, Layout::PADV_Y + 96, 95, 27,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_PLAYABILITY), g_hInst, nullptr);
        CreateWindowW(L"static", L"Optional: max 5 notes/hand, 10 total per simultaneous attack",
            WS_CHILD | WS_VISIBLE,
            Layout::PADV_X + 120, Layout::PADV_Y + 101, 430, 20,
            hWnd, nullptr, g_hInst, nullptr);

        // Config Group
        CreateWindowW(L"button", L"Config",
            WS_CHILD | WS_VISIBLE | BS_GROUPBOX,
            Layout::CFG_X, Layout::CFG_Y, Layout::CFG_W, Layout::CFG_H,
            hWnd, reinterpret_cast<HMENU>(ID_GRP_CONFIG), g_hInst, nullptr);

        HWND hChkAlwaysOnTop = CreateWindowW(L"button", L"Always On Top",
            WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX,
            Layout::CFG_X + 10, Layout::CFG_Y + 25, 120, 20,
            hWnd, reinterpret_cast<HMENU>(ID_CHK_TOP), g_hInst, nullptr);
        bool alwaysOnTop = midi::Config::getInstance().ui.alwaysOnTop;
        SendMessage(hChkAlwaysOnTop, BM_SETCHECK, alwaysOnTop ? BST_CHECKED : BST_UNCHECKED, 0);
        SetAlwaysOnTop(hWnd, alwaysOnTop);

        HWND hChkRandomSong = CreateWindowW(L"button", L"Shuffle Play",
            WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX,
            Layout::CFG_X + 140, Layout::CFG_Y + 25, 115, 20,
            hWnd, reinterpret_cast<HMENU>(ID_CHK_RANDOM_SONG), g_hInst, nullptr);
        SendMessage(hChkRandomSong, BM_SETCHECK, g_randomSongEnabled ? BST_CHECKED : BST_UNCHECKED, 0);

        HWND hStaticOpacity = CreateWindowW(L"static", L"Opacity:",
            WS_CHILD | WS_VISIBLE,
            Layout::CFG_X + 255, Layout::CFG_Y + 25, 60, 20,
            hWnd, nullptr, g_hInst, nullptr);

        HWND hOpacitySlider = CreateWindowExW(0, TRACKBAR_CLASSW, L"",
            WS_CHILD | WS_VISIBLE | TBS_AUTOTICKS,
            Layout::CFG_X + 310, Layout::CFG_Y + 20, 120, 30,
            hWnd, reinterpret_cast<HMENU>(ID_SLIDER_OPACITY), g_hInst, nullptr);
        SendMessage(hOpacitySlider, TBM_SETRANGE, TRUE, MAKELPARAM(100, 255));
        SendMessage(hOpacitySlider, TBM_SETTICFREQ, 15, 0);
        SendMessage(hOpacitySlider, TBM_SETPOS, TRUE, 255);

        g_hOpacityIndicatorBox = CreateWindowExW(WS_EX_CLIENTEDGE,
            L"edit",
            L"255",
            WS_CHILD | WS_VISIBLE | ES_READONLY | ES_CENTER,
            Layout::CFG_X + 445, Layout::CFG_Y + 25, 40, 20,
            hWnd, nullptr, g_hInst, nullptr);
        HWND hPrevSongBtn = CreateWindowW(L"button", L"Prev",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::CFG_X + 495, Layout::CFG_Y + 25, 40, 20,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_PREV_SONG), g_hInst, nullptr);
        HWND hNextSongBtn = CreateWindowW(L"button", L"Next",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::CFG_X + 495 + 45, Layout::CFG_Y + 25, 40, 20,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_NEXT_SONG), g_hInst, nullptr);

        // Details Group
        CreateWindowW(L"button", L"Details",
            WS_CHILD | WS_VISIBLE | BS_GROUPBOX,
            Layout::DET_X, Layout::DET_Y, Layout::DET_W, Layout::DET_H,
            hWnd, reinterpret_cast<HMENU>(ID_GRP_DETAILS), g_hInst, nullptr);
        g_editDetails = CreateWindowW(L"edit", L"",
            WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL | WS_BORDER,
            Layout::DET_X + 10, Layout::DET_Y + 20, Layout::DET_W - 20, Layout::DET_H - 30,
            hWnd, reinterpret_cast<HMENU>(ID_EDIT_DETAILS), g_hInst, nullptr);

        // Tracks Group
        g_trackControl.Create(hWnd, Layout::TRK_X, Layout::TRK_Y, Layout::TRK_W, Layout::TRK_H - 2);

        // Log Group
        CreateWindowW(L"button", L"Log",
            WS_CHILD | WS_VISIBLE | BS_GROUPBOX,
            Layout::LOG_X, Layout::LOG_Y, Layout::LOG_W, Layout::LOG_H,
            hWnd, reinterpret_cast<HMENU>(ID_GRP_LOG), g_hInst, nullptr);
        HWND editLog = CreateWindowW(L"edit", L"",
            WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL | WS_BORDER,
            Layout::LOG_X + 10, Layout::LOG_Y + 20, Layout::LOG_W - 100, Layout::LOG_H - 30,
            hWnd, reinterpret_cast<HMENU>(ID_EDIT_LOG), g_hInst, nullptr);
        CreateWindowW(L"button", L"Clear Log",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::LOG_X + Layout::LOG_W - 80, Layout::LOG_Y + 25, 70, 25,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_CLEARLOG), g_hInst, nullptr);
        CreateWindowW(L"button", L"Refresh MIDI",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::LOG_X + Layout::LOG_W - 80, Layout::LOG_Y + 55, 70, 25,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_REFRESH_MIDI), g_hInst, nullptr);
        CreateWindowW(L"button", L"Edit V-Curve",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::LOG_X + Layout::LOG_W - 80, Layout::LOG_Y + 85, 70, 25,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_VLCURVE), g_hInst, nullptr);
        CreateWindowW(L"button", L"Ref V-List",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::LOG_X + Layout::LOG_W - 80, Layout::LOG_Y + 115, 70, 25,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_REFRESH_VCURVE), g_hInst, nullptr);

        // Initialize Toggle States
        std::vector<int> toggles = { ID_BTN_88KEY, ID_BTN_VOLADJ, ID_BTN_VELOCITY, ID_BTN_SUSTAIN, ID_BTN_TRANSPOSEOUT, ID_BTN_PLAYABILITY, ID_BTN_MIDI2QWERTY };
        for (int t : toggles)
            g_toggleStates[t] = false;
        if (g_player && g_player->eightyEightKeyModeActive)
            g_toggleStates[ID_BTN_88KEY] = true;
        g_toggleStates[ID_BTN_PLAYABILITY] = midi::Config::getInstance().playability.ENABLED;

        // Initial Setup
        DragAcceptFiles(hWnd, TRUE);
        const auto& uiSettings = midi::Config::getInstance().ui;
        std::filesystem::path savedDir(Utf8ToWide(uiSettings.lastMidiDirectory));
        if (savedDir.empty()) savedDir = midi::Config::resolvePath("midi");
        if (!savedDir.is_absolute()) savedDir = midi::Config::resolvePath(savedDir);
        g_currentMidiDir = (std::filesystem::exists(savedDir) && std::filesystem::is_directory(savedDir)) ? savedDir : midi::Config::resolvePath("midi");
        int startupOpacity = std::clamp(uiSettings.opacity, 100, 255);
        SendMessage(GetDlgItem(hWnd, ID_SLIDER_OPACITY), TBM_SETPOS, TRUE, startupOpacity);
        wchar_t opacityText[16]; swprintf_s(opacityText, L"%d", startupOpacity); SetWindowTextW(g_hOpacityIndicatorBox, opacityText);
        SetLayeredWindowAttributes(hWnd, 0, static_cast<BYTE>(startupOpacity), LWA_ALPHA);
        ScanMidiFolder(); SortMidiItems(); PopulateMidiList(); RefreshRecentMidiCombo(hWnd);
        AddToolTip(hWnd, ID_BTN_RELOAD, L"Rebuild the currently loaded MIDI without browsing to it again.");
        AddToolTip(hWnd, ID_BTN_RESET_PLAYBACK, L"Return to 0:00, speed 1.00x and transpose +0, and clear mute/solo. Humanizer, Velocity and Sustain mode are not changed.");
        AddToolTip(hWnd, ID_BTN_HUMANIZER, L"Human timing presets and exact millisecond controls. Changes rebuild the loaded MIDI automatically.");
        AddToolTip(hWnd, ID_BTN_88KEY, L"Use the full configured virtual-piano keyboard range.");
        AddToolTip(hWnd, ID_BTN_VOLADJ, L"Automatically calibrate and adjust Roblox volume/velocity keys.");
        AddToolTip(hWnd, ID_BTN_VELOCITY, L"Use MIDI note velocity when choosing virtual-piano velocity keys.");
        AddToolTip(hWnd, ID_BTN_TRANSPOSEOUT, L"Transpose notes that would otherwise fall outside the selected keyboard range.");
        AddToolTip(hWnd, ID_BTN_PLAYABILITY, L"Optional virtual-piano optimizer. Limits simultaneous physical attacks to 5 notes per hand and 10 total while preserving bass, top voice, velocity, and likely melody importance.");
        AddToolTip(hWnd, ID_BTN_MIDI2QWERTY, L"Use a physical MIDI input device to send QWERTY piano keys.");
        AddToolTip(hWnd, ID_BTN_MIDICONNECT, L"Send loaded MIDI (and optional live MIDI input) directly through the Visual Pianos MidiConnect protocol.");
        AddToolTip(hWnd, ID_SLIDER_SEEK, L"Drag to seek directly through the loaded song.");
        SetTimer(hWnd, IDT_TIMELEFT_TIMER, 200, nullptr);
        g_guiReady.store(true);
        PostMessage(hWnd, WM_UPDATE_LOG, 0, 0);
        UpdateWindowFocusability();

        return 0;
    }

    case WM_ERASEBKGND:
        return 1;

    case WM_PAINT:
    {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hWnd, &ps);
        EndPaint(hWnd, &ps);
        return 0;
    }

    case WM_DRAWITEM:
    {
        const DRAWITEMSTRUCT* dis = reinterpret_cast<const DRAWITEMSTRUCT*>(lParam);
        if (dis->CtlType == ODT_BUTTON) {
            DrawFancyButton(dis);
            return TRUE;
        }
        break;
    }

    case WM_HSCROLL:
    {
        HWND hwCtrl = reinterpret_cast<HWND>(lParam);
        int idCtrl = GetDlgCtrlID(hwCtrl);
        if (idCtrl == ID_SLIDER_SEEK) {
            const int code = LOWORD(wParam);
            if (code == TB_THUMBTRACK) g_seekDragging = true;
            if (code == TB_THUMBPOSITION || code == TB_ENDTRACK || code == TB_LINEUP || code == TB_LINEDOWN || code == TB_PAGEUP || code == TB_PAGEDOWN) {
                g_seekDragging = false;
                if (g_player && g_player->midiFileSelected.load(std::memory_order_acquire) && g_totalSongSeconds > 0.0) {
                    const int pos = static_cast<int>(SendMessage(hwCtrl, TBM_GETPOS, 0, 0));
                    const double targetSeconds = g_totalSongSeconds * (static_cast<double>(pos) / 10000.0);
                    g_player->seek_to(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::duration<double>(targetSeconds)));
                }
            }
        }
        else if (idCtrl == ID_SLIDER_SUSTAIN_CUTOFF) {
            switch (LOWORD(wParam)) {
            case TB_THUMBPOSITION:
            case TB_THUMBTRACK:
            case TB_LINEUP:
            case TB_LINEDOWN:
            case TB_PAGEUP:
            case TB_PAGEDOWN:
            case TB_ENDTRACK:
            {
                g_sustainCutoff = static_cast<int>(SendMessage(hwCtrl, TBM_GETPOS, 0, 0));
                wchar_t buf[16];
                swprintf_s(buf, L"%d", g_sustainCutoff);
                SetWindowTextW(g_hSustainCutoffValueBox, buf);
                break;
            }
            }
        }
        else if (idCtrl == ID_SLIDER_OPACITY) {
            int opacity = static_cast<int>(SendMessage(hwCtrl, TBM_GETPOS, 0, 0));
            if (opacity < 100) opacity = 100;
            SetLayeredWindowAttributes(g_hMainWnd, 0, static_cast<BYTE>(opacity), LWA_ALPHA);
            wchar_t opacityText[16];
            swprintf_s(opacityText, L"%d", opacity);
            SetWindowTextW(g_hOpacityIndicatorBox, opacityText);
            auto& cfg = midi::Config::getInstance(); cfg.ui.opacity = opacity;
            if (LOWORD(wParam) == TB_ENDTRACK || LOWORD(wParam) == TB_THUMBPOSITION) { try { cfg.saveToFile("config.json"); } catch (...) {} }
        }
        return 0;
    }

    case WM_UPDATE_LOG:
    {
        std::string data;
        {
            std::lock_guard<std::mutex> lk(g_logMutex);
            data = g_logBuffer;
        }
        std::string replaced;
        replaced.reserve(data.size() + 50);
        for (char c : data) {
            if (c == '\n')
                replaced.append("\r\n");
            else
                replaced.push_back(c);
        }
        int wideLen = MultiByteToWideChar(CP_UTF8, 0, replaced.c_str(), -1, nullptr, 0);
        if (wideLen > 0) {
            std::wstring wreplaced(wideLen, L'\0');
            MultiByteToWideChar(CP_UTF8, 0, replaced.c_str(), -1, &wreplaced[0], wideLen);
            if (!wreplaced.empty() && wreplaced.back() == L'\0')
                wreplaced.pop_back();
            HWND editLog = GetDlgItem(hWnd, ID_EDIT_LOG);
            SetWindowTextW(editLog, wreplaced.c_str());
            SendMessage(editLog, EM_LINESCROLL, 0, 999999);
        }
        return 0;
    }

    case WM_DROPFILES:
    {
        HDROP drop = reinterpret_cast<HDROP>(wParam);
        const UINT count = DragQueryFileW(drop, 0xFFFFFFFF, nullptr, 0);
        for (UINT i = 0; i < count; ++i) {
            wchar_t pathBuffer[32768]{};
            if (!DragQueryFileW(drop, i, pathBuffer, static_cast<UINT>(std::size(pathBuffer)))) continue;
            std::filesystem::path p(pathBuffer); std::wstring ext = p.extension().wstring(); std::transform(ext.begin(), ext.end(), ext.begin(), ::towlower);
            if (ext == L".mid" || ext == L".midi") { LoadMidiFilePath(hWnd, p.wstring(), false); break; }
        }
        DragFinish(drop); return 0;
    }

    case WM_COMMAND:
    {
        int id = LOWORD(wParam);
        int code = HIWORD(wParam);
        switch (id) {
        case ID_EDIT_MIDI_SEARCH:
            if (code == EN_CHANGE) {
                ScanMidiSearchResults(GetMidiBrowserSearchText());
                SortMidiItems();
                PopulateMidiList();
            }
            break;

        case ID_CB_RECENT:
            if (code == CBN_SELCHANGE) {
                HWND combo = GetDlgItem(hWnd, ID_CB_RECENT); int sel = static_cast<int>(SendMessage(combo, CB_GETCURSEL, 0, 0));
                const auto& recent = midi::Config::getInstance().ui.recentMidiFiles;
                if (sel >= 0 && sel < static_cast<int>(recent.size())) { std::wstring path = Utf8ToWide(recent[static_cast<size_t>(sel)]); if (std::filesystem::exists(path)) LoadMidiFilePath(hWnd, path, false); else MessageBoxW(hWnd, L"That recent MIDI file no longer exists.", L"Recent MIDI", MB_OK | MB_ICONINFORMATION); }
            }
            break;

        case ID_CB_SORT:
            if (code == CBN_SELCHANGE) {
                HWND cb = GetDlgItem(hWnd, ID_CB_SORT);
                int sel = static_cast<int>(SendMessage(cb, CB_GETCURSEL, 0, 0));
                SortMidiItems();
                PopulateMidiList();
            }
            break;

        case ID_BTN_REFRESH:
            if (code == BN_CLICKED) {
                ScanMidiSearchResults(GetMidiBrowserSearchText());
                SortMidiItems();
                PopulateMidiList();
                std::wcout << L"[Refresh] MIDI browser refreshed.\n";
            }
            break;

        case ID_BTN_HUMANIZER:
            if (code == BN_CLICKED) ShowHumanizerPopup(hWnd);
            break;

        case ID_BTN_RELOAD:
            if (code == BN_CLICKED) { if (!ReloadCurrentMidi(hWnd)) MessageBoxW(hWnd, L"Load a MIDI file first.", L"Reload MIDI", MB_OK | MB_ICONINFORMATION); }
            break;

        case ID_BTN_RESET_PLAYBACK:
            if (code == BN_CLICKED && g_player) {
                g_player->reset_playback_basics();
                UpdateTrackInfo();
                UpdateMidiDetails();
                SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_STATUS), L"Playback reset");
            }
            break;

        case ID_BTN_PLAYABILITY:
            if (code == BN_CLICKED) {
                auto& cfg = midi::Config::getInstance();
                cfg.playability.ENABLED = !cfg.playability.ENABLED;
                g_toggleStates[ID_BTN_PLAYABILITY] = cfg.playability.ENABLED;
                InvalidateRect(GetDlgItem(hWnd, ID_BTN_PLAYABILITY), nullptr, TRUE);
                try {
                    cfg.saveToFile("config.json");
                    std::cout << "[Playability] Optimizer " << (cfg.playability.ENABLED ? "enabled" : "disabled") << ".\n";
                    if (g_player && g_player->midiFileSelected.load(std::memory_order_acquire))
                        ReloadCurrentMidi(hWnd);
                    UpdateMidiDetails();
                }
                catch (const std::exception& ex) {
                    MessageBoxW(hWnd, Utf8ToWide(ex.what()).c_str(), L"Playability Optimizer", MB_OK | MB_ICONERROR);
                }
            }
            break;

        case ID_BTN_HELP:
            if (code == BN_CLICKED)
                ShowHelpPopup(hWnd);
            break;

        case ID_CHK_TOP:
            if (code == BN_CLICKED) {
                HWND hChk = reinterpret_cast<HWND>(lParam);
                bool top = (SendMessage(hChk, BM_GETCHECK, 0, 0) == BST_CHECKED);
                SetAlwaysOnTop(hWnd, top);
                midi::Config::getInstance().ui.alwaysOnTop = top;
                try {
                    midi::Config::getInstance().saveToFile("config.json");
                    std::cout << "[Config] Saved Always on Top state: " << (top ? "ENABLED" : "DISABLED") << "\n";
                }
                catch (const std::exception& ex) {
                    std::cerr << "[Config] Failed to save config: " << ex.what() << "\n";
                }
            }
            break;

        case ID_CHK_RANDOM_SONG:
            if (code == BN_CLICKED) {
                HWND hChk = reinterpret_cast<HWND>(lParam);
                LRESULT state = SendMessage(hChk, BM_GETCHECK, 0, 0);
                if (state == BST_CHECKED) {
                    if ((g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())) {
                        MessageBoxA(hWnd, "Random Song cannot be enabled while MIDI2Key or MIDIConnect is active.",
                            "Conflict", MB_OK | MB_ICONWARNING);
                        SendMessage(hChk, BM_SETCHECK, BST_UNCHECKED, 0);
                        g_randomSongEnabled = false;
                    }
                    else {
                        g_randomSongEnabled = true;
                    }
                }
                else {
                    g_randomSongEnabled = false;
                }
            }
            break;

        case ID_BTN_CLEARLOG:
            if (code == BN_CLICKED) {
                HWND editLog = GetDlgItem(hWnd, ID_EDIT_LOG);
                int ret = MessageBoxA(hWnd, "Are you sure you want to clear the log?\nThis cannot be undone.",
                    "Confirm Clear", MB_YESNO | MB_ICONQUESTION);
                if (ret == IDYES) {
                    ClearLog(editLog);
                    std::cout << "[LOG] Cleared.\n";
                }
            }
            break;

        case ID_BTN_REFRESH_VCURVE:
            if (code == BN_CLICKED) {
                RefreshVelocityCurveCombo(hWnd);
                std::cout << "[VELOCITY] Velocity curves refreshed.\n";
            }
            break;

        case ID_BTN_REFRESH_MIDI:
            if (code == BN_CLICKED) {
                std::cout << "[MIDI Devices] Refreshing device list...\n";
                if (g_midi2key && g_midi2key->IsActive())
                    g_midi2key->CloseDevice();
                int previousDevice = g_selectedMidiDevice;
                HWND cbMidiDev = GetDlgItem(hWnd, ID_CB_MIDIDEV);
                MIDIDeviceUI::PopulateMidiInDevices(cbMidiDev, g_selectedMidiDevice);
                if (g_midi2key && g_midi2key->IsActive() && g_selectedMidiDevice >= 0) {
                    if (MIDIDeviceUI::TestDeviceAccess(g_selectedMidiDevice))
                        g_midi2key->OpenDevice(g_selectedMidiDevice);
                    else
                        std::cout << "[MIDI Devices] Cannot reopen device - no longer accessible\n";
                }
            }
            break;

        case ID_BTN_LOAD:
            if (code == BN_CLICKED) {
                const std::wstring path = GetSelectedMidiFullPath();
                if (path.empty()) { std::cout << "[Load] No MIDI file selected.\n"; MessageBoxW(hWnd, L"Select a MIDI file first.", L"Load MIDI", MB_OK | MB_ICONINFORMATION); }
                else LoadMidiFilePath(hWnd, path, false);
            }
            break;

        case ID_LB_MIDI:
            if (code == LBN_DBLCLK) {
                int sel = static_cast<int>(SendMessage(g_lbMidi, LB_GETCURSEL, 0, 0));
                if (sel != LB_ERR && sel >= 0 && sel < static_cast<int>(g_midiItems.size())) {
                    const MidiItem& item = g_midiItems[sel];
                    if (item.isFolder) {
                        if (item.name == L"..")
                            g_currentMidiDir = std::filesystem::path(g_currentMidiDir).parent_path();
                        else
                            g_currentMidiDir = item.fullPath;
                        auto& cfg = midi::Config::getInstance(); cfg.ui.lastMidiDirectory = WideToUtf8(g_currentMidiDir.wstring()); try { cfg.saveToFile("config.json"); } catch (...) {}
                        ScanMidiFolder(); SortMidiItems(); PopulateMidiList();
                    }
                    else {
                        SendMessage(hWnd, WM_COMMAND, MAKEWPARAM(ID_BTN_LOAD, BN_CLICKED),
                            reinterpret_cast<LPARAM>(GetDlgItem(hWnd, ID_BTN_LOAD)));
                    }
                }
            }
            break;

        case WM_CLOSE:
            DestroyWindow(hWnd);
            break;

        case ID_BTN_VLCURVE:
            if (code == BN_CLICKED) {
                auto editor = new VelocityCurveEditor();
                editor->Create(hWnd);
            }
            break;

        case ID_BTN_PLAY:
            if (code == BN_CLICKED) {
                if ((g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Auto controls are disabled while MIDI input is active.", "Info", MB_OK | MB_ICONINFORMATION);
                    break;
                }
                if (!g_player->midiFileSelected.load(std::memory_order_acquire)) {
                    MessageBoxA(hWnd, "Please load a MIDI file first.", "Error", MB_OK | MB_ICONERROR);
                    break;
                }
                FocusRobloxWindow();
                g_player->toggle_play_pause();
            }
            break;

        case ID_BTN_MIDICONNECT:
            if (code == BN_CLICKED) {
                if (g_toggleStates[ID_BTN_MIDI2QWERTY]) {
                    MessageBoxA(hWnd, "Please disable MIDI->QWERTY mode first.", "Conflict", MB_OK | MB_ICONWARNING);
                    break;
                }
                g_toggleStates[ID_BTN_MIDICONNECT] = !g_toggleStates[ID_BTN_MIDICONNECT];
                bool newState = g_toggleStates[ID_BTN_MIDICONNECT];
                InvalidateRect(GetDlgItem(hWnd, ID_BTN_MIDICONNECT), nullptr, TRUE);
                if (newState) {
                    if (!g_midiConnect)
                        g_midiConnect = std::make_unique<MIDIConnect>();
                    g_midiConnect->SetActive(true);
                    g_midiConnect->OpenDevice(g_selectedMidiDevice);
                    std::cout << "[MidiConnect] ENABLED\n";
                    FocusRobloxWindow();
                    g_midiConnect->ReleaseAllNumpadKeys();
                }
                else {
                    if (g_midiConnect) {
                        g_midiConnect->SetActive(false);
                        g_midiConnect->CloseDevice();
                    }
                    std::cout << "[MidiConnect] DISABLED\n";
                }
                UpdateWindowFocusability();
            }
            break;

        case ID_BTN_RESTART:
            if (code == BN_CLICKED) {
                if ((g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Auto controls are disabled while MIDI input is active.", "Info", MB_OK | MB_ICONINFORMATION);
                    break;
                }
                if (!g_player->midiFileSelected.load(std::memory_order_acquire)) {
                    MessageBoxA(hWnd, "Please load a MIDI file first.", "Error", MB_OK | MB_ICONERROR);
                    break;
                }
                FocusRobloxWindow();
                g_player->restart_song();
            }
            break;

        case ID_BTN_SKIP:
            if (code == BN_CLICKED) {
                if ((g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Auto controls are disabled while MIDI input is active.", "Info", MB_OK | MB_ICONINFORMATION);
                    break;
                }
                if (!g_player->midiFileSelected.load(std::memory_order_acquire)) {
                    MessageBoxA(hWnd, "Please load a MIDI file first.", "Error", MB_OK | MB_ICONERROR);
                    break;
                }
                using namespace std::chrono_literals;
                g_player->skip(10s);
            }
            break;

        case ID_BTN_REW:
            if (code == BN_CLICKED) {
                if ((g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Auto controls are disabled while MIDI input is active.", "Info", MB_OK | MB_ICONINFORMATION);
                    break;
                }
                if (!g_player->midiFileSelected.load(std::memory_order_acquire)) {
                    MessageBoxA(hWnd, "Please load a MIDI file first.", "Error", MB_OK | MB_ICONERROR);
                    break;
                }
                using namespace std::chrono_literals;
                g_player->rewind(10s);
            }
            break;

        case ID_BTN_SPEEDUP:
            if (code == BN_CLICKED) {
                if ((g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Auto controls are disabled while MIDI input is active.", "Info", MB_OK | MB_ICONINFORMATION);
                    break;
                }
                if (!g_player->midiFileSelected.load(std::memory_order_acquire)) {
                    MessageBoxA(hWnd, "Please load a MIDI file first.", "Error", MB_OK | MB_ICONERROR);
                    break;
                }
                g_player->speed_up();
            }
            break;

        case ID_BTN_SPEEDDN:
            if (code == BN_CLICKED) {
                if ((g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Auto controls are disabled while MIDI input is active.", "Info", MB_OK | MB_ICONINFORMATION);
                    break;
                }
                if (!g_player->midiFileSelected.load(std::memory_order_acquire)) {
                    MessageBoxA(hWnd, "Please load a MIDI file first.", "Error", MB_OK | MB_ICONERROR);
                    break;
                }
                g_player->slow_down();
            }
            break;

        case ID_BTN_MIDI2QWERTY:
            if (code == BN_CLICKED) {
                if (g_toggleStates[ID_BTN_MIDICONNECT]) {
                    MessageBoxA(hWnd, "Please disable MidiConnect mode first.", "Conflict", MB_OK | MB_ICONWARNING);
                    break;
                }
                g_toggleStates[ID_BTN_MIDI2QWERTY] = !g_toggleStates[ID_BTN_MIDI2QWERTY];
                bool newState = g_toggleStates[ID_BTN_MIDI2QWERTY];
                InvalidateRect(GetDlgItem(hWnd, ID_BTN_MIDI2QWERTY), nullptr, TRUE);
                if (newState) {
                    if (!g_midi2key)
                        g_midi2key = std::make_unique<MIDI2Key>(g_player);
                    g_midi2key->SetActive(true);
                    g_midi2key->OpenDevice(g_selectedMidiDevice);
                    std::cout << "[MIDI->QWERTY] ENABLED\n";
                    std::cout << "[WARNING] DO NOT use MIDI2Key with spam / black MIDIs or similar\n";
                    FocusRobloxWindow();
                    g_player->release_all_keys();
                }
                else {
                    if (g_midi2key) {
                        g_midi2key->SetActive(false);
                        g_midi2key->CloseDevice();
                    }
                    std::cout << "[MIDI->QWERTY] DISABLED\n";
                }
                UpdateWindowFocusability();
            }
            break;

        case ID_CB_VELOCITY_CURVE:
            if (code == CBN_SELCHANGE) {
                if (!g_player) break;
                HWND cb = GetDlgItem(hWnd, ID_CB_VELOCITY_CURVE);
                int sel = static_cast<int>(SendMessage(cb, CB_GETCURSEL, 0, 0));
                g_player->setVelocityCurveIndex(sel);
                auto& config = midi::Config::getInstance();
                if (sel < 5)
                    config.playback.velocityCurve = static_cast<midi::VelocityCurveType>(sel);
                else
                    config.playback.velocityCurve = midi::VelocityCurveType::Custom;
                std::cout << "[VELOCITY] Changed curve to: "
                    << (sel < 5 ? g_player->getVelocityCurveName(config.playback.velocityCurve)
                        : config.playback.customVelocityCurves[sel - 5].name) << "\n";

                if (g_midiConnect && g_midiConnect->IsActive()) {
                    g_midiConnect->CloseDevice();
                    g_midiConnect->OpenDevice(g_selectedMidiDevice);
                }
                if (g_midi2key && g_midi2key->IsActive()) {
                    g_midi2key->CloseDevice();
                    g_midi2key->OpenDevice(g_selectedMidiDevice);
                }
            }
            break;

        case ID_CB_MIDIDEV:
            if (code == CBN_SELCHANGE) {
                HWND cb = GetDlgItem(hWnd, ID_CB_MIDIDEV);
                int sel = static_cast<int>(SendMessage(cb, CB_GETCURSEL, 0, 0));
                g_selectedMidiDevice = sel;
                if (g_midi2key && g_midi2key->IsActive()) {
                    g_midi2key->CloseDevice();
                    g_midi2key->OpenDevice(sel);
                }
                if (g_midiConnect && g_midiConnect->IsActive()) {
                    g_midiConnect->CloseDevice();
                    g_midiConnect->OpenDevice(sel);
                }
            }
            break;

        case ID_CB_MIDICH:
            if (code == CBN_SELCHANGE) {
                HWND cb = GetDlgItem(hWnd, ID_CB_MIDICH);
                int sel = static_cast<int>(SendMessage(cb, CB_GETCURSEL, 0, 0));
                g_selectedMidiChannel = (sel <= 0 ? -1 : sel - 1);
            }
            break;

        case ID_BTN_PREV_SONG:
            if (code == BN_CLICKED) {
                int sel = static_cast<int>(SendMessage(g_lbMidi, LB_GETCURSEL, 0, 0));
                int count = static_cast<int>(SendMessage(g_lbMidi, LB_GETCOUNT, 0, 0));
                int newSel = sel;
                for (int i = sel - 1; i >= 0; i--) {
                    if (!g_midiItems[i].isFolder) {
                        newSel = i;
                        break;
                    }
                }
                if (newSel == sel) {
                    for (int i = count - 1; i >= 0; i--) {
                        if (!g_midiItems[i].isFolder) {
                            newSel = i;
                            break;
                        }
                    }
                }
                SendMessage(g_lbMidi, LB_SETCURSEL, newSel, 0);
                PostMessage(g_hMainWnd, WM_COMMAND, MAKEWPARAM(ID_BTN_LOAD, BN_CLICKED),
                    reinterpret_cast<LPARAM>(GetDlgItem(g_hMainWnd, ID_BTN_LOAD)));
                PostMessage(g_hMainWnd, WM_COMMAND, MAKEWPARAM(ID_BTN_PLAY, BN_CLICKED),
                    reinterpret_cast<LPARAM>(GetDlgItem(g_hMainWnd, ID_BTN_PLAY)));
            }
            break;

        case ID_BTN_NEXT_SONG:
            if (code == BN_CLICKED) {
                int sel = static_cast<int>(SendMessage(g_lbMidi, LB_GETCURSEL, 0, 0));
                int count = static_cast<int>(SendMessage(g_lbMidi, LB_GETCOUNT, 0, 0));
                int newSel = sel;
                for (int i = sel + 1; i < count; i++) {
                    if (!g_midiItems[i].isFolder) {
                        newSel = i;
                        break;
                    }
                }
                if (newSel == sel) {
                    for (int i = 0; i < count; i++) {
                        if (!g_midiItems[i].isFolder) {
                            newSel = i;
                            break;
                        }
                    }
                }
                SendMessage(g_lbMidi, LB_SETCURSEL, newSel, 0);
                PostMessage(g_hMainWnd, WM_COMMAND, MAKEWPARAM(ID_BTN_LOAD, BN_CLICKED),
                    reinterpret_cast<LPARAM>(GetDlgItem(g_hMainWnd, ID_BTN_LOAD)));
                PostMessage(g_hMainWnd, WM_COMMAND, MAKEWPARAM(ID_BTN_PLAY, BN_CLICKED),
                    reinterpret_cast<LPARAM>(GetDlgItem(g_hMainWnd, ID_BTN_PLAY)));
            }
            break;

        default:
            if (IsToggleButtonID(id) && code == BN_CLICKED && id != ID_BTN_MIDI2QWERTY) {
                g_toggleStates[id] = !g_toggleStates[id];
                InvalidateRect(GetDlgItem(hWnd, id), nullptr, TRUE);
                if (!g_player->midiFileSelected.load(std::memory_order_acquire) &&
                    !(g_midi2key && g_midi2key->IsActive()) &&
                    !(g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Load a MIDI file first or enable MIDI->QWERTY to use advanced features.",
                        "Warning", MB_OK | MB_ICONWARNING);
                    g_toggleStates[id] = !g_toggleStates[id];
                    InvalidateRect(GetDlgItem(hWnd, id), nullptr, TRUE);
                    break;
                }
                switch (id) {
                case ID_BTN_88KEY:
                    g_player->toggle_88_key_mode();
                    break;
                case ID_BTN_VOLADJ:
                {
                    bool newState = g_toggleStates[ID_BTN_VOLADJ];
                    g_player->toggle_volume_adjustment();
                    if (newState) {
                        FocusRobloxWindow();
                        g_player->calibrate_volume();
                    }
                    break;
                }
                case ID_BTN_VELOCITY:
                    g_player->toggle_velocity_keypress();
                    break;
                case ID_BTN_SUSTAIN:
                    g_player->toggleSustainMode();
                    break;
                case ID_BTN_TRANSPOSEOUT:
                    g_player->toggle_out_of_range_transpose();
                    break;
                }
            }
            else if (id == ID_BTN_TRANSPOSE && code == BN_CLICKED) {
                if (!g_player->midiFileSelected.load(std::memory_order_acquire) &&
                    !(g_midi2key && g_midi2key->IsActive()) &&
                    !(g_midiConnect && g_midiConnect->IsActive())) {
                    MessageBoxA(hWnd, "Load a MIDI file first or enable MIDI->QWERTY to use this feature.",
                        "Error", MB_OK | MB_ICONERROR);
                    break;
                }
                if (!g_player->midiFileSelected.load(std::memory_order_acquire)) {
                    MessageBoxA(hWnd, "No loaded MIDI file to analyze for transpose suggestions.\n"
                        "But if you only need the function for direct key press in 'midi2key' mode, ignore this message.",
                        "Info", MB_OK | MB_ICONINFORMATION);
                }
                int best = g_player->toggle_transpose_adjustment();
                char buf[128];
                sprintf_s(buf, "Suggested transpose: [%d]", best);
                MessageBoxA(hWnd, buf, "Transpose Suggestion", MB_OK | MB_ICONINFORMATION);
            }
            break;
        }
        break;
    }

    case WM_CTLCOLORSTATIC:
    {
        HDC hdc = reinterpret_cast<HDC>(wParam);
        HWND ctrl = reinterpret_cast<HWND>(lParam);
        int cid = GetDlgCtrlID(ctrl);
        if (cid == ID_EDIT_LOG || cid == ID_EDIT_TRACKS || cid == ID_EDIT_DETAILS) {
            static HFONT hMonospaceFont = nullptr;
            if (!hMonospaceFont) {
                LOGFONT lf = {};
                lf.lfHeight = -14;
                wcscpy_s(lf.lfFaceName, L"Consolas");
                hMonospaceFont = CreateFontIndirect(&lf);
            }
            if (cid == ID_EDIT_LOG) {
                static HBRUSH hbrLogBg = nullptr;
                if (!hbrLogBg)
                    hbrLogBg = CreateSolidBrush(RGB(230, 255, 230));
                SetBkMode(hdc, OPAQUE);
                SetBkColor(hdc, RGB(230, 255, 230));
                SetTextColor(hdc, RGB(40, 80, 40));
                SelectObject(hdc, hMonospaceFont);
                return reinterpret_cast<LRESULT>(hbrLogBg);
            }
            else {
                static HBRUSH hbrWhite = (HBRUSH)GetStockObject(WHITE_BRUSH);
                SetBkMode(hdc, OPAQUE);
                SetBkColor(hdc, RGB(255, 255, 255));
                SetTextColor(hdc, RGB(0, 0, 0));
                SelectObject(hdc, hMonospaceFont);
                return reinterpret_cast<LRESULT>(hbrWhite);
            }
        }
        SetBkMode(hdc, TRANSPARENT);
        static HBRUSH hbrWhite = (HBRUSH)GetStockObject(WHITE_BRUSH);
        return reinterpret_cast<LRESULT>(hbrWhite);
    }

    case WM_CTLCOLOREDIT:
    {
        HDC hdc = reinterpret_cast<HDC>(wParam);
        HWND ctrl = reinterpret_cast<HWND>(lParam);
        int cid = GetDlgCtrlID(ctrl);
        if (cid == ID_EDIT_LOG || cid == ID_EDIT_TRACKS || cid == ID_EDIT_DETAILS) {
            SendMessage(hWnd, WM_CTLCOLORSTATIC, wParam, lParam);
            return reinterpret_cast<LRESULT>(GetStockObject(NULL_BRUSH));
        }
        return DefWindowProc(hWnd, msg, wParam, lParam);
    }
    case WM_TIMER:
    {
        if (wParam == IDT_TIMELEFT_TIMER) {
            auto now = std::chrono::steady_clock::now();

            if (g_player) {
                wchar_t speedText[48];
                swprintf_s(speedText, L"Speed: %.2fx", g_player->current_speed);
                SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_SPEED), speedText);
                wchar_t transposeText[48];
                swprintf_s(transposeText, L"Transpose: %+d", g_player->currentTransposition);
                SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_TRANSPOSE), transposeText);
            }

            static unsigned long long lastPanicSerial = g_panicSerial.load(std::memory_order_acquire);
            static std::chrono::steady_clock::time_point panicVisibleUntil{};
            const auto panicSerial = g_panicSerial.load(std::memory_order_acquire);
            if (panicSerial != lastPanicSerial) {
                lastPanicSerial = panicSerial;
                panicVisibleUntil = now + std::chrono::seconds(2);
                SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_STATUS), L"PANIC - notes released");
            }
            else if (panicVisibleUntil.time_since_epoch().count() != 0 && now >= panicVisibleUntil) {
                panicVisibleUntil = {};
                SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_STATUS), L"Ready");
            }

            bool shouldUpdate = (now - g_lastTimeUpdate) >= TIME_UPDATE_INTERVAL;
            static bool lastPlaybackState = false;
            bool currentPlaybackState = g_player && !g_player->paused.load(std::memory_order_relaxed);
            if (currentPlaybackState != lastPlaybackState) {
                shouldUpdate = true;
                lastPlaybackState = currentPlaybackState;
            }
            if (!shouldUpdate)
                return 0;
            if (!g_player || !g_player->midiFileSelected.load(std::memory_order_relaxed)) {
                static bool lastWasDefault = false;
                if (!lastWasDefault) {
                    SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_TIME), L"0:00 / 0:00");
                    lastWasDefault = true;
                }
                UpdateWindowFocusability();
                return 0;
            }
            static wchar_t timeStr[32];
            g_lastTimeUpdate = now;
            double currentSeconds = 0.0;
            if (!g_player->paused.load(std::memory_order_relaxed))
                currentSeconds = std::chrono::duration<double>(g_player->get_adjusted_time()).count();
            else
                currentSeconds = std::chrono::duration<double>(g_player->total_adjusted_time).count(); // Use last stored time when paused
            currentSeconds = std::clamp(currentSeconds, 0.0, g_totalSongSeconds);
            if (!g_seekDragging && g_totalSongSeconds > 0.0) { const int seekPos = static_cast<int>(std::clamp((currentSeconds / g_totalSongSeconds) * 10000.0, 0.0, 10000.0)); SendMessage(GetDlgItem(hWnd, ID_SLIDER_SEEK), TBM_SETPOS, TRUE, seekPos); }
            int currentMins = static_cast<int>(currentSeconds) / 60;
            int currentSecs = static_cast<int>(currentSeconds) % 60;
            int totalMins = static_cast<int>(g_totalSongSeconds) / 60;
            int totalSecs = static_cast<int>(g_totalSongSeconds) % 60;
            static int lastCurrentMins = -1, lastCurrentSecs = -1;
            static int lastTotalMins = -1, lastTotalSecs = -1;
            if (currentMins != lastCurrentMins || currentSecs != lastCurrentSecs ||
                totalMins != lastTotalMins || totalSecs != lastTotalSecs) {
                swprintf_s(timeStr, L"%d:%02d / %d:%02d",
                    std::min(currentMins, 999), currentSecs,
                    std::min(totalMins, 999), totalSecs);
                SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_TIME), timeStr);
                lastCurrentMins = currentMins;
                lastCurrentSecs = currentSecs;
                lastTotalMins = totalMins;
                lastTotalSecs = totalSecs;
            }
            static bool randomTriggered = false;
            if (g_randomSongEnabled && currentSeconds >= g_totalSongSeconds && !randomTriggered) {
                randomTriggered = true;
                std::vector<int> fileIndices;
                for (int i = 0; i < static_cast<int>(g_midiItems.size()); ++i) {
                    if (!g_midiItems[i].isFolder)
                        fileIndices.push_back(i);
                }
                if (!fileIndices.empty()) {
                    int currentSelection = static_cast<int>(SendMessage(g_lbMidi, LB_GETCURSEL, 0, 0));
                    bool currentInFiles = (std::find(fileIndices.begin(), fileIndices.end(), currentSelection) != fileIndices.end());
                    int randomIndex = currentSelection;
                    if (fileIndices.size() == 1) {
                        randomIndex = fileIndices[0];
                    }
                    else {
                        do {
                            randomIndex = fileIndices[rand() % fileIndices.size()];
                        } while (currentInFiles && randomIndex == currentSelection);
                    }
                    SendMessage(g_lbMidi, LB_SETCURSEL, randomIndex, 0);
                    PostMessage(hWnd, WM_COMMAND, MAKEWPARAM(ID_BTN_LOAD, BN_CLICKED),
                        reinterpret_cast<LPARAM>(GetDlgItem(hWnd, ID_BTN_LOAD)));
                    PostMessage(hWnd, WM_COMMAND, MAKEWPARAM(ID_BTN_PLAY, BN_CLICKED),
                        reinterpret_cast<LPARAM>(GetDlgItem(hWnd, ID_BTN_PLAY)));
                }
            }
            if (currentSeconds < g_totalSongSeconds)
                randomTriggered = false;
            UpdateWindowFocusability();
            return 0;
        }
        break;
    }
    case WM_DESTROY:
        if (g_player) {
            g_player->should_stop.store(true, std::memory_order_release);
            SetEvent(g_player->command_event);
            if (g_player->playback_thread && g_player->playback_thread->joinable()) {
                try {
                    g_player->playback_thread->join();
                    g_player->playback_thread.reset();
                    std::cout << "[GRACEFUL EXIT] Playback thread joined successfully.\n";
                }
                catch (const std::exception& e) {
                    std::cerr << "[GRACEFUL EXIT] Exception while joining playback thread: " << e.what() << "\n";
                }
                catch (...) {
                    std::cerr << "[GRACEFUL EXIT] Unknown exception while joining playback thread.\n";
                }
            }
            if (g_midi2key) {
                g_midi2key->SetActive(false);
                g_midi2key->CloseDevice();
                g_midi2key.reset();
            }
            if (g_midiConnect) {
                g_midiConnect->SetActive(false);
                g_midiConnect->CloseDevice();
                g_midiConnect.reset();
            }
            {
                std::lock_guard<std::mutex> lk(g_logMutex);
                g_logBuffer.clear();
            }
            g_toggleStates.clear();
            std::cout << "[GRACEFUL EXIT] Global states cleared.\n";
            PostQuitMessage(0);
            return 0;
        }
        break;
    }
    return DefWindowProc(hWnd, msg, wParam, lParam);
}

// -----------------------------------------------------------------------------
// Main Entry Point
// -----------------------------------------------------------------------------
int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE, PWSTR, int) {
    srand(static_cast<unsigned int>(time(NULL)));

    UniqueHandle singleInstanceMutex(CreateMutexW(nullptr, TRUE, L"Global\\MIDI++_On_Top"));
    g_hSingleInstanceMutex = singleInstanceMutex;
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        HWND existingWindow = FindWindowW(L"MIDI++", L"MIDI++ Custom Build");
        if (existingWindow) {
            if (IsIconic(existingWindow))
                ShowWindow(existingWindow, SW_RESTORE);
            SetForegroundWindow(existingWindow);
        }
        return 0;
    }

    GdiplusTokenWrapper gdiplusToken;
    Gdiplus::GdiplusStartupInput gdiplusStartupInput;
    if (Gdiplus::GdiplusStartup(&gdiplusToken.token, &gdiplusStartupInput, nullptr) != Gdiplus::Ok) {
        MessageBoxA(nullptr, "Failed to initialize GDI+.", "Error", MB_ICONERROR);
        return -1;
    }

    static VirtualPianoPlayer player;
    g_player = &player;

    RedirectCout();
    auto& cfg = midi::Config::getInstance();

    std::cout << " ===== MIDI++ Custom Build | Based on v1.0.4.R5 by Zeph, Tested by Gene =====\n";
    std::cout << "Hotkeys:\n";
    std::cout << "  Play/Pause:     " << getReadableKey(cfg.hotkeys.PLAY_PAUSE_KEY) << "\n";
    std::cout << "  Rewind:         " << getReadableKey(cfg.hotkeys.REWIND_KEY) << "\n";
    std::cout << "  Skip:           " << getReadableKey(cfg.hotkeys.SKIP_KEY) << "\n";
    std::cout << "  Panic/Release:  " << getReadableKey(cfg.hotkeys.PANIC_KEY) << "\n";
    g_hInst = hInstance;
    HICON hIcon = LoadIconW(hInstance, MAKEINTRESOURCEW(IDI_APP_ICON));
    HICON hIconSmall = LoadIconW(hInstance, MAKEINTRESOURCEW(IDI_APP_ICON_SMALL));
    if (!hIcon || !hIconSmall) {
        MessageBoxA(nullptr, "Failed to load application icons!", "Error", MB_ICONERROR);
        return -1;
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
    RegisterClassExW(&wc);
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
    SetLayeredWindowAttributes(g_hMainWnd, 0, static_cast<BYTE>(std::clamp(cfg.ui.opacity, 100, 255)), LWA_ALPHA);
    if (!g_hMainWnd) {
        MessageBoxA(nullptr, "Failed to create main window!", "Error", MB_ICONERROR);
        return -1;
    }
    ShowWindow(g_hMainWnd, SW_SHOW);
    UpdateWindow(g_hMainWnd);
    MSG msg;

    while (GetMessage(&msg, nullptr, 0, 0) > 0) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    return static_cast<int>(msg.wParam);
}
