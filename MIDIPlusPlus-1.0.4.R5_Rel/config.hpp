#pragma once

#include <string>
#include <map>
#include <stdexcept>
#include <filesystem>
#include <optional>
#include <vector>
#include <array>
#include <cstdint>
#include "json.hpp"

namespace midi {

    class ConfigException : public std::runtime_error {
    public:
        explicit ConfigException(const std::string& message) : std::runtime_error(message) {}
    };

    enum class VelocityCurveType {
        LinearCoarse = 0,
        LinearFine = 1,
        ImprovedLowVolume = 2,
        Logarithmic = 3,
        Exponential = 4,
        Custom = 5
    };

    enum class NoteHandlingMode {
        FIFO,
        LIFO,
        NoHandling
    };

    struct VolumeSettings {
        int MIN_VOLUME = 10;
        int MAX_VOLUME = 200;
        int INITIAL_VOLUME = 100;
        int VOLUME_STEP = 10;
        int ADJUSTMENT_INTERVAL_MS = 50;

        void validate() const;
    };

    // Humanizer changes only timing inside the already-built playback queue.
    // It never moves a Note On earlier than the MIDI and never extends a Note
    // Off past its original timestamp.
    struct HumanizerSettings {
        bool ENABLED = true;

        int CHORD_DETECTION_WINDOW_MS = 3;
        int CHORD_PRESS_MIN_SPREAD_MS = 12;
        int CHORD_PRESS_MAX_SPREAD_MS = 36;
        int CHORD_RELEASE_MIN_SPREAD_MS = 8;
        int CHORD_RELEASE_MAX_SPREAD_MS = 26;
        int SIMULTANEOUS_FINGER_CHANCE_PERCENT = 10;

        bool SEQUENTIAL_ARTICULATION = true;
        int SEQUENTIAL_TRIGGER_WINDOW_MS = 200;
        int SEQUENTIAL_MIN_GAP_MS = 8;
        int SEQUENTIAL_MAX_GAP_MS = 20;

        // false = repeatable performance. true = a new timing pass every load.
        bool RANDOMIZE_EACH_PLAY = false;

        // Used when RANDOMIZE_EACH_PLAY is false. The Humanizer popup can
        // generate a new seed on demand, then keep that performance repeatable.
        std::uint64_t PERFORMANCE_SEED = 0x6d6964692b2b4831ULL;

        void validate() const;
    };

    struct HumanizerPreset {
        std::string name;
        HumanizerSettings settings;
    };

    struct AutoTranspose {
        bool ENABLED = false;
        std::string TRANSPOSE_UP_KEY = "VK_UP";
        std::string TRANSPOSE_DOWN_KEY = "VK_DOWN";

        void validate() const;
    };

    struct UISettings {
        bool alwaysOnTop = false;
        int opacity = 255;
        std::string lastMidiDirectory = "midi";
        std::vector<std::string> recentMidiFiles;
    };

    struct MIDISettings {
        bool FILTER_DRUMS = true;
        void validate() const;
    };

    struct HotkeySettings {
        std::string SUSTAIN_KEY = "VK_SPACE";
        std::string VOLUME_UP_KEY = "VK_RIGHT";
        std::string VOLUME_DOWN_KEY = "VK_LEFT";
        std::string PLAY_PAUSE_KEY = "VK_F1";
        std::string REWIND_KEY = "VK_F2";
        std::string SKIP_KEY = "VK_F3";
        std::string PANIC_KEY = "VK_F4";
        void validate() const;
    };

    struct CustomVelocityCurve {
        std::string name;
        std::array<int, 32> velocityValues;
    };

    struct PlaybackSettings {
        VelocityCurveType velocityCurve = VelocityCurveType::LinearCoarse;
        NoteHandlingMode noteHandlingMode = NoteHandlingMode::LIFO;
        int REPEATED_NOTE_GAP_MS = 15;
        std::vector<CustomVelocityCurve> customVelocityCurves;
        void validate() const;
    };

    class Config {
    public:
        static constexpr std::size_t MAX_CUSTOM_HUMANIZER_PRESETS = 5;

        MIDISettings midi;
        PlaybackSettings playback;
        VolumeSettings volume;
        HumanizerSettings humanizer;
        std::string activeHumanizerPreset = "Custom (Modified)";
        std::vector<HumanizerPreset> customHumanizerPresets;
        AutoTranspose auto_transpose;
        HotkeySettings hotkeys;
        UISettings ui;
        std::map<std::string, std::map<std::string, std::string>> key_mappings;
        std::map<std::string, std::string> controls;
        std::vector<std::string> playlistFiles;

        static Config& getInstance();

        void loadFromFile(const std::filesystem::path& path);
        void saveToFile(const std::filesystem::path& path) const;
        void validate() const;
        void setDefaults();

        // Resolve portable relative paths beside MIDI++.exe rather than against
        // whichever working directory happened to launch the program.
        static std::filesystem::path resolvePath(const std::filesystem::path& path);

        static NoteHandlingMode stringToNoteHandlingMode(const std::string& mode);
        static std::string noteHandlingModeToString(NoteHandlingMode mode);

        Config(const Config&) = delete;
        Config& operator=(const Config&) = delete;

    private:
        Config() = default;
        void validateKeyMappings() const;
    };

    void to_json(nlohmann::json& j, const VolumeSettings& v);
    void from_json(const nlohmann::json& j, VolumeSettings& v);
    void to_json(nlohmann::json& j, const HumanizerSettings& h);
    void from_json(const nlohmann::json& j, HumanizerSettings& h);
    void to_json(nlohmann::json& j, const AutoTranspose& l);
    void from_json(const nlohmann::json& j, AutoTranspose& l);
    void to_json(nlohmann::json& j, const MIDISettings& m);
    void from_json(const nlohmann::json& j, MIDISettings& m);
    void to_json(nlohmann::json& j, const HotkeySettings& h);
    void from_json(const nlohmann::json& j, HotkeySettings& h);
    void to_json(nlohmann::json& j, const PlaybackSettings& p);
    void from_json(const nlohmann::json& j, PlaybackSettings& p);
    void to_json(nlohmann::json& j, const Config& c);
    void from_json(const nlohmann::json& j, Config& c);
    void to_json(nlohmann::json& j, const UISettings& ui);
    void from_json(const nlohmann::json& j, UISettings& ui);

} // namespace midi
