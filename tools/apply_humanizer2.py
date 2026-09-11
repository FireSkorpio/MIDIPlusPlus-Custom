from pathlib import Path
import json

ROOT = Path('MIDIPlusPlus-1.0.4.R5_Rel')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)


def insert_before(text: str, marker: str, addition: str, label: str) -> str:
    count = text.count(marker)
    if count != 1:
        raise RuntimeError(f'{label}: marker count {count}')
    return text.replace(marker, addition + marker, 1)


def insert_after(text: str, marker: str, addition: str, label: str) -> str:
    count = text.count(marker)
    if count != 1:
        raise RuntimeError(f'{label}: marker count {count}')
    return text.replace(marker, marker + addition, 1)

# -----------------------------------------------------------------------------
# config.hpp: advanced Humanizer and Playability configuration
# -----------------------------------------------------------------------------
p = ROOT / 'config.hpp'
text = p.read_text(encoding='utf-8')

advanced_structs = r'''
    // Advanced Humanizer 2.0 behavior is intentionally config-driven. The
    // normal presets remain focused on the familiar timing controls above.
    struct HumanizerAdvancedSettings {
        bool BETTER_HAND_INFERENCE = true;
        bool TEMPO_AWARE_ENABLED = false;
        bool MELODY_PRIORITY_ENABLED = false;
        bool VELOCITY_HUMANIZER_ENABLED = false;
        std::string VELOCITY_HUMANIZER_MODE = "BALANCED"; // BALANCED, MELODY_FOCUS, CHORD_FOCUS
        int VELOCITY_VARIATION = 6; // maximum deterministic +/- variation before contextual bias

        void validate() const;
    };

    struct PlayabilityOptimizerSettings {
        bool ENABLED = false;
        int MAX_SIMULTANEOUS_NOTES = 10; // physical keys, not sustain-held sounding notes
        int MAX_NOTES_PER_HAND = 5;
        int SIMULTANEOUS_WINDOW_MS = 8;

        void validate() const;
    };

'''
text = insert_after(text,
    '    struct HumanizerPreset {\n        std::string name;\n        HumanizerSettings settings;\n    };\n\n',
    advanced_structs,
    'advanced config structs')

text = replace_once(text,
    '        std::vector<HumanizerPreset> customHumanizerPresets;\n        AutoTranspose auto_transpose;\n',
    '        std::vector<HumanizerPreset> customHumanizerPresets;\n        HumanizerAdvancedSettings humanizerAdvanced;\n        PlayabilityOptimizerSettings playability;\n        AutoTranspose auto_transpose;\n',
    'advanced config members')

text = replace_once(text,
    '    void to_json(nlohmann::json& j, const AutoTranspose& l);\n',
    '    void to_json(nlohmann::json& j, const HumanizerAdvancedSettings& h);\n    void from_json(const nlohmann::json& j, HumanizerAdvancedSettings& h);\n    void to_json(nlohmann::json& j, const PlayabilityOptimizerSettings& p);\n    void from_json(const nlohmann::json& j, PlayabilityOptimizerSettings& p);\n    void to_json(nlohmann::json& j, const AutoTranspose& l);\n',
    'advanced json declarations')
p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# ConfigHandler.cpp
# -----------------------------------------------------------------------------
p = ROOT / 'ConfigHandler.cpp'
text = p.read_text(encoding='utf-8')

validators = r'''
    void HumanizerAdvancedSettings::validate() const {
        if (VELOCITY_HUMANIZER_MODE != "BALANCED" &&
            VELOCITY_HUMANIZER_MODE != "MELODY_FOCUS" &&
            VELOCITY_HUMANIZER_MODE != "CHORD_FOCUS") {
            throw ConfigException("VELOCITY_HUMANIZER_MODE must be BALANCED, MELODY_FOCUS, or CHORD_FOCUS");
        }
        if (VELOCITY_VARIATION < 0 || VELOCITY_VARIATION > 24)
            throw ConfigException("VELOCITY_VARIATION must be between 0 and 24");
    }

    void PlayabilityOptimizerSettings::validate() const {
        if (MAX_SIMULTANEOUS_NOTES < 1 || MAX_SIMULTANEOUS_NOTES > 10)
            throw ConfigException("MAX_SIMULTANEOUS_NOTES must be between 1 and 10");
        if (MAX_NOTES_PER_HAND < 1 || MAX_NOTES_PER_HAND > 5)
            throw ConfigException("MAX_NOTES_PER_HAND must be between 1 and 5");
        if (MAX_SIMULTANEOUS_NOTES < MAX_NOTES_PER_HAND)
            throw ConfigException("MAX_SIMULTANEOUS_NOTES cannot be smaller than MAX_NOTES_PER_HAND");
        if (SIMULTANEOUS_WINDOW_MS < 0 || SIMULTANEOUS_WINDOW_MS > 50)
            throw ConfigException("SIMULTANEOUS_WINDOW_MS must be between 0 and 50");
    }

'''
text = insert_before(text, '    void AutoTranspose::validate() const {', validators, 'advanced validators')

text = replace_once(text,
    '            humanizer.validate();\n            if (customHumanizerPresets.size() > MAX_CUSTOM_HUMANIZER_PRESETS)\n',
    '            humanizer.validate();\n            humanizerAdvanced.validate();\n            playability.validate();\n            if (customHumanizerPresets.size() > MAX_CUSTOM_HUMANIZER_PRESETS)\n',
    'config validation calls')

advanced_json = r'''
    void to_json(json& j, const HumanizerAdvancedSettings& h) {
        j = json{
            {"BETTER_HAND_INFERENCE", h.BETTER_HAND_INFERENCE},
            {"TEMPO_AWARE_ENABLED", h.TEMPO_AWARE_ENABLED},
            {"MELODY_PRIORITY_ENABLED", h.MELODY_PRIORITY_ENABLED},
            {"VELOCITY_HUMANIZER_ENABLED", h.VELOCITY_HUMANIZER_ENABLED},
            {"VELOCITY_HUMANIZER_MODE", h.VELOCITY_HUMANIZER_MODE},
            {"VELOCITY_VARIATION", h.VELOCITY_VARIATION}
        };
    }

    void from_json(const json& j, HumanizerAdvancedSettings& h) {
        if (j.contains("BETTER_HAND_INFERENCE")) j.at("BETTER_HAND_INFERENCE").get_to(h.BETTER_HAND_INFERENCE);
        if (j.contains("TEMPO_AWARE_ENABLED")) j.at("TEMPO_AWARE_ENABLED").get_to(h.TEMPO_AWARE_ENABLED);
        if (j.contains("MELODY_PRIORITY_ENABLED")) j.at("MELODY_PRIORITY_ENABLED").get_to(h.MELODY_PRIORITY_ENABLED);
        if (j.contains("VELOCITY_HUMANIZER_ENABLED")) j.at("VELOCITY_HUMANIZER_ENABLED").get_to(h.VELOCITY_HUMANIZER_ENABLED);
        if (j.contains("VELOCITY_HUMANIZER_MODE")) j.at("VELOCITY_HUMANIZER_MODE").get_to(h.VELOCITY_HUMANIZER_MODE);
        if (j.contains("VELOCITY_VARIATION")) j.at("VELOCITY_VARIATION").get_to(h.VELOCITY_VARIATION);
        h.validate();
    }

    void to_json(json& j, const PlayabilityOptimizerSettings& p) {
        j = json{
            {"ENABLED", p.ENABLED},
            {"MAX_SIMULTANEOUS_NOTES", p.MAX_SIMULTANEOUS_NOTES},
            {"MAX_NOTES_PER_HAND", p.MAX_NOTES_PER_HAND},
            {"SIMULTANEOUS_WINDOW_MS", p.SIMULTANEOUS_WINDOW_MS}
        };
    }

    void from_json(const json& j, PlayabilityOptimizerSettings& p) {
        if (j.contains("ENABLED")) j.at("ENABLED").get_to(p.ENABLED);
        if (j.contains("MAX_SIMULTANEOUS_NOTES")) j.at("MAX_SIMULTANEOUS_NOTES").get_to(p.MAX_SIMULTANEOUS_NOTES);
        if (j.contains("MAX_NOTES_PER_HAND")) j.at("MAX_NOTES_PER_HAND").get_to(p.MAX_NOTES_PER_HAND);
        if (j.contains("SIMULTANEOUS_WINDOW_MS")) j.at("SIMULTANEOUS_WINDOW_MS").get_to(p.SIMULTANEOUS_WINDOW_MS);
        p.validate();
    }

'''
text = insert_before(text, '    void to_json(json& j, const AutoTranspose& at) {', advanced_json, 'advanced json functions')

text = replace_once(text,
    '            {"HUMANIZER_SETTINGS", c.humanizer},\n            {"HUMANIZER_ACTIVE_PRESET", c.activeHumanizerPreset},\n',
    '            {"HUMANIZER_SETTINGS", c.humanizer},\n            {"HUMANIZER_ADVANCED", c.humanizerAdvanced},\n            {"PLAYABILITY_OPTIMIZER", c.playability},\n            {"HUMANIZER_ACTIVE_PRESET", c.activeHumanizerPreset},\n',
    'serialize advanced config')

text = replace_once(text,
    '        c.activeHumanizerPreset = "Custom (Modified)";\n',
    '        if (j.contains("HUMANIZER_ADVANCED"))\n            j.at("HUMANIZER_ADVANCED").get_to(c.humanizerAdvanced);\n        if (j.contains("PLAYABILITY_OPTIMIZER"))\n            j.at("PLAYABILITY_OPTIMIZER").get_to(c.playability);\n\n        c.activeHumanizerPreset = "Custom (Modified)";\n',
    'deserialize advanced config')

text = replace_once(text,
    '        activeHumanizerPreset = "Casual";\n        customHumanizerPresets.clear();\n\n        // AutoTranspose settings\n',
    '        activeHumanizerPreset = "Casual";\n        customHumanizerPresets.clear();\n        humanizerAdvanced = HumanizerAdvancedSettings{};\n        playability = PlayabilityOptimizerSettings{};\n\n        // AutoTranspose settings\n',
    'advanced defaults')
p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# PlaybackCore.cpp - Humanizer 2.0 engine
# -----------------------------------------------------------------------------
p = ROOT / 'PlaybackCore.cpp'
text = p.read_text(encoding='utf-8')
text = replace_once(text, '#include <filesystem>\n', '#include <filesystem>\n#include <unordered_set>\n#include <cctype>\n', 'H2 includes')

text = replace_once(text,
    '''void VirtualPianoPlayer::apply_humanizer() {
    const auto& settings = midi::Config::getInstance().humanizer;
    if (!settings.ENABLED)
        return;

    using ns = std::chrono::nanoseconds;
''',
    '''void VirtualPianoPlayer::apply_humanizer() {
    const auto& cfg = midi::Config::getInstance();
    const auto& settings = cfg.humanizer;
    const auto& advanced = cfg.humanizerAdvanced;
    const auto& optimizer = cfg.playability;
    const bool humanizerEnabled = settings.ENABLED;
    if (!humanizerEnabled && !optimizer.ENABLED)
        return;

    using ns = std::chrono::nanoseconds;
''',
    'H2 apply header')

text = replace_once(text,
    '''        int trackIndex = -1;
        Hand hand = Hand::Right;
    };
''',
    '''        int trackIndex = -1;
        Hand hand = Hand::Right;
        bool dropped = false;
    };
''',
    'logical note dropped flag')

# Tempo timeline and deterministic timing scale after millisToNs helper.
tempo_code = r'''
    // Build a tempo timeline in real time so optional tempo-aware timing can
    // tighten fast passages and relax slower passages without changing the
    // user's stored preset values.
    std::vector<std::pair<ns, double>> tempoTimeline;
    tempoTimeline.push_back({ ns::zero(), 120.0 });
    if (advanced.TEMPO_AWARE_ENABLED && midi_file.division != 0 && (midi_file.division & 0x8000) == 0) {
        auto changes = midi_file.tempoChanges;
        std::sort(changes.begin(), changes.end(), [](const TempoChange& a, const TempoChange& b) { return a.tick < b.tick; });
        uint32_t currentTick = 0;
        uint32_t currentTempo = 500000; // 120 BPM
        ns currentTime = ns::zero();
        tempoTimeline.clear();
        tempoTimeline.push_back({ currentTime, 120.0 });
        for (const auto& change : changes) {
            if (change.tick < currentTick || change.microsecondsPerQuarter == 0)
                continue;
            const uint64_t deltaTicks = static_cast<uint64_t>(change.tick - currentTick);
            const long double deltaMicros = static_cast<long double>(deltaTicks) *
                static_cast<long double>(currentTempo) / static_cast<long double>(midi_file.division);
            currentTime += std::chrono::duration_cast<ns>(std::chrono::duration<long double, std::micro>(deltaMicros));
            currentTick = change.tick;
            currentTempo = change.microsecondsPerQuarter;
            const double bpm = 60000000.0 / static_cast<double>(currentTempo);
            tempoTimeline.push_back({ currentTime, bpm });
        }
    }

    auto timingScaleAt = [&](ns when) noexcept -> double {
        if (!advanced.TEMPO_AWARE_ENABLED || tempoTimeline.empty())
            return 1.0;
        double bpm = tempoTimeline.front().second;
        for (const auto& point : tempoTimeline) {
            if (point.first > when)
                break;
            bpm = point.second;
        }
        if (bpm <= 70.0)
            return 1.15;
        if (bpm < 120.0)
            return 1.0 + ((120.0 - bpm) / 50.0) * 0.15;
        return std::clamp(120.0 / std::max(120.0, bpm), 0.55, 1.0);
    };

'''
text = insert_after(text,
    '''    auto millisToNs = [](double ms) noexcept -> ns {
        if (ms <= 0.0)
            return ns(0);
        return ns(static_cast<ns::rep>(ms * 1000000.0 + 0.5));
    };

''',
    tempo_code,
    'tempo timeline')

# Replace track assignment block with track-name hints.
old_track_assign = '''    for (auto& n : notes) {
        const int median = trackMedian[n.trackIndex];
        if (median <= 55)          // G3 or below: strongly left-hand track
            n.hand = Hand::Left;
        else if (median >= 65)     // F4 or above: strongly right-hand track
            n.hand = Hand::Right;
        else
            n.hand = (n.pitch < 60) ? Hand::Left : Hand::Right; // C4 fallback
    }
'''
new_track_assign = r'''    // Explicit piano-track naming is the strongest clue when present. Many
    // piano MIDIs label their two staves/tracks as left/bass and right/treble.
    // When names are absent, register and continuity remain the fallback.
    std::unordered_map<int, int> trackHandHint; // -1 left, +1 right, 0 unknown
    auto lowerText = [](std::string value) {
        std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        return value;
    };
    for (const auto& [track, median] : trackMedian) {
        std::string name;
        if (track >= 0 && static_cast<size_t>(track) < midi_file.tracks.size())
            name = lowerText(midi_file.tracks[static_cast<size_t>(track)].name);
        int hint = 0;
        const bool leftNamed = name.find("left hand") != std::string::npos || name == "lh" ||
            name.find("bass clef") != std::string::npos || name.find("bass staff") != std::string::npos ||
            name.find("lower staff") != std::string::npos || name.find("left") != std::string::npos;
        const bool rightNamed = name.find("right hand") != std::string::npos || name == "rh" ||
            name.find("treble clef") != std::string::npos || name.find("treble staff") != std::string::npos ||
            name.find("upper staff") != std::string::npos || name.find("right") != std::string::npos;
        if (leftNamed && !rightNamed) hint = -1;
        else if (rightNamed && !leftNamed) hint = 1;
        else if (name == "bass" && median <= 60) hint = -1;
        else if (name == "treble" && median >= 60) hint = 1;
        trackHandHint[track] = hint;
    }

    for (auto& n : notes) {
        const int median = trackMedian[n.trackIndex];
        const int hint = advanced.BETTER_HAND_INFERENCE ? trackHandHint[n.trackIndex] : 0;
        if (hint < 0)
            n.hand = Hand::Left;
        else if (hint > 0)
            n.hand = Hand::Right;
        else if (median <= 55)
            n.hand = Hand::Left;
        else if (median >= 65)
            n.hand = Hand::Right;
        else
            n.hand = (n.pitch < 60) ? Hand::Left : Hand::Right;
    }
'''
text = replace_once(text, old_track_assign, new_track_assign, 'track hand hints')

# Strong track checks inside group refinement now recognize explicit names too.
text = replace_once(text,
    '''        for (size_t idx : byPitch) {
            const int median = trackMedian[notes[idx].trackIndex];
            hasStrongLeftTrack |= (median <= 55);
            hasStrongRightTrack |= (median >= 65);
        }
''',
    '''        for (size_t idx : byPitch) {
            const int track = notes[idx].trackIndex;
            const int median = trackMedian[track];
            const int hint = advanced.BETTER_HAND_INFERENCE ? trackHandHint[track] : 0;
            hasStrongLeftTrack |= (hint < 0) || (median <= 55);
            hasStrongRightTrack |= (hint > 0) || (median >= 65);
        }
''',
    'strong track hint refinement')

# Persistent hand-position tracking, melody candidates, and playability optimizer.
analysis_insert = r'''
    if (advanced.BETTER_HAND_INFERENCE) {
        // Track where each hand has recently been instead of re-splitting every
        // ambiguous note around middle C. This allows both hands to travel into
        // either staff/register while still favoring physically nearby motion.
        double leftCenter = 48.0;   // C3
        double rightCenter = 67.0;  // G4
        for (const auto& group : onsetGroups) {
            for (size_t idx : group) {
                if (trackHandHint[notes[idx].trackIndex] != 0)
                    continue;
                const double pitch = static_cast<double>(notes[idx].pitch);
                double leftCost = std::abs(pitch - leftCenter);
                double rightCost = std::abs(pitch - rightCenter);
                if (pitch > rightCenter + 7.0) leftCost += 8.0;
                if (pitch < leftCenter - 7.0) rightCost += 8.0;
                notes[idx].hand = leftCost <= rightCost ? Hand::Left : Hand::Right;
            }

            auto collectHand = [&](Hand hand) {
                std::vector<size_t> out;
                for (size_t idx : group)
                    if (notes[idx].hand == hand) out.push_back(idx);
                return out;
            };
            auto left = collectHand(Hand::Left);
            auto right = collectHand(Hand::Right);

            // Rebalance an otherwise playable <=10-note gesture so one hand is
            // not assigned six notes while the other hand still has fingers free.
            while (left.size() > 5 && right.size() < 5) {
                auto it = std::max_element(left.begin(), left.end(), [&](size_t a, size_t b) { return notes[a].pitch < notes[b].pitch; });
                notes[*it].hand = Hand::Right;
                right.push_back(*it);
                left.erase(it);
            }
            while (right.size() > 5 && left.size() < 5) {
                auto it = std::min_element(right.begin(), right.end(), [&](size_t a, size_t b) { return notes[a].pitch < notes[b].pitch; });
                notes[*it].hand = Hand::Left;
                left.push_back(*it);
                right.erase(it);
            }

            if (!left.empty()) {
                double average = 0.0;
                for (size_t idx : left) average += notes[idx].pitch;
                average /= static_cast<double>(left.size());
                leftCenter = leftCenter * 0.60 + average * 0.40;
            }
            if (!right.empty()) {
                double average = 0.0;
                for (size_t idx : right) average += notes[idx].pitch;
                average /= static_cast<double>(right.size());
                rightCenter = rightCenter * 0.60 + average * 0.40;
            }
        }
    }

    // Identify a likely melodic voice for optional melody-priority timing and
    // for the optimizer's importance scoring. Right-hand continuity is favored,
    // but the highest global voice remains a fallback.
    std::unordered_set<NoteEvent*> melodyPresses;
    std::unordered_map<NoteEvent*, size_t> onsetSize;
    int previousMelodyPitch = -1;
    for (const auto& group : onsetGroups) {
        for (size_t idx : group)
            onsetSize[notes[idx].press] = group.size();
        if (group.empty())
            continue;
        size_t best = group.front();
        double bestScore = -1e9;
        for (size_t idx : group) {
            const auto& n = notes[idx];
            double score = static_cast<double>(n.pitch) * 1.5 + static_cast<double>(n.press->velocity) * 0.05;
            if (n.hand == Hand::Right) score += 18.0;
            if (previousMelodyPitch >= 0) score -= std::abs(n.pitch - previousMelodyPitch) * 0.75;
            if (score > bestScore) {
                bestScore = score;
                best = idx;
            }
        }
        melodyPresses.insert(notes[best].press);
        previousMelodyPitch = notes[best].pitch;
    }

    size_t optimizerDroppedCount = 0;
    if (optimizer.ENABLED) {
        const ns optimizerWindow = std::chrono::milliseconds(optimizer.SIMULTANEOUS_WINDOW_MS);
        auto importance = [&](size_t idx, int lowPitch, int highPitch) {
            const auto& n = notes[idx];
            double score = static_cast<double>(n.press->velocity);
            if (melodyPresses.count(n.press)) score += 500.0;
            if (n.pitch == lowPitch) score += 350.0;   // bass anchor
            if (n.pitch == highPitch) score += 300.0; // top voice
            score += (n.hand == Hand::Left ? (127 - n.pitch) : n.pitch) * 0.12;
            return score;
        };

        for (size_t i = 0; i < notes.size();) {
            const ns start = notes[i].originalPress;
            std::vector<size_t> group;
            size_t j = i;
            while (j < notes.size() && notes[j].originalPress - start <= optimizerWindow) {
                group.push_back(j);
                ++j;
            }
            int lowPitch = 127, highPitch = 0;
            for (size_t idx : group) {
                lowPitch = std::min(lowPitch, notes[idx].pitch);
                highPitch = std::max(highPitch, notes[idx].pitch);
            }

            auto trimHand = [&](Hand hand) {
                std::vector<size_t> candidates;
                for (size_t idx : group)
                    if (!notes[idx].dropped && notes[idx].hand == hand) candidates.push_back(idx);
                if (candidates.size() <= static_cast<size_t>(optimizer.MAX_NOTES_PER_HAND))
                    return;
                std::stable_sort(candidates.begin(), candidates.end(), [&](size_t a, size_t b) {
                    return importance(a, lowPitch, highPitch) > importance(b, lowPitch, highPitch);
                });
                for (size_t k = static_cast<size_t>(optimizer.MAX_NOTES_PER_HAND); k < candidates.size(); ++k) {
                    notes[candidates[k]].dropped = true;
                    ++optimizerDroppedCount;
                }
            };
            trimHand(Hand::Left);
            trimHand(Hand::Right);

            std::vector<size_t> kept;
            for (size_t idx : group)
                if (!notes[idx].dropped) kept.push_back(idx);
            if (kept.size() > static_cast<size_t>(optimizer.MAX_SIMULTANEOUS_NOTES)) {
                std::stable_sort(kept.begin(), kept.end(), [&](size_t a, size_t b) {
                    return importance(a, lowPitch, highPitch) > importance(b, lowPitch, highPitch);
                });
                for (size_t k = static_cast<size_t>(optimizer.MAX_SIMULTANEOUS_NOTES); k < kept.size(); ++k) {
                    notes[kept[k]].dropped = true;
                    ++optimizerDroppedCount;
                }
            }
            i = j;
        }
        if (optimizerDroppedCount > 0)
            std::cout << "[Playability] Simplified " << optimizerDroppedCount << " simultaneous note(s) to respect 5 fingers per hand / 10 total.\n";
    }

'''
text = insert_before(text,
    '    // Convert each onset group into at most one gesture per hand.  A gesture\n',
    analysis_insert,
    'H2 hand tracking and optimizer')

# Skip optimizer-dropped notes when constructing hand gestures.
text = replace_once(text,
    '''        for (size_t idx : group) {
            if (notes[idx].hand == Hand::Left)
                left.members.push_back(idx);
            else
                right.members.push_back(idx);
        }
''',
    '''        for (size_t idx : group) {
            if (notes[idx].dropped)
                continue;
            if (notes[idx].hand == Hand::Left)
                left.members.push_back(idx);
            else
                right.members.push_back(idx);
        }
''',
    'skip dropped hand group notes')

# Tempo-aware scaling on chord press and release ranges.
text = replace_once(text,
    '''            double minPressSpreadMs = static_cast<double>(settings.CHORD_PRESS_MIN_SPREAD_MS);
            double maxPressSpreadMs = settings.CHORD_PRESS_MAX_SPREAD_MS * countScale;
''',
    '''            const double tempoScale = timingScaleAt(group.originalStart);
            double minPressSpreadMs = static_cast<double>(settings.CHORD_PRESS_MIN_SPREAD_MS) * tempoScale;
            double maxPressSpreadMs = settings.CHORD_PRESS_MAX_SPREAD_MS * countScale * tempoScale;
''',
    'tempo-aware press scale')
text = replace_once(text,
    '''            double minReleaseSpreadMs = static_cast<double>(settings.CHORD_RELEASE_MIN_SPREAD_MS);
            double maxReleaseSpreadMs = settings.CHORD_RELEASE_MAX_SPREAD_MS * countScale;
''',
    '''            double minReleaseSpreadMs = static_cast<double>(settings.CHORD_RELEASE_MIN_SPREAD_MS) * tempoScale;
            double maxReleaseSpreadMs = settings.CHORD_RELEASE_MAX_SPREAD_MS * countScale * tempoScale;
''',
    'tempo-aware release scale')

# Melody priority keeps the likely melody Note On on source timing.
text = replace_once(text,
    '''                LogicalNote& n = notes[fingered[hit].noteIndex];
                const ns candidate = group.originalStart + millisToNs(offsetMs);
                ns newPress = std::max(n.originalPress, candidate);
''',
    '''                LogicalNote& n = notes[fingered[hit].noteIndex];
                if (advanced.MELODY_PRIORITY_ENABLED && melodyPresses.count(n.press)) {
                    n.press->time = n.originalPress;
                    continue;
                }
                const ns candidate = group.originalStart + millisToNs(offsetMs);
                ns newPress = std::max(n.originalPress, candidate);
''',
    'melody timing priority')

# Only run timing humanization when master Humanizer is enabled.
text = replace_once(text,
    '''    humanizeHandGroups(leftGroups, Hand::Left);
    humanizeHandGroups(rightGroups, Hand::Right);

    if (settings.SEQUENTIAL_ARTICULATION &&
''',
    '''    if (humanizerEnabled) {
        humanizeHandGroups(leftGroups, Hand::Left);
        humanizeHandGroups(rightGroups, Hand::Right);
    }

    if (humanizerEnabled && settings.SEQUENTIAL_ARTICULATION &&
''',
    'master timing guard')

# Tempo-aware sequential gap scale.
text = replace_once(text,
    '''                    double minGapMs = static_cast<double>(settings.SEQUENTIAL_MIN_GAP_MS);
                    double maxGapMs = static_cast<double>(settings.SEQUENTIAL_MAX_GAP_MS);
''',
    '''                    const double sequentialScale = timingScaleAt(current.originalStart);
                    double minGapMs = static_cast<double>(settings.SEQUENTIAL_MIN_GAP_MS) * sequentialScale;
                    double maxGapMs = static_cast<double>(settings.SEQUENTIAL_MAX_GAP_MS) * sequentialScale;
''',
    'tempo-aware sequential scale')

# Velocity humanizer and dropped-event removal before the final sort.
final_transforms = r'''
    if (humanizerEnabled && advanced.VELOCITY_HUMANIZER_ENABLED) {
        for (auto& n : notes) {
            if (n.dropped || !n.press)
                continue;
            uint64_t seed = static_cast<uint64_t>(n.originalPress.count());
            seed ^= static_cast<uint64_t>((n.pitch + 11) * 811 + (n.trackIndex + 13) * 313);
            const double randomUnit = unitRandom(seed ^ 0x56454cULL);
            int delta = static_cast<int>(std::llround((randomUnit * 2.0 - 1.0) * advanced.VELOCITY_VARIATION));
            const bool melody = melodyPresses.count(n.press) != 0;
            const bool chordMember = onsetSize[n.press] > 1;

            if (advanced.VELOCITY_HUMANIZER_MODE == "MELODY_FOCUS") {
                if (melody) delta += 8;
                else if (chordMember) delta -= 3;
            }
            else if (advanced.VELOCITY_HUMANIZER_MODE == "CHORD_FOCUS") {
                if (chordMember) delta += 4;
                if (melody) delta += 1;
            }
            else { // BALANCED
                if (melody) delta += 3;
                else if (chordMember) delta -= 1;
            }
            n.press->velocity = std::clamp(n.press->velocity + delta, 1, 127);
        }
    }

    if (optimizerDroppedCount > 0) {
        std::unordered_set<NoteEvent*> droppedEvents;
        for (const auto& n : notes) {
            if (n.dropped) {
                droppedEvents.insert(n.press);
                droppedEvents.insert(n.release);
            }
        }
        note_buffer.erase(std::remove_if(note_buffer.begin(), note_buffer.end(), [&](NoteEvent* event) {
            return droppedEvents.count(event) != 0;
        }), note_buffer.end());
    }

'''
text = insert_before(text,
    '    // Humanization may have moved both Note On and Note Off timestamps.\n',
    final_transforms,
    'velocity humanizer and optimizer removal')

p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# MIDI++.cpp - only visible H2 control is Playability Optimizer
# -----------------------------------------------------------------------------
p = ROOT / 'MIDI++.cpp'
text = p.read_text(encoding='utf-8')
text = replace_once(text, '    static const int WIN_H = 835;\n', '    static const int WIN_H = 865;\n', 'H2 window height')
text = replace_once(text, '    static const int PADV_H = 100;\n', '    static const int PADV_H = 130;\n', 'H2 advanced height')
text = replace_once(text,
    '    ID_BTN_HUMANIZER,\n    ID_BTN_HELP,\n',
    '    ID_BTN_HUMANIZER,\n    ID_BTN_PLAYABILITY,\n    ID_BTN_HELP,\n',
    'playability control ID')
text = replace_once(text,
    '    case ID_BTN_TRANSPOSEOUT:\n    case ID_BTN_MIDI2QWERTY:\n',
    '    case ID_BTN_TRANSPOSEOUT:\n    case ID_BTN_PLAYABILITY:\n    case ID_BTN_MIDI2QWERTY:\n',
    'playability togglable')

play_button = r'''        CreateWindowW(L"button", L"Playability",
            WS_CHILD | WS_VISIBLE | BS_OWNERDRAW,
            Layout::PADV_X + 15, Layout::PADV_Y + 96, 95, 27,
            hWnd, reinterpret_cast<HMENU>(ID_BTN_PLAYABILITY), g_hInst, nullptr);
        CreateWindowW(L"static", L"Optional: max 5 notes/hand, 10 total per simultaneous attack",
            WS_CHILD | WS_VISIBLE,
            Layout::PADV_X + 120, Layout::PADV_Y + 101, 430, 20,
            hWnd, nullptr, g_hInst, nullptr);

'''
text = insert_before(text, '        // Config Group\n', play_button, 'playability UI')

text = replace_once(text,
    '        std::vector<int> toggles = { ID_BTN_88KEY, ID_BTN_VOLADJ, ID_BTN_VELOCITY, ID_BTN_SUSTAIN, ID_BTN_TRANSPOSEOUT, ID_BTN_MIDI2QWERTY };\n',
    '        std::vector<int> toggles = { ID_BTN_88KEY, ID_BTN_VOLADJ, ID_BTN_VELOCITY, ID_BTN_SUSTAIN, ID_BTN_TRANSPOSEOUT, ID_BTN_PLAYABILITY, ID_BTN_MIDI2QWERTY };\n',
    'playability toggle init')
text = replace_once(text,
    '        if (g_player && g_player->eightyEightKeyModeActive)\n            g_toggleStates[ID_BTN_88KEY] = true;\n',
    '        if (g_player && g_player->eightyEightKeyModeActive)\n            g_toggleStates[ID_BTN_88KEY] = true;\n        g_toggleStates[ID_BTN_PLAYABILITY] = midi::Config::getInstance().playability.ENABLED;\n',
    'playability initial state')

text = replace_once(text,
    '        AddToolTip(hWnd, ID_BTN_TRANSPOSEOUT, L"Transpose notes that would otherwise fall outside the selected keyboard range.");\n',
    '        AddToolTip(hWnd, ID_BTN_TRANSPOSEOUT, L"Transpose notes that would otherwise fall outside the selected keyboard range.");\n        AddToolTip(hWnd, ID_BTN_PLAYABILITY, L"Optional virtual-piano optimizer. Limits simultaneous physical attacks to 5 notes per hand and 10 total while preserving bass, top voice, velocity, and likely melody importance.");\n',
    'playability tooltip')

playability_case = r'''        case ID_BTN_PLAYABILITY:
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

'''
text = insert_before(text, '        case ID_BTN_HELP:\n', playability_case, 'playability command')

# Details show whether optimizer and config-only H2 options are active.
text = replace_once(text,
    '    lastLine += (filterDrums ? " (Ch10 Filter: On)" : " (Ch10 Filter: Off)");\n',
    '    lastLine += (filterDrums ? " (Ch10 Filter: On)" : " (Ch10 Filter: Off)");\n    lastLine += (midi::Config::getInstance().playability.ENABLED ? " (Optimizer: On)" : " (Optimizer: Off)");\n',
    'H2 details status')

# Help explains advanced config-only features.
text = replace_once(text,
    '    L"If a requested timing value is impossible for a very short note, MIDI++ uses as much as physically fits.\\r\\n\\r\\n"\n',
    '    L"If a requested timing value is impossible for a very short note, MIDI++ uses as much as physically fits.\\r\\n\\r\\n"\n    L"HUMANIZER 2.0 ADVANCED CONFIG\\r\\n"\n    L"Better hand inference is enabled by default and tracks left/right staff clues plus recent hand position.\\r\\n"\n    L"Tempo-aware timing, melody-priority timing, and velocity humanization are config-only and disabled by default.\\r\\n"\n    L"Velocity Humanizer modes: BALANCED, MELODY_FOCUS, CHORD_FOCUS.\\r\\n"\n    L"Playability is the visible optional toggle; it limits simultaneous physical attacks, not sustain-held sounding notes.\\r\\n\\r\\n"\n',
    'H2 help text')

p.write_text(text, encoding='utf-8')

# -----------------------------------------------------------------------------
# config.json defaults for the new branch. Advanced effects intentionally off.
# -----------------------------------------------------------------------------
p = ROOT / 'config.json'
data = json.loads(p.read_text(encoding='utf-8'))
data['HUMANIZER_ADVANCED'] = {
    'BETTER_HAND_INFERENCE': True,
    'TEMPO_AWARE_ENABLED': False,
    'MELODY_PRIORITY_ENABLED': False,
    'VELOCITY_HUMANIZER_ENABLED': False,
    'VELOCITY_HUMANIZER_MODE': 'BALANCED',
    'VELOCITY_VARIATION': 6,
}
data['PLAYABILITY_OPTIMIZER'] = {
    'ENABLED': False,
    'MAX_SIMULTANEOUS_NOTES': 10,
    'MAX_NOTES_PER_HAND': 5,
    'SIMULTANEOUS_WINDOW_MS': 8,
}
p.write_text(json.dumps(data, indent=4) + '\n', encoding='utf-8')

# -----------------------------------------------------------------------------
# Docs
# -----------------------------------------------------------------------------
p = ROOT / 'HUMANIZER.md'
text = p.read_text(encoding='utf-8')
h2 = r'''

## Humanizer 2.0 experimental branch

Humanizer 2.0 adds a more persistent two-hand model. Track names such as left/right hand or bass/treble staff are treated as strong hints; otherwise MIDI++ follows register, chord shape, and each hand's recent position. This allows a hand to travel across middle C instead of treating C4 as a permanent split.

Advanced features live in `HUMANIZER_ADVANCED` and are intentionally conservative by default:

- `BETTER_HAND_INFERENCE` defaults to `true`.
- `TEMPO_AWARE_ENABLED` defaults to `false`. When enabled, stored preset values are left unchanged, but actual timing is tightened at fast tempos and slightly relaxed at slow tempos.
- `MELODY_PRIORITY_ENABLED` defaults to `false`. When enabled, a likely melodic voice stays on the source Note On while supporting chord tones receive Humanizer spread.
- `VELOCITY_HUMANIZER_ENABLED` defaults to `false`. Modes are `BALANCED`, `MELODY_FOCUS`, and `CHORD_FOCUS`; source velocity dynamics are preserved and only small contextual changes are added.

`PLAYABILITY_OPTIMIZER` is separate and also defaults off. The UI exposes it as **Playability**. When enabled it limits one simultaneous physical attack to at most 5 notes per inferred hand and 10 total, preferring bass, top voice, likely melody, and stronger source notes. Sustain-held notes are not counted as fingers still pressing keys, so more than 10 notes may continue sounding under pedal.
'''
if '## Humanizer 2.0 experimental branch' not in text:
    text += h2
p.write_text(text, encoding='utf-8')

p = Path('UPDATE_NOTES.md')
text = p.read_text(encoding='utf-8')
notes = r'''

## Humanizer 2.0 branch

- Better hand inference tracks named bass/treble or left/right piano tracks plus recent hand position.
- Optional Playability Optimizer toggle: max 5 simultaneous physical notes per hand, 10 total; sustain-held sounding notes may exceed 10.
- Optional config-only tempo-aware Humanizer, disabled by default.
- Optional config-only melody-priority timing, disabled by default.
- Optional config-only velocity Humanizer with BALANCED, MELODY_FOCUS, and CHORD_FOCUS modes, disabled by default.
- Humanizer 2.0 remains isolated from `main`; `main` receives only the separately validated QoL changes.
'''
if '## Humanizer 2.0 branch' not in text:
    text += notes
p.write_text(text, encoding='utf-8')

print('Humanizer 2.0 patch applied successfully.')
