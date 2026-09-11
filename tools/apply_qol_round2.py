from pathlib import Path

ROOT = Path('MIDIPlusPlus-1.0.4.R5_Rel')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, addition: str, label: str) -> str:
    if text.count(marker) != 1:
        raise RuntimeError(f'{label}: marker count {text.count(marker)}')
    return text.replace(marker, addition + marker, 1)

# -----------------------------------------------------------------------------
# PlaybackSystem.hpp
# -----------------------------------------------------------------------------
p = ROOT / 'PlaybackSystem.hpp'
text = p.read_text(encoding='utf-8')
text = replace_once(
    text,
    'extern int    g_sustainCutoff;\n',
    'extern int    g_sustainCutoff;\nextern std::atomic<unsigned long long> g_panicSerial;\n',
    'panic feedback global')
text = replace_once(
    text,
    '    void panic();\n    void calibrate_volume();\n',
    '    void panic();\n    void reset_playback_basics();\n    void calibrate_volume();\n',
    'reset playback declaration')
p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# PlaybackCore.cpp
# -----------------------------------------------------------------------------
p = ROOT / 'PlaybackCore.cpp'
text = p.read_text(encoding='utf-8')
text = replace_once(
    text,
    'double g_totalSongSeconds = 0.0;\n',
    'double g_totalSongSeconds = 0.0;\nstd::atomic<unsigned long long> g_panicSerial{ 0 };\n',
    'panic serial definition')

reset_impl = r'''void VirtualPianoPlayer::reset_playback_basics() {
    // Reset only transport/playback basics. Humanizer, velocity configuration,
    // sustain mode and sustain cutoff deliberately remain untouched.
    if (!paused.load(std::memory_order_acquire))
        toggle_play_pause();

    release_all_keys();
    current_speed = 1.0;
    time_factor = inv_cpu_freq * 1e9 * current_speed;
    currentTransposition = 0;

    for (auto& muted : trackMuted)
        if (muted) muted->store(false, std::memory_order_release);
    for (auto& soloed : trackSoloed)
        if (soloed) soloed->store(false, std::memory_order_release);

    total_adjusted_time = std::chrono::nanoseconds::zero();
    buffer_index.store(0, std::memory_order_release);
    if (midiFileSelected.load(std::memory_order_acquire))
        seek_to(std::chrono::nanoseconds::zero());

    std::cout << "[PLAYBACK] Reset: 0:00, speed 1.00x, transpose +0, mute/solo cleared.\n";
}

'''
text = insert_before(text, 'void VirtualPianoPlayer::speed_up() {', reset_impl, 'reset playback implementation')

panic_start = text.find('void VirtualPianoPlayer::panic() {')
panic_end = text.find('void VirtualPianoPlayer::initializeKeyCache()', panic_start)
if panic_start < 0 or panic_end < 0:
    raise RuntimeError('panic function bounds not found')
panic_segment = text[panic_start:panic_end]
if 'g_panicSerial.fetch_add' not in panic_segment:
    if 'release_all_keys();' not in panic_segment:
        raise RuntimeError('panic release_all_keys anchor missing')
    panic_segment = panic_segment.replace(
        'release_all_keys();',
        'release_all_keys();\n    g_panicSerial.fetch_add(1, std::memory_order_acq_rel);',
        1)
    text = text[:panic_start] + panic_segment + text[panic_end:]
p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# MIDI++.cpp
# -----------------------------------------------------------------------------
p = ROOT / 'MIDI++.cpp'
text = p.read_text(encoding='utf-8')
text = replace_once(text, '#include <filesystem>\n', '#include <filesystem>\n#include <fstream>\n', 'fstream include')
text = replace_once(text, '#include <shellapi.h>\n', '#include <shellapi.h>\n#include <commdlg.h>\n', 'commdlg include')
text = replace_once(text, '#pragma comment(lib, "Shell32.lib")\n', '#pragma comment(lib, "Shell32.lib")\n#pragma comment(lib, "Comdlg32.lib")\n', 'commdlg lib')

text = replace_once(text, '    static const int WIN_H = 790;\n', '    static const int WIN_H = 835;\n', 'window height')
text = replace_once(text, '    static const int PBASIC_H = 130;\n', '    static const int PBASIC_H = 175;\n', 'playback group height')

text = replace_once(text,
    '    ID_LB_MIDI,\n    ID_CB_RECENT,\n',
    '    ID_LB_MIDI,\n    ID_CB_RECENT,\n    ID_EDIT_MIDI_SEARCH,\n',
    'search control id')
text = replace_once(text,
    '    ID_BTN_RESTART,\n    ID_BTN_RELOAD,\n',
    '    ID_BTN_RESTART,\n    ID_BTN_RELOAD,\n    ID_BTN_RESET_PLAYBACK,\n',
    'reset control id')
text = replace_once(text,
    '    ID_STATIC_TIME,\n    ID_SLIDER_SEEK,\n',
    '    ID_STATIC_TIME,\n    ID_SLIDER_SEEK,\n    ID_STATIC_SPEED,\n    ID_STATIC_TRANSPOSE,\n    ID_STATIC_STATUS,\n',
    'status control ids')

search_helpers = r'''
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

'''
text = insert_before(text, 'static int GetSortMode() {', search_helpers, 'recursive MIDI search helpers')

# Humanizer popup IDs
text = replace_once(text,
    '    ID_HUM_SAVE_AS,\n    ID_HUM_UPDATE,\n    ID_HUM_DELETE,\n    ID_HUM_CLOSE\n',
    '    ID_HUM_SAVE_AS,\n    ID_HUM_UPDATE,\n    ID_HUM_DELETE,\n    ID_HUM_DUPLICATE,\n    ID_HUM_EXPORT,\n    ID_HUM_IMPORT,\n    ID_HUM_CLOSE\n',
    'humanizer import/export IDs')

preset_helpers = r'''
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

'''
text = insert_before(text, 'static LRESULT CALLBACK HumanizerWndProc', preset_helpers, 'preset import/export helpers')

# Humanizer popup bottom controls: add duplicate/export/import row and move action row down.
old_bottom = '''        HWND hint = CreateWindowW(L"static", L"Preset changes rebuild the loaded MIDI immediately. Manual edits rebuild when Apply is pressed.", WS_CHILD | WS_VISIBLE, 18, y, 565, 20, hwnd, nullptr, g_hInst, nullptr); SetDefaultGuiFont(hint);
        HWND apply = CreateWindowW(L"button", L"Apply", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON, 160, y + 32, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_APPLY), g_hInst, nullptr);
        HWND reset = CreateWindowW(L"button", L"Reset to Preset", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 258, y + 32, 115, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_RESET), g_hInst, nullptr);
        HWND close = CreateWindowW(L"button", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 381, y + 32, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_CLOSE), g_hInst, nullptr);
        SetDefaultGuiFont(apply); SetDefaultGuiFont(reset); SetDefaultGuiFont(close); PopulateHumanizerPopup(hwnd); return 0;
'''
new_bottom = '''        HWND hint = CreateWindowW(L"static", L"Preset changes rebuild the loaded MIDI immediately. Manual edits rebuild when Apply is pressed.", WS_CHILD | WS_VISIBLE, 18, y, 565, 20, hwnd, nullptr, g_hInst, nullptr); SetDefaultGuiFont(hint);
        HWND duplicate = CreateWindowW(L"button", L"Duplicate", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 145, y + 28, 90, 26, hwnd, reinterpret_cast<HMENU>(ID_HUM_DUPLICATE), g_hInst, nullptr);
        HWND exportBtn = CreateWindowW(L"button", L"Export", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 245, y + 28, 90, 26, hwnd, reinterpret_cast<HMENU>(ID_HUM_EXPORT), g_hInst, nullptr);
        HWND importBtn = CreateWindowW(L"button", L"Import", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 345, y + 28, 90, 26, hwnd, reinterpret_cast<HMENU>(ID_HUM_IMPORT), g_hInst, nullptr);
        HWND apply = CreateWindowW(L"button", L"Apply", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON, 160, y + 62, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_APPLY), g_hInst, nullptr);
        HWND reset = CreateWindowW(L"button", L"Reset to Preset", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 258, y + 62, 115, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_RESET), g_hInst, nullptr);
        HWND close = CreateWindowW(L"button", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 381, y + 62, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_CLOSE), g_hInst, nullptr);
        SetDefaultGuiFont(duplicate); SetDefaultGuiFont(exportBtn); SetDefaultGuiFont(importBtn);
        SetDefaultGuiFont(apply); SetDefaultGuiFont(reset); SetDefaultGuiFont(close); PopulateHumanizerPopup(hwnd); return 0;
'''
text = replace_once(text, old_bottom, new_bottom, 'humanizer popup buttons')
text = replace_once(text, 'CW_USEDEFAULT, CW_USEDEFAULT, 625, 545, owner, nullptr, g_hInst, nullptr);', 'CW_USEDEFAULT, CW_USEDEFAULT, 625, 580, owner, nullptr, g_hInst, nullptr);', 'humanizer popup height')

# Add Humanizer command cases before Delete.
duplicate_cases = r'''        case ID_HUM_DUPLICATE:
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
'''
text = insert_before(text, '        case ID_HUM_DELETE:\n', duplicate_cases, 'humanizer command cases')

# MIDI browser search UI and list sizing.
old_file_list = '''        g_lbMidi = CreateWindowW(L"listbox", nullptr,
            WS_CHILD | WS_VISIBLE | LBS_NOTIFY | WS_VSCROLL | WS_HSCROLL | WS_BORDER | LBS_NOINTEGRALHEIGHT,
            Layout::FILES_X + 10, Layout::FILES_Y + 50, 210, 310,
            hWnd, reinterpret_cast<HMENU>(ID_LB_MIDI), g_hInst, nullptr);
        SetWindowSubclass(g_lbMidi, MidiListSubclassProc, 0, 0);
'''
new_file_list = '''        HWND searchEdit = CreateWindowExW(WS_EX_CLIENTEDGE, L"edit", L"",
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
'''
text = replace_once(text, old_file_list, new_file_list, 'browser search UI')

# Remove the old overlapping Reload button from row 1.
old_reload = '''        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        CreateWindowW(L"button", L"Reload",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_RELOAD), g_hInst, nullptr);
        bx = Layout::PBASIC_X + 20;
'''
new_reload = '''        bx = Layout::PBASIC_X + 20;
'''
text = replace_once(text, old_reload, new_reload, 'move Reload button')

# Add third playback row after time display.
old_time = '''        CreateWindowW(L"static", L"0:00 / 0:00",
            WS_CHILD | WS_VISIBLE | SS_CENTER,
            Layout::PBASIC_X + 485, Layout::PBASIC_Y + 99, 105, 20,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_TIME), g_hInst, nullptr);

        // Advanced Group
'''
new_time = '''        CreateWindowW(L"static", L"0:00 / 0:00",
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
'''
text = replace_once(text, old_time, new_time, 'playback status row')

# Refresh button respects recursive search when search text is present.
text = replace_once(text,
    '''            if (code == BN_CLICKED) {
                ScanMidiFolder();
                SortMidiItems();
                PopulateMidiList();
                std::wcout << L"[Refresh] Scanned current MIDI folder: " << g_currentMidiDir.wstring() << L"\\n";
            }
''',
    '''            if (code == BN_CLICKED) {
                ScanMidiSearchResults(GetMidiBrowserSearchText());
                SortMidiItems();
                PopulateMidiList();
                std::wcout << L"[Refresh] MIDI browser refreshed.\\n";
            }
''',
    'refresh search behavior')

# Insert search command before recent combo handling.
search_case = r'''        case ID_EDIT_MIDI_SEARCH:
            if (code == EN_CHANGE) {
                ScanMidiSearchResults(GetMidiBrowserSearchText());
                SortMidiItems();
                PopulateMidiList();
            }
            break;

'''
text = insert_before(text, '        case ID_CB_RECENT:\n', search_case, 'search command')

# Reset playback command next to Reload.
reset_case = r'''        case ID_BTN_RESET_PLAYBACK:
            if (code == BN_CLICKED && g_player) {
                g_player->reset_playback_basics();
                UpdateTrackInfo();
                UpdateMidiDetails();
                SetWindowTextW(GetDlgItem(hWnd, ID_STATIC_STATUS), L"Playback reset");
            }
            break;

'''
text = insert_before(text, '        case ID_BTN_HELP:\n', reset_case, 'reset playback command')

# Add tooltips for the new controls.
text = replace_once(text,
    '        AddToolTip(hWnd, ID_BTN_RELOAD, L"Rebuild the currently loaded MIDI without browsing to it again.");\n',
    '        AddToolTip(hWnd, ID_BTN_RELOAD, L"Rebuild the currently loaded MIDI without browsing to it again.");\n        AddToolTip(hWnd, ID_BTN_RESET_PLAYBACK, L"Return to 0:00, speed 1.00x and transpose +0, and clear mute/solo. Humanizer, Velocity and Sustain mode are not changed.");\n',
    'reset tooltip')

# Timer: visible speed/transpose and panic feedback, independent of slower time-text refresh.
timer_anchor = '''        if (wParam == IDT_TIMELEFT_TIMER) {
            auto now = std::chrono::steady_clock::now();
            bool shouldUpdate = (now - g_lastTimeUpdate) >= TIME_UPDATE_INTERVAL;
'''
timer_replace = '''        if (wParam == IDT_TIMELEFT_TIMER) {
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
'''
text = replace_once(text, timer_anchor, timer_replace, 'timer status displays')

# Help text additions.
text = replace_once(text,
    '    L"Different timing each play: off = repeatable timing; on = a new micro-performance each load/play.\\r\\n\\r\\n"\n',
    '    L"Different timing each play: off = repeatable timing; on = a new micro-performance each load/play.\\r\\n"\n    L"Duplicate/Export/Import: copy presets locally or move a Humanizer preset between MIDI++ installs.\\r\\n\\r\\n"\n',
    'help humanizer import/export')

p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# Documentation
# -----------------------------------------------------------------------------
p = Path('UPDATE_NOTES.md')
text = p.read_text(encoding='utf-8')
append = r'''

## QoL round 2

- Added Humanizer preset duplication plus JSON preset export/import.
- F4 Panic now has visible two-second feedback in the Playback panel in addition to the log.
- Added always-visible speed and transpose readouts.
- Added Reset Playback: returns to 0:00, speed 1.00x, transpose +0, and clears track mute/solo without changing Humanizer, Velocity, or Sustain mode.
- Added recursive MIDI browser search across the entire `midi` folder and all subfolders.
- Moved Reload out of an overlapping control position and added a dedicated playback status row.
'''
if '## QoL round 2' not in text:
    text += append
p.write_text(text, encoding='utf-8')

print('QoL round 2 patch applied successfully.')
