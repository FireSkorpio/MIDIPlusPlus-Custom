from pathlib import Path
import json
import re

ROOT = Path('MIDIPlusPlus-1.0.4.R5_Rel')


def read(name):
    return (ROOT / name).read_text(encoding='utf-8')


def write(name, text):
    (ROOT / name).write_text(text, encoding='utf-8', newline='')


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


def insert_before(text, marker, insertion, label):
    if marker not in text:
        raise RuntimeError(f'{label}: marker not found')
    return text.replace(marker, insertion + marker, 1)


def replace_between(text, start, end, replacement, label):
    i = text.find(start)
    if i < 0:
        raise RuntimeError(f'{label}: start marker not found')
    j = text.find(end, i)
    if j < 0:
        raise RuntimeError(f'{label}: end marker not found')
    return text[:i] + replacement + text[j:]


# -----------------------------------------------------------------------------
# ConfigHandler.cpp
# -----------------------------------------------------------------------------
text = read('ConfigHandler.cpp')
text = replace_once(text, '#include <algorithm>\n', '#include <algorithm>\n#include <windows.h>\n', 'ConfigHandler windows include')

text = replace_once(
    text,
    '        validateKey(SKIP_KEY);\n        validateKey(EMERGENCY_EXIT_KEY);\n',
    '        validateKey(SKIP_KEY);\n        validateKey(PANIC_KEY);\n',
    'Hotkey validation rename')

text = replace_once(
    text,
    '''    Config& Config::getInstance() {
        static Config instance;
        return instance;
    }

    void Config::loadFromFile(const std::filesystem::path& path) {
        if (!std::filesystem::exists(path)) {
            throw ConfigException("Config file not found: " + path.string());
        }

        try {
            std::ifstream file(path);
''',
    '''    Config& Config::getInstance() {
        static Config instance;
        return instance;
    }

    std::filesystem::path Config::resolvePath(const std::filesystem::path& path) {
        if (path.is_absolute())
            return path;

        wchar_t modulePath[32768]{};
        DWORD len = GetModuleFileNameW(nullptr, modulePath, static_cast<DWORD>(std::size(modulePath)));
        if (len == 0 || len >= std::size(modulePath))
            return path;

        std::filesystem::path exeDir = std::filesystem::path(modulePath).parent_path();
        return exeDir / path;
    }

    void Config::loadFromFile(const std::filesystem::path& path) {
        const auto resolvedPath = resolvePath(path);
        if (!std::filesystem::exists(resolvedPath)) {
            throw ConfigException("Config file not found: " + resolvedPath.string());
        }

        try {
            std::ifstream file(resolvedPath);
''',
    'Config path resolver/load')

text = replace_once(
    text,
    '''    void Config::saveToFile(const std::filesystem::path& path) const {
        try {
            json j;
            to_json(j, *this);
            std::ofstream file(path);
            file << j.dump(4);
''',
    '''    void Config::saveToFile(const std::filesystem::path& path) const {
        try {
            json j;
            to_json(j, *this);
            const auto resolvedPath = resolvePath(path);
            std::ofstream file(resolvedPath);
            file << j.dump(4);
''',
    'Config save resolver')

text = replace_once(
    text,
    '''            humanizer.validate();
            auto_transpose.validate();
            hotkeys.validate();
            validateKeyMappings();
''',
    '''            humanizer.validate();
            if (customHumanizerPresets.size() > MAX_CUSTOM_HUMANIZER_PRESETS)
                throw ConfigException("A maximum of 5 custom Humanizer presets is supported");
            for (const auto& preset : customHumanizerPresets) {
                if (preset.name.empty())
                    throw ConfigException("Custom Humanizer preset names cannot be empty");
                preset.settings.validate();
            }
            auto_transpose.validate();
            hotkeys.validate();
            validateKeyMappings();
''',
    'Config preset validation')

text = replace_once(
    text,
    '''            {"SEQUENTIAL_MAX_GAP_MS", h.SEQUENTIAL_MAX_GAP_MS},
            {"RANDOMIZE_EACH_PLAY", h.RANDOMIZE_EACH_PLAY}
''',
    '''            {"SEQUENTIAL_MAX_GAP_MS", h.SEQUENTIAL_MAX_GAP_MS},
            {"RANDOMIZE_EACH_PLAY", h.RANDOMIZE_EACH_PLAY},
            {"PERFORMANCE_SEED", h.PERFORMANCE_SEED}
''',
    'Humanizer seed serialization')

text = replace_once(
    text,
    '''        if (j.contains("SEQUENTIAL_MAX_GAP_MS")) j.at("SEQUENTIAL_MAX_GAP_MS").get_to(h.SEQUENTIAL_MAX_GAP_MS);
        if (j.contains("RANDOMIZE_EACH_PLAY")) j.at("RANDOMIZE_EACH_PLAY").get_to(h.RANDOMIZE_EACH_PLAY);
''',
    '''        if (j.contains("SEQUENTIAL_MAX_GAP_MS")) j.at("SEQUENTIAL_MAX_GAP_MS").get_to(h.SEQUENTIAL_MAX_GAP_MS);
        if (j.contains("RANDOMIZE_EACH_PLAY")) j.at("RANDOMIZE_EACH_PLAY").get_to(h.RANDOMIZE_EACH_PLAY);
        if (j.contains("PERFORMANCE_SEED")) j.at("PERFORMANCE_SEED").get_to(h.PERFORMANCE_SEED);
''',
    'Humanizer seed loading')

old_ui = '''    void to_json(nlohmann::json& j, const UISettings& ui) {
        j = nlohmann::json{ {"alwaysOnTop", ui.alwaysOnTop} };
    }

    void from_json(const nlohmann::json& j, UISettings& ui) {
        j.at("alwaysOnTop").get_to(ui.alwaysOnTop);
    }
'''
new_ui = '''    void to_json(nlohmann::json& j, const UISettings& ui) {
        j = nlohmann::json{
            {"alwaysOnTop", ui.alwaysOnTop},
            {"opacity", ui.opacity},
            {"lastMidiDirectory", ui.lastMidiDirectory},
            {"recentMidiFiles", ui.recentMidiFiles}
        };
    }

    void from_json(const nlohmann::json& j, UISettings& ui) {
        if (j.contains("alwaysOnTop")) j.at("alwaysOnTop").get_to(ui.alwaysOnTop);
        if (j.contains("opacity")) j.at("opacity").get_to(ui.opacity);
        if (j.contains("lastMidiDirectory")) j.at("lastMidiDirectory").get_to(ui.lastMidiDirectory);
        if (j.contains("recentMidiFiles") && j.at("recentMidiFiles").is_array()) {
            ui.recentMidiFiles.clear();
            for (const auto& item : j.at("recentMidiFiles")) {
                if (item.is_string() && ui.recentMidiFiles.size() < 5)
                    ui.recentMidiFiles.push_back(item.get<std::string>());
            }
        }
        ui.opacity = std::clamp(ui.opacity, 100, 255);
    }
'''
text = replace_once(text, old_ui, new_ui, 'UI settings serialization')

old_hotkey_json = '''    void to_json(nlohmann::json& j, const HotkeySettings& h) {
        j = nlohmann::json{
            {"SUSTAIN_KEY", h.SUSTAIN_KEY},
            {"VOLUME_UP_KEY", h.VOLUME_UP_KEY},
            {"VOLUME_DOWN_KEY", h.VOLUME_DOWN_KEY},
            {"PLAY_PAUSE_KEY", h.PLAY_PAUSE_KEY},
            {"REWIND_KEY", h.REWIND_KEY},
            {"SKIP_KEY", h.SKIP_KEY},
            {"EMERGENCY_EXIT_KEY", h.EMERGENCY_EXIT_KEY}
        };
    }

    void from_json(const nlohmann::json& j, HotkeySettings& h) {
        // Optional reads keep older R5 configs usable. Missing keys retain the
        // defaults declared in HotkeySettings.
        if (j.contains("SUSTAIN_KEY")) j.at("SUSTAIN_KEY").get_to(h.SUSTAIN_KEY);
        if (j.contains("VOLUME_UP_KEY")) j.at("VOLUME_UP_KEY").get_to(h.VOLUME_UP_KEY);
        if (j.contains("VOLUME_DOWN_KEY")) j.at("VOLUME_DOWN_KEY").get_to(h.VOLUME_DOWN_KEY);
        if (j.contains("PLAY_PAUSE_KEY")) j.at("PLAY_PAUSE_KEY").get_to(h.PLAY_PAUSE_KEY);
        if (j.contains("REWIND_KEY")) j.at("REWIND_KEY").get_to(h.REWIND_KEY);
        if (j.contains("SKIP_KEY")) j.at("SKIP_KEY").get_to(h.SKIP_KEY);
        if (j.contains("EMERGENCY_EXIT_KEY")) j.at("EMERGENCY_EXIT_KEY").get_to(h.EMERGENCY_EXIT_KEY);
        h.validate();
    }
'''
new_hotkey_json = '''    void to_json(nlohmann::json& j, const HotkeySettings& h) {
        j = nlohmann::json{
            {"SUSTAIN_KEY", h.SUSTAIN_KEY},
            {"VOLUME_UP_KEY", h.VOLUME_UP_KEY},
            {"VOLUME_DOWN_KEY", h.VOLUME_DOWN_KEY},
            {"PLAY_PAUSE_KEY", h.PLAY_PAUSE_KEY},
            {"REWIND_KEY", h.REWIND_KEY},
            {"SKIP_KEY", h.SKIP_KEY},
            {"PANIC_KEY", h.PANIC_KEY}
        };
    }

    void from_json(const nlohmann::json& j, HotkeySettings& h) {
        if (j.contains("SUSTAIN_KEY")) j.at("SUSTAIN_KEY").get_to(h.SUSTAIN_KEY);
        if (j.contains("VOLUME_UP_KEY")) j.at("VOLUME_UP_KEY").get_to(h.VOLUME_UP_KEY);
        if (j.contains("VOLUME_DOWN_KEY")) j.at("VOLUME_DOWN_KEY").get_to(h.VOLUME_DOWN_KEY);
        if (j.contains("PLAY_PAUSE_KEY")) j.at("PLAY_PAUSE_KEY").get_to(h.PLAY_PAUSE_KEY);
        if (j.contains("REWIND_KEY")) j.at("REWIND_KEY").get_to(h.REWIND_KEY);
        if (j.contains("SKIP_KEY")) j.at("SKIP_KEY").get_to(h.SKIP_KEY);
        if (j.contains("PANIC_KEY"))
            j.at("PANIC_KEY").get_to(h.PANIC_KEY);
        else if (j.contains("EMERGENCY_EXIT_KEY"))
            j.at("EMERGENCY_EXIT_KEY").get_to(h.PANIC_KEY);
        h.validate();
    }
'''
text = replace_once(text, old_hotkey_json, new_hotkey_json, 'Panic hotkey serialization')

text = replace_once(
    text,
    '''        if (j.contains("CUSTOM_VELOCITY_CURVES")) {
            for (const auto& curveJson : j["CUSTOM_VELOCITY_CURVES"]) {
''',
    '''        if (j.contains("CUSTOM_VELOCITY_CURVES")) {
            p.customVelocityCurves.clear();
            for (const auto& curveJson : j["CUSTOM_VELOCITY_CURVES"]) {
''',
    'Velocity curve duplicate prevention')

text = replace_once(
    text,
    '''            {"HUMANIZER_SETTINGS", c.humanizer},
            {"AUTO_TRANSPOSE", c.auto_transpose},
''',
    '''            {"HUMANIZER_SETTINGS", c.humanizer},
            {"HUMANIZER_ACTIVE_PRESET", c.activeHumanizerPreset},
            {"HUMANIZER_PRESETS", json::array()},
            {"AUTO_TRANSPOSE", c.auto_transpose},
''',
    'Config preset JSON keys')

text = replace_once(
    text,
    '''        for (const auto& curve : c.playback.customVelocityCurves) {
            j["CUSTOM_VELOCITY_CURVES"].push_back({
                {"name", curve.name},
                {"values", curve.velocityValues}
                });
        }
''',
    '''        for (const auto& curve : c.playback.customVelocityCurves) {
            j["CUSTOM_VELOCITY_CURVES"].push_back({
                {"name", curve.name},
                {"values", curve.velocityValues}
                });
        }
        for (const auto& preset : c.customHumanizerPresets) {
            j["HUMANIZER_PRESETS"].push_back({
                {"name", preset.name},
                {"settings", preset.settings}
                });
        }
''',
    'Config custom preset serialization loop')

text = replace_once(
    text,
    '''        else if (j.contains("LEGIT_MODE_SETTINGS")) {
            const auto& legacy = j.at("LEGIT_MODE_SETTINGS");
            if (legacy.contains("ENABLED"))
                legacy.at("ENABLED").get_to(c.humanizer.ENABLED);
        }
        j.at("AUTO_TRANSPOSE").get_to(c.auto_transpose);
''',
    '''        else if (j.contains("LEGIT_MODE_SETTINGS")) {
            const auto& legacy = j.at("LEGIT_MODE_SETTINGS");
            if (legacy.contains("ENABLED"))
                legacy.at("ENABLED").get_to(c.humanizer.ENABLED);
        }

        c.activeHumanizerPreset = "Custom (Modified)";
        if (j.contains("HUMANIZER_ACTIVE_PRESET") && j.at("HUMANIZER_ACTIVE_PRESET").is_string())
            j.at("HUMANIZER_ACTIVE_PRESET").get_to(c.activeHumanizerPreset);

        c.customHumanizerPresets.clear();
        if (j.contains("HUMANIZER_PRESETS") && j.at("HUMANIZER_PRESETS").is_array()) {
            for (const auto& item : j.at("HUMANIZER_PRESETS")) {
                if (c.customHumanizerPresets.size() >= Config::MAX_CUSTOM_HUMANIZER_PRESETS)
                    break;
                if (!item.contains("name") || !item.contains("settings"))
                    continue;
                HumanizerPreset preset;
                item.at("name").get_to(preset.name);
                item.at("settings").get_to(preset.settings);
                if (!preset.name.empty())
                    c.customHumanizerPresets.push_back(std::move(preset));
            }
        }

        j.at("AUTO_TRANSPOSE").get_to(c.auto_transpose);
''',
    'Config custom preset loading')

start = text.find('        // Humanizer settings\n', text.find('void Config::setDefaults()'))
end = text.find('        // AutoTranspose settings\n', start)
if start < 0 or end < 0:
    raise RuntimeError('setDefaults Humanizer markers not found')
humanizer_defaults = '''        // Humanizer settings - Casual is the visible, hobby-player preset.
        humanizer = HumanizerSettings{};
        humanizer.ENABLED = true;
        humanizer.CHORD_DETECTION_WINDOW_MS = 50;
        humanizer.CHORD_PRESS_MIN_SPREAD_MS = 32;
        humanizer.CHORD_PRESS_MAX_SPREAD_MS = 78;
        humanizer.CHORD_RELEASE_MIN_SPREAD_MS = 25;
        humanizer.CHORD_RELEASE_MAX_SPREAD_MS = 64;
        humanizer.SIMULTANEOUS_FINGER_CHANCE_PERCENT = 10;
        humanizer.SEQUENTIAL_ARTICULATION = true;
        humanizer.SEQUENTIAL_TRIGGER_WINDOW_MS = 200;
        humanizer.SEQUENTIAL_MIN_GAP_MS = 40;
        humanizer.SEQUENTIAL_MAX_GAP_MS = 100;
        humanizer.RANDOMIZE_EACH_PLAY = false;
        humanizer.PERFORMANCE_SEED = 0x6d6964692b2b4831ULL;
        activeHumanizerPreset = "Casual";
        customHumanizerPresets.clear();

'''
text = text[:start] + humanizer_defaults + text[end:]

hotkey_start = text.find('        // Hotkey settings', text.find('void Config::setDefaults()'))
hotkey_end = text.find('        // Setup default LIMITED key mappings', hotkey_start)
if hotkey_start < 0 or hotkey_end < 0:
    raise RuntimeError('setDefaults hotkey markers not found')
text = text[:hotkey_start] + '''        // Hotkey settings. F4 is a safe panic instead of terminating MIDI++.
        hotkeys = HotkeySettings{};

        ui.opacity = 255;
        ui.lastMidiDirectory = "midi";
        ui.recentMidiFiles.clear();

''' + text[hotkey_end:]

write('ConfigHandler.cpp', text)


# -----------------------------------------------------------------------------
# PlaybackSystem.hpp
# -----------------------------------------------------------------------------
text = read('PlaybackSystem.hpp')
text = replace_once(text,
    '    enum class Command { NONE, SKIP, REWIND, RESTART };',
    '    enum class Command { NONE, SKIP, REWIND, SEEK, RESTART };',
    'Playback command enum')
text = replace_once(text,
    '    void requestRewind(std::chrono::seconds amount);\n    bool hasCommand() const;',
    '    void requestRewind(std::chrono::seconds amount);\n    void requestSeek(std::chrono::nanoseconds position);\n    bool hasCommand() const;',
    'Playback seek declaration')
text = replace_once(text,
    '    std::chrono::seconds command_amount{ 0 };\n    std::atomic<bool> command_processed{ true };',
    '    std::chrono::seconds command_amount{ 0 };\n    std::chrono::nanoseconds command_position{ 0 };\n    std::atomic<bool> command_processed{ true };',
    'Playback seek storage')
text = replace_once(text,
    '    void rewind(std::chrono::seconds duration);\n    void restart_song();',
    '    void rewind(std::chrono::seconds duration);\n    void seek_to(std::chrono::nanoseconds position);\n    void restart_song();',
    'Player seek declaration')
text = replace_once(text,
    '    void release_all_keys();\n    void calibrate_volume();',
    '    void release_all_keys();\n    void panic();\n    void calibrate_volume();',
    'Player panic declaration')
text = text.replace('emergency_exit_key_code', 'panic_key_code')
text = text.replace('    void emergency_exit();\n', '')
write('PlaybackSystem.hpp', text)


# -----------------------------------------------------------------------------
# PlaybackCore.cpp
# -----------------------------------------------------------------------------
text = read('PlaybackCore.cpp')

text = replace_once(text,
    '''void PlaybackControl::requestRewind(std::chrono::seconds amount) {
    std::lock_guard<std::mutex> lock(mutex);
    pending_command = Command::REWIND;
    command_amount = amount;
    command_processed.store(false, std::memory_order_release);
    SetEvent(VirtualPianoPlayer::command_event); // Signal command event
}

bool PlaybackControl::hasCommand() const {
''',
    '''void PlaybackControl::requestRewind(std::chrono::seconds amount) {
    std::lock_guard<std::mutex> lock(mutex);
    pending_command = Command::REWIND;
    command_amount = amount;
    command_processed.store(false, std::memory_order_release);
    SetEvent(VirtualPianoPlayer::command_event); // Signal command event
}

void PlaybackControl::requestSeek(std::chrono::nanoseconds position) {
    std::lock_guard<std::mutex> lock(mutex);
    pending_command = Command::SEEK;
    command_position = std::max(position, std::chrono::nanoseconds::zero());
    command_processed.store(false, std::memory_order_release);
    SetEvent(VirtualPianoPlayer::command_event);
}

bool PlaybackControl::hasCommand() const {
''',
    'Playback requestSeek implementation')

text = replace_once(text,
    '''    case Command::REWIND:
        new_state.position = (scaled > new_state.position) ? std::chrono::nanoseconds(0)
            : new_state.position - scaled;
        new_state.needs_reset = true;
        break;
    default:
''',
    '''    case Command::REWIND:
        new_state.position = (scaled > new_state.position) ? std::chrono::nanoseconds(0)
            : new_state.position - scaled;
        new_state.needs_reset = true;
        break;
    case Command::SEEK:
        new_state.position = command_position;
        new_state.needs_reset = true;
        break;
    default:
''',
    'Playback SEEK processing')

text = replace_once(text,
    '''        try {
            if (std::filesystem::exists("config.json")) {
                std::filesystem::copy_file(
                    "config.json", "config.invalid.backup.json",
                    std::filesystem::copy_options::overwrite_existing);
            }
            std::ofstream errorFile("config_error.txt", std::ios::trunc);
''',
    '''        try {
            const auto configPath = midi::Config::resolvePath("config.json");
            const auto backupPath = configPath.parent_path() / "config.invalid.backup.json";
            const auto errorPath = configPath.parent_path() / "config_error.txt";
            if (std::filesystem::exists(configPath)) {
                std::filesystem::copy_file(
                    configPath, backupPath,
                    std::filesystem::copy_options::overwrite_existing);
            }
            std::ofstream errorFile(errorPath, std::ios::trunc);
''',
    'Portable config backup')

text = replace_once(text,
    '''    uint64_t sessionSeed = 0x6d6964692b2b4831ULL; // "midi++H1"
    if (settings.RANDOMIZE_EACH_PLAY) {
''',
    '''    uint64_t sessionSeed = settings.PERFORMANCE_SEED;
    if (settings.RANDOMIZE_EACH_PLAY) {
''',
    'Humanizer performance seed')

hotkey_start = 'void VirtualPianoPlayer::hotkey_listener() {'
hotkey_end = 'void VirtualPianoPlayer::initializeKeyCache() {'
panic_block = r'''void VirtualPianoPlayer::hotkey_listener() {
    int playPauseVK = stringToVK(midi::Config::getInstance().hotkeys.PLAY_PAUSE_KEY);
    int rewindVK = stringToVK(midi::Config::getInstance().hotkeys.REWIND_KEY);
    int skipVK = stringToVK(midi::Config::getInstance().hotkeys.SKIP_KEY);
    int panicVK = stringToVK(midi::Config::getInstance().hotkeys.PANIC_KEY);

    bool wasPlayPause = false, wasRewind = false, wasSkip = false, wasPanic = false;

    while (!hotkey_stop.load(std::memory_order_acquire)) {
        bool playPauseDown = (GetAsyncKeyState(playPauseVK) & 0x8000) != 0;
        bool rewindDown = (GetAsyncKeyState(rewindVK) & 0x8000) != 0;
        bool skipDown = (GetAsyncKeyState(skipVK) & 0x8000) != 0;
        bool panicDown = (GetAsyncKeyState(panicVK) & 0x8000) != 0;

        if (playPauseDown && !wasPlayPause)
            toggle_play_pause();
        if (rewindDown && !wasRewind)
            rewind(std::chrono::seconds(10));
        if (skipDown && !wasSkip)
            skip(std::chrono::seconds(10));
        if (panicDown && !wasPanic)
            panic();

        wasPlayPause = playPauseDown;
        wasRewind = rewindDown;
        wasSkip = skipDown;
        wasPanic = panicDown;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}

void VirtualPianoPlayer::panic() {
    const bool wasPlaying = !paused.exchange(true, std::memory_order_acq_rel);
    if (wasPlaying && playback_started.load(std::memory_order_acquire)) {
        const unsigned long long currentTsc = __rdtsc();
        const unsigned long long tickDiff = currentTsc - last_resume_tsc;
        const double elapsedSeconds = static_cast<double>(tickDiff) * inv_cpu_freq;
        const auto elapsedNs = static_cast<std::chrono::nanoseconds::rep>(
            elapsedSeconds * 1e9 * current_speed + 0.5);
        total_adjusted_time += std::chrono::nanoseconds(elapsedNs);
    }
    release_all_keys();
    signalPlayback();
    std::cout << "[PANIC] Released all notes and paused playback. MIDI++ remains open.\n";
}

'''
text = replace_between(text, hotkey_start, hotkey_end, panic_block, 'Panic hotkey block')
text = text.replace('emergency_exit_key_code', 'panic_key_code')
text = text.replace('EMERGENCY_EXIT_KEY', 'PANIC_KEY')

seek_method = r'''void VirtualPianoPlayer::seek_to(std::chrono::nanoseconds position) {
    if (!midiFileSelected.load(std::memory_order_acquire))
        return;

    release_all_keys();
    const auto total = note_buffer.empty() ? std::chrono::nanoseconds::zero() : note_buffer.back()->time;
    position = std::clamp(position, std::chrono::nanoseconds::zero(), total);

    if (!playback_started.load(std::memory_order_acquire) || !playback_thread) {
        total_adjusted_time = position;
        buffer_index.store(find_next_event_index(position), std::memory_order_release);
        last_resume_tsc = __rdtsc();
        return;
    }

    playback_control.requestSeek(position);
    signalPlayback();
}

'''
text = insert_before(text, 'void VirtualPianoPlayer::speed_up() {', seek_method, 'Player seek implementation')
write('PlaybackCore.cpp', text)


# -----------------------------------------------------------------------------
# MIDI++.cpp
# -----------------------------------------------------------------------------
text = read('MIDI++.cpp')
text = replace_once(text, '#include <windowsx.h>\n', '#include <windowsx.h>\n#include <shellapi.h>\n', 'Shell drag-drop include')
text = replace_once(text, '#pragma comment(lib, "Gdiplus.lib")\n', '#pragma comment(lib, "Gdiplus.lib")\n#pragma comment(lib, "Shell32.lib")\n', 'Shell32 link')

text = replace_once(text,
    'static bool g_randomSongEnabled = false;\n',
    '''static bool g_randomSongEnabled = false;
static std::wstring g_currentLoadedMidiPath;
static bool g_seekDragging = false;
static HWND g_hToolTip = nullptr;
''',
    'QoL globals')

text = replace_once(text,
    '''    ID_BTN_REFRESH,
    ID_LB_MIDI,
''',
    '''    ID_BTN_REFRESH,
    ID_LB_MIDI,
    ID_CB_RECENT,
''',
    'Recent control ID')
text = replace_once(text,
    '''    ID_BTN_SPEEDDN,
    ID_BTN_RESTART,
''',
    '''    ID_BTN_SPEEDDN,
    ID_BTN_RESTART,
    ID_BTN_RELOAD,
''',
    'Reload control ID')
text = replace_once(text,
    '''    IDT_TIMELEFT_TIMER,
    ID_STATIC_TIME,
''',
    '''    IDT_TIMELEFT_TIMER,
    ID_STATIC_TIME,
    ID_SLIDER_SEEK,
''',
    'Seek control ID')

text = text.replace('    static const int WIN_H = 760;', '    static const int WIN_H = 790;')
text = text.replace('    static const int PBASIC_H = 100;', '    static const int PBASIC_H = 130;')
text = text.replace('if (!std::filesystem::equivalent(currentDir, "midi")) {',
                    'if (!std::filesystem::equivalent(currentDir, midi::Config::resolvePath("midi"))) {')
text = text.replace('std::filesystem::path favFolder = std::filesystem::path(L"midi") / L"favorite";',
                    'std::filesystem::path favFolder = midi::Config::resolvePath("midi") / L"favorite";')

selected_helper_end = '''static std::wstring GetSelectedMidiFullPath() {
    int sel = static_cast<int>(SendMessage(g_lbMidi, LB_GETCURSEL, 0, 0));
    if (sel == LB_ERR || sel < 0 || sel >= static_cast<int>(g_midiItems.size()))
        return L"";
    const MidiItem& item = g_midiItems[sel];
    if (item.isFolder)
        return L""; 
    return item.fullPath;
}

'''
helpers = r'''static std::string WideToUtf8(const std::wstring& value) {
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

'''
text = replace_once(text, selected_helper_end, selected_helper_end + helpers, 'QoL helper insertion')
text = replace_once(text,
    '    std::wstring wpath = GetSelectedMidiFullPath();\n',
    '    std::wstring wpath = !g_currentLoadedMidiPath.empty() ? g_currentLoadedMidiPath : GetSelectedMidiFullPath();\n',
    'Loaded-path details')

analysis_marker = '''    oss << " (" << totalNotes << " notes)";
    appendLine(oss.str());

    if (!mf.tempoChanges.empty()) {
'''
analysis_insert = r'''    oss << " (" << totalNotes << " notes)";
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
'''
text = replace_once(text, analysis_marker, analysis_insert, 'Expanded MIDI details')
text = replace_once(text,
    '''    lastLine += (humanizer ? " (Humanizer: On)" : " (Humanizer: Off)");
    lastLine += (filterDrums ? " (Ch10 Filter: On)" : " (Ch10 Filter: Off)");
''',
    '''    lastLine += (humanizer ? " (Humanizer: On)" : " (Humanizer: Off)");
    if (humanizer)
        lastLine += " (Preset: " + midi::Config::getInstance().activeHumanizerPreset + ")";
    lastLine += (filterDrums ? " (Ch10 Filter: On)" : " (Ch10 Filter: Off)");
''',
    'Details Humanizer preset')

load_helper = r'''static bool LoadMidiFilePath(HWND owner, const std::wstring& wpath, bool preserveSession) {
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

'''
text = insert_before(text, '// -----------------------------------------------------------------------------\n// Humanizer / Help popups\n// -----------------------------------------------------------------------------\n', load_helper, 'Load helper insertion')

start_marker = '// -----------------------------------------------------------------------------\n// Humanizer / Help popups\n// -----------------------------------------------------------------------------\n'
help_marker = 'static const wchar_t* kHelpText ='
hum_start = text.find(start_marker)
hum_end = text.find(help_marker, hum_start)
if hum_start < 0 or hum_end < 0:
    raise RuntimeError('Humanizer section markers not found')
humanizer_section = r'''// -----------------------------------------------------------------------------
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
        HWND apply = CreateWindowW(L"button", L"Apply", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON, 160, y + 32, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_APPLY), g_hInst, nullptr);
        HWND reset = CreateWindowW(L"button", L"Reset to Preset", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 258, y + 32, 115, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_RESET), g_hInst, nullptr);
        HWND close = CreateWindowW(L"button", L"Close", WS_CHILD | WS_VISIBLE | WS_TABSTOP, 381, y + 32, 90, 28, hwnd, reinterpret_cast<HMENU>(ID_HUM_CLOSE), g_hInst, nullptr);
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
    g_hHumanizerWnd = CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_DLGMODALFRAME, L"MIDIPlusPlusHumanizerPopup", L"MIDI++ Custom Build - Humanizer", WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU, CW_USEDEFAULT, CW_USEDEFAULT, 625, 545, owner, nullptr, g_hInst, nullptr);
    if (g_hHumanizerWnd) { CenterPopup(g_hHumanizerWnd, owner); ShowWindow(g_hHumanizerWnd, SW_SHOW); SetForegroundWindow(g_hHumanizerWnd); }
}

'''
text = text[:hum_start] + humanizer_section + text[hum_end:]

text = text.replace('F2 rewinds, F3 skips, F4 stops.', 'F2 rewinds, F3 skips, F4 panics/releases all notes without closing MIDI++.')
text = text.replace('Humanizer: edits Humanizer timing in milliseconds and saves it to config.json. Reload the MIDI after changing timing.', 'Humanizer: choose Professional, Intermediate, Casual, or up to 5 saved custom presets. Preset changes rebuild the loaded MIDI automatically; manual edits rebuild on Apply.')

text = replace_once(text,
    '''        g_lbMidi = CreateWindowW(L"listbox", nullptr,
            WS_CHILD | WS_VISIBLE | LBS_NOTIFY | WS_VSCROLL | WS_HSCROLL | WS_BORDER | LBS_NOINTEGRALHEIGHT,
            Layout::FILES_X + 10, Layout::FILES_Y + 50, 210, 350,
            hWnd, reinterpret_cast<HMENU>(ID_LB_MIDI), g_hInst, nullptr);
        SetWindowSubclass(g_lbMidi, MidiListSubclassProc, 0, 0);
''',
    '''        g_lbMidi = CreateWindowW(L"listbox", nullptr,
            WS_CHILD | WS_VISIBLE | LBS_NOTIFY | WS_VSCROLL | WS_HSCROLL | WS_BORDER | LBS_NOINTEGRALHEIGHT,
            Layout::FILES_X + 10, Layout::FILES_Y + 50, 210, 310,
            hWnd, reinterpret_cast<HMENU>(ID_LB_MIDI), g_hInst, nullptr);
        SetWindowSubclass(g_lbMidi, MidiListSubclassProc, 0, 0);
        CreateWindowW(L"static", L"Recent:", WS_CHILD | WS_VISIBLE,
            Layout::FILES_X + 10, Layout::FILES_Y + 365, 48, 20, hWnd, nullptr, g_hInst, nullptr);
        HWND recentCombo = CreateWindowW(L"combobox", nullptr, WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
            Layout::FILES_X + 60, Layout::FILES_Y + 362, 160, 130,
            hWnd, reinterpret_cast<HMENU>(ID_CB_RECENT), g_hInst, nullptr);
        SetDefaultGuiFont(recentCombo);
''',
    'Recent MIDI combo UI')

text = replace_once(text,
    '''        CreateWindowW(L"button", L"Restart",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_RESTART), g_hInst, nullptr);
        bx = Layout::PBASIC_X + 20;
''',
    '''        CreateWindowW(L"button", L"Restart",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_RESTART), g_hInst, nullptr);
        bx += Layout::PB_BTN_WIDTH + Layout::PB_BTN_GAP;
        CreateWindowW(L"button", L"Reload",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            bx, Layout::PB_ROW1_Y, Layout::PB_BTN_WIDTH, Layout::PB_BTN_HEIGHT,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_RELOAD), g_hInst, nullptr);
        bx = Layout::PBASIC_X + 20;
''',
    'Reload button')

old_time = '''        CreateWindowW(L"static", L"0:00 / 0:00",
            WS_CHILD | WS_VISIBLE | SS_CENTER,
            Layout::PB_STATIC_TIME_X - 90, Layout::PB_STATIC_TIME_Y + 36,
            Layout::PB_STATIC_TIME_W - 50, Layout::PB_STATIC_TIME_H,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_TIME), g_hInst, nullptr);
'''
new_time = '''        HWND seekSlider = CreateWindowExW(0, TRACKBAR_CLASSW, L"",
            WS_CHILD | WS_VISIBLE | TBS_NOTICKS,
            Layout::PBASIC_X + 15, Layout::PBASIC_Y + 96, 465, 25,
            hWnd, reinterpret_cast<HMENU>(ID_SLIDER_SEEK), g_hInst, nullptr);
        SendMessage(seekSlider, TBM_SETRANGE, TRUE, MAKELPARAM(0, 10000));
        SendMessage(seekSlider, TBM_SETPOS, TRUE, 0);
        CreateWindowW(L"static", L"0:00 / 0:00",
            WS_CHILD | WS_VISIBLE | SS_CENTER,
            Layout::PBASIC_X + 485, Layout::PBASIC_Y + 99, 105, 20,
            hWnd, reinterpret_cast<HMENU>(ID_STATIC_TIME), g_hInst, nullptr);
'''
text = replace_once(text, old_time, new_time, 'Seek bar UI')

text = replace_once(text,
    '''        // Initial Setup
        ScanMidiFolder();
        SortMidiItems();
        PopulateMidiList();
''',
    '''        // Initial Setup
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
        AddToolTip(hWnd, ID_BTN_HUMANIZER, L"Human timing presets and exact millisecond controls. Changes rebuild the loaded MIDI automatically.");
        AddToolTip(hWnd, ID_BTN_88KEY, L"Use the full configured virtual-piano keyboard range.");
        AddToolTip(hWnd, ID_BTN_VOLADJ, L"Automatically calibrate and adjust Roblox volume/velocity keys.");
        AddToolTip(hWnd, ID_BTN_VELOCITY, L"Use MIDI note velocity when choosing virtual-piano velocity keys.");
        AddToolTip(hWnd, ID_BTN_TRANSPOSEOUT, L"Transpose notes that would otherwise fall outside the selected keyboard range.");
        AddToolTip(hWnd, ID_BTN_MIDI2QWERTY, L"Use a physical MIDI input device to send QWERTY piano keys.");
        AddToolTip(hWnd, ID_BTN_MIDICONNECT, L"Alternate live MIDI input mode using the specialized key injector.");
        AddToolTip(hWnd, ID_SLIDER_SEEK, L"Drag to seek directly through the loaded song.");
''',
    'Session/tooltips startup')

text = replace_once(text,
    '''        if (idCtrl == ID_SLIDER_SUSTAIN_CUTOFF) {
''',
    '''        if (idCtrl == ID_SLIDER_SEEK) {
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
''',
    'Seek slider handler')

text = replace_once(text,
    '''            SetWindowTextW(g_hOpacityIndicatorBox, opacityText);
        }
''',
    '''            SetWindowTextW(g_hOpacityIndicatorBox, opacityText);
            auto& cfg = midi::Config::getInstance(); cfg.ui.opacity = opacity;
            if (LOWORD(wParam) == TB_ENDTRACK || LOWORD(wParam) == TB_THUMBPOSITION) { try { cfg.saveToFile("config.json"); } catch (...) {} }
        }
''',
    'Opacity session save')

wm_command_marker = '    case WM_COMMAND:\n    {\n'
drop_case = r'''    case WM_DROPFILES:
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

'''
text = insert_before(text, wm_command_marker, drop_case, 'Drag-drop handler')

text = replace_once(text,
    '''        case ID_CB_SORT:
            if (code == CBN_SELCHANGE) {
''',
    '''        case ID_CB_RECENT:
            if (code == CBN_SELCHANGE) {
                HWND combo = GetDlgItem(hWnd, ID_CB_RECENT); int sel = static_cast<int>(SendMessage(combo, CB_GETCURSEL, 0, 0));
                const auto& recent = midi::Config::getInstance().ui.recentMidiFiles;
                if (sel >= 0 && sel < static_cast<int>(recent.size())) { std::wstring path = Utf8ToWide(recent[static_cast<size_t>(sel)]); if (std::filesystem::exists(path)) LoadMidiFilePath(hWnd, path, false); else MessageBoxW(hWnd, L"That recent MIDI file no longer exists.", L"Recent MIDI", MB_OK | MB_ICONINFORMATION); }
            }
            break;

        case ID_CB_SORT:
            if (code == CBN_SELCHANGE) {
''',
    'Recent command handler')

text = replace_once(text,
    '''        case ID_BTN_HUMANIZER:
            if (code == BN_CLICKED)
                ShowHumanizerPopup(hWnd);
            break;
''',
    '''        case ID_BTN_HUMANIZER:
            if (code == BN_CLICKED) ShowHumanizerPopup(hWnd);
            break;

        case ID_BTN_RELOAD:
            if (code == BN_CLICKED) { if (!ReloadCurrentMidi(hWnd)) MessageBoxW(hWnd, L"Load a MIDI file first.", L"Reload MIDI", MB_OK | MB_ICONINFORMATION); }
            break;
''',
    'Reload command handler')

load_case_start = '        case ID_BTN_LOAD:\n'
load_case_end = '        case ID_LB_MIDI:\n'
i = text.find(load_case_start); j = text.find(load_case_end, i)
if i < 0 or j < 0: raise RuntimeError('Load case markers not found')
new_load_case = r'''        case ID_BTN_LOAD:
            if (code == BN_CLICKED) {
                const std::wstring path = GetSelectedMidiFullPath();
                if (path.empty()) { std::cout << "[Load] No MIDI file selected.\n"; MessageBoxW(hWnd, L"Select a MIDI file first.", L"Load MIDI", MB_OK | MB_ICONINFORMATION); }
                else LoadMidiFilePath(hWnd, path, false);
            }
            break;

'''
text = text[:i] + new_load_case + text[j:]

text = replace_once(text,
    '''                        ScanMidiFolder();
                        SortMidiItems();
                        PopulateMidiList();
''',
    '''                        auto& cfg = midi::Config::getInstance(); cfg.ui.lastMidiDirectory = WideToUtf8(g_currentMidiDir.wstring()); try { cfg.saveToFile("config.json"); } catch (...) {}
                        ScanMidiFolder(); SortMidiItems(); PopulateMidiList();
''',
    'Remember MIDI folder')

text = replace_once(text,
    '''            currentSeconds = std::min(currentSeconds, g_totalSongSeconds);
            int currentMins = static_cast<int>(currentSeconds) / 60;
''',
    '''            currentSeconds = std::clamp(currentSeconds, 0.0, g_totalSongSeconds);
            if (!g_seekDragging && g_totalSongSeconds > 0.0) { const int seekPos = static_cast<int>(std::clamp((currentSeconds / g_totalSongSeconds) * 10000.0, 0.0, 10000.0)); SendMessage(GetDlgItem(hWnd, ID_SLIDER_SEEK), TBM_SETPOS, TRUE, seekPos); }
            int currentMins = static_cast<int>(currentSeconds) / 60;
''',
    'Seek timer synchronization')

text = text.replace('cfg.hotkeys.EMERGENCY_EXIT_KEY', 'cfg.hotkeys.PANIC_KEY')
text = text.replace('std::cout << "  Play Stop:      "', 'std::cout << "  Panic/Release:  "')
text = replace_once(text,
    '    SetLayeredWindowAttributes(g_hMainWnd, 0, 255, LWA_ALPHA);\n',
    '    SetLayeredWindowAttributes(g_hMainWnd, 0, static_cast<BYTE>(std::clamp(cfg.ui.opacity, 100, 255)), LWA_ALPHA);\n',
    'Startup opacity restore')

write('MIDI++.cpp', text)


# config.json shipped defaults
config_path = ROOT / 'config.json'
cfg = json.loads(config_path.read_text(encoding='utf-8'))
h = cfg.setdefault('HUMANIZER_SETTINGS', {})
h.update({'ENABLED': True, 'CHORD_DETECTION_WINDOW_MS': 50, 'CHORD_PRESS_MIN_SPREAD_MS': 32, 'CHORD_PRESS_MAX_SPREAD_MS': 78, 'CHORD_RELEASE_MIN_SPREAD_MS': 25, 'CHORD_RELEASE_MAX_SPREAD_MS': 64, 'SIMULTANEOUS_FINGER_CHANCE_PERCENT': 10, 'SEQUENTIAL_ARTICULATION': True, 'SEQUENTIAL_TRIGGER_WINDOW_MS': 200, 'SEQUENTIAL_MIN_GAP_MS': 40, 'SEQUENTIAL_MAX_GAP_MS': 100, 'RANDOMIZE_EACH_PLAY': False, 'PERFORMANCE_SEED': 0x6d6964692b2b4831})
cfg['HUMANIZER_ACTIVE_PRESET'] = 'Casual'; cfg['HUMANIZER_PRESETS'] = []
hot = cfg.setdefault('HOTKEY_SETTINGS', {}); hot['PANIC_KEY'] = hot.pop('EMERGENCY_EXIT_KEY', 'VK_F4')
ui = cfg.setdefault('UI_SETTINGS', {}); ui.setdefault('alwaysOnTop', True); ui.setdefault('opacity', 255); ui.setdefault('lastMidiDirectory', 'midi'); ui.setdefault('recentMidiFiles', [])
config_path.write_text(json.dumps(cfg, indent=4) + '\n', encoding='utf-8')

humanizer_doc = '''# MIDI++ Custom Build - Humanizer\n\nThe Humanizer modifies MIDI++'s prepared playback queue; it does not rewrite MIDI files.\n\n## Core timing rules\n\n- A Note On is never moved earlier than the source MIDI timestamp.\n- A Note Off is never moved later than the source MIDI timestamp.\n- Humanization can shorten a note slightly, but never makes it longer than the source MIDI note.\n- Sustain events are left alone.\n- Requested timing is constrained when a note is too short to support it.\n- Millisecond controls accept `0-1000` ms and percentages accept `0-100`.\n- Repeated-note protection runs after Humanizer timing.\n\n## Skill presets\n\n- **Professional** - tight, polished timing with subtle natural variation.\n- **Intermediate** - controlled hobby-player timing with clearly visible finger separation.\n- **Casual** - looser, visible articulation based on the tested Roblox settings.\n\nCasual uses chord detection `50 ms`, press spread `32-78 ms`, release spread `25-64 ms`, sequential gap `40-100 ms`, trigger window `200 ms`, and `10%` simultaneous-finger chance. Exact values remain editable.\n\n## Custom presets\n\nUp to **5** custom presets can be stored in `config.json`. Use **Save As**, **Update/Rename**, or **Delete** in the Humanizer window. Built-ins cannot be overwritten or deleted.\n\n## Automatic rebuild\n\nSelecting a preset immediately saves it and rebuilds the currently loaded MIDI. Manual edits rebuild when **Apply** is pressed. Playback is left paused at the beginning after a rebuild.\n\n## Repeatable performances\n\nWhen **Different timing each play** is off, `PERFORMANCE_SEED` makes the Humanizer repeatable. **New Performance** creates another repeatable timing pass and rebuilds the MIDI.\n\n## F4 Panic\n\nF4 is **Panic / Release All Notes**. It pauses playback, releases held keys/sustain, and keeps MIDI++ open.\n\n## Config safety\n\nMalformed configs are preserved as `config.invalid.backup.json`, the error is written to `config_error.txt`, and relative config paths resolve beside `MIDI++.exe`.\n'''
write('HUMANIZER.md', humanizer_doc)

notes_path = Path('UPDATE_NOTES.md')
if notes_path.exists():
    notes = notes_path.read_text(encoding='utf-8')
    addition = '\n## QoL update\n\n- Professional / Intermediate / Casual Humanizer presets.\n- Up to five saved custom Humanizer presets with rename/update/delete.\n- Automatic MIDI rebuild on preset changes and Apply.\n- Repeatable Humanizer performance seeds and New Performance.\n- F4 Panic / Release All Notes instead of closing MIDI++.\n- Seek bar, Reload Current MIDI, drag-and-drop loading, recent MIDI list, session opacity/folder memory, tooltips, and expanded MIDI details.\n- Portable config path handling and backward migration from EMERGENCY_EXIT_KEY to PANIC_KEY.\n- Virtual MIDI integration is intentionally not included.\n'
    if '## QoL update' not in notes: notes_path.write_text(notes.rstrip() + '\n' + addition, encoding='utf-8')

print('QoL patch applied successfully.')
