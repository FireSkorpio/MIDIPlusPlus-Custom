"""Compile production optimizer/scheduler methods with a recording output backend.
Run: python3 tests/test_playback_releases.py (requires a C++20 compiler).
Only Windows output/transport scaffolding is replaced; algorithm bodies are read
verbatim so these checks exercise the actual implementation, not a Python copy.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'MIDIPlusPlus-1.0.4.R5_Rel'
source = (SRC / 'PlaybackCore.cpp').read_text()
header = (SRC / 'PlaybackSystem.hpp').read_text()

def function(signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

preamble = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cctype>
#include <iostream>
#include <map>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include "config.hpp"
#include "midi_structures.h"
using namespace std::chrono_literals;
midi::Config& midi::Config::getInstance() { static Config config; return config; }
enum class EventType { Press, Release };
'''
start = header.index('struct alignas(64) NoteEvent {')
end = header.index('\n};', start) + 3
# Constructors are not needed by the recording harness; preserve production fields.
event = header[start:header.index('    NoteEvent() noexcept;', start)] + '};\n'
harness = r'''
class VirtualPianoPlayer {
public:
    MidiFile midi_file;
    std::vector<NoteEvent*> note_buffer;
    std::unordered_map<std::string, std::atomic<bool>> pressed_keys;
    std::map<std::string, std::string> full_key_mappings, limited_key_mappings;
    bool ENABLE_OUT_OF_RANGE_TRANSPOSE = false, eightyEightKeyModeActive = false;
    std::vector<std::pair<std::string, bool>> output;
    void KeyPress(std::string_view key, bool down) { output.emplace_back(key, down); }
    void press_key(std::string_view) noexcept;
    void release_key(std::string_view) noexcept;
    std::string transpose_note(std::string_view);
    int note_name_to_midi(std::string_view);
    std::string get_note_name(int);
    void apply_humanizer();
    void apply_repeated_note_gap();
    void execute_note_event(const NoteEvent& e) {
        if (e.isSustain) return;
        if (e.action == EventType::Press) press_key(e.note);
        else release_key(e.note);
    }
    size_t dispatch(const std::vector<NoteEvent*>& batch);
};
'''
methods = '\n'.join(function(sig) for sig in [
    'void VirtualPianoPlayer::apply_humanizer()',
    'void VirtualPianoPlayer::apply_repeated_note_gap()',
    'void VirtualPianoPlayer::press_key(',
    'void VirtualPianoPlayer::release_key(',
    'std::string VirtualPianoPlayer::transpose_note(',
    'int VirtualPianoPlayer::note_name_to_midi(',
    'std::string VirtualPianoPlayer::get_note_name(',
])
start = source.index('auto fut = processing_pool.enqueue([this, batch = std::move(batch)]() -> size_t {')
start = source.index('{', start) + 1
end = source.index('return batch.size();', start) + len('return batch.size();')
methods += '\nsize_t VirtualPianoPlayer::dispatch(const std::vector<NoteEvent*>& batch) {' + source[start:end] + '\n}\n'
tests = r'''
NoteEvent e(int ms, std::string_view note, EventType action, int track=0, int vel=80) {
    return {std::chrono::milliseconds(ms), note, action, vel, false, 0, track};
}
int main() {
    auto& cfg = midi::Config::getInstance();
    cfg.humanizer.ENABLED = false;
    cfg.playability.ENABLED = true;
    cfg.playback.REPEATED_NOTE_GAP_MS = 0;
    int cases = 0;
    // Real optimizer filtering under both pairing policies, repeated pitch,
    // overlapping notes on separate tracks, and preserved sustained durations.
    for (auto mode : {midi::NoteHandlingMode::FIFO, midi::NoteHandlingMode::LIFO,
                      midi::NoteHandlingMode::NoHandling}) {
        for (int limit : {1, 3, 5}) {
            cfg.playback.noteHandlingMode = mode;
            cfg.playability.MAX_NOTES_PER_HAND = limit;
            cfg.playability.MAX_SIMULTANEOUS_NOTES = limit;
            std::vector<NoteEvent> events;
            for (auto note : {"C4", "D4", "E4", "F4", "G4", "A4"}) {
                events.push_back(e(0, note, EventType::Press));
                events.push_back(e(3, note, EventType::Release));
                events.push_back(e(10, note, EventType::Press));
                events.push_back(e(500, note, EventType::Release));
            }
            events.push_back(e(1, "C4", EventType::Press, 1));
            events.push_back(e(600, "C4", EventType::Release, 1));
            // Same-track overlap also exercises FIFO versus LIFO pairing.
            events.push_back(e(100, "D4", EventType::Press));
            events.push_back(e(650, "D4", EventType::Release));
            std::unordered_map<NoteEvent*, std::chrono::nanoseconds> originalTimes;
            VirtualPianoPlayer p;
            for (auto& ev : events) {
                p.note_buffer.push_back(&ev);
                originalTimes[&ev] = ev.time;
            }
            p.apply_humanizer();
            assert(p.note_buffer.size() < events.size()); // omissions are valid
            for (auto* ev : p.note_buffer) {
                // Optimizer must not change the timestamp of any retained event.
                assert(ev->time == originalTimes.at(ev));
                p.limited_key_mappings[std::string(ev->note)] = std::string(ev->note);
            }
            std::map<std::pair<std::string, int>, int> balances;
            for (auto* ev : p.note_buffer) {
                auto& count = balances[{std::string(ev->note), ev->trackIndex}];
                count += ev->action == EventType::Press ? 1 : -1;
                assert(count >= 0); // no orphaned releases after filtering
            }
            for (auto& [voice, count] : balances) assert(count == 0);
            // Simulate a delayed wake: all events become due in one batch.
            p.dispatch(p.note_buffer);
            for (auto& [note, state] : p.pressed_keys) assert(!state.load());
            ++cases;
        }
    }
    // Single short note: old dispatch sent Off then On and left it down.
    VirtualPianoPlayer p;
    p.limited_key_mappings["C4"] = "a";
    auto on = e(0, "C4", EventType::Press);
    auto off = e(1, "C4", EventType::Release);
    p.dispatch({&on, &off});
    assert((p.output == std::vector<std::pair<std::string,bool>>{{"a",true},{"a",false}}));
    // At equal time, the sorted queue releases the old note before retrigger.
    p.output.clear();
    auto on2 = e(1, "C4", EventType::Press);
    auto off2 = e(2, "C4", EventType::Release);
    p.dispatch({&on, &off, &on2, &off2});
    assert(p.output.size() == 4 && !p.pressed_keys["C4"].load());
    // Folded notes must release the same output/state used on attack.
    for (bool full : {false, true}) {
        VirtualPianoPlayer folded;
        folded.ENABLE_OUT_OF_RANGE_TRANSPOSE = true;
        folded.eightyEightKeyModeActive = full;
        auto actual = folded.transpose_note("C1");
        folded.limited_key_mappings[actual] = "z";
        folded.full_key_mappings[actual] = "z";
        folded.press_key("C1");
        folded.release_key("C1");
        assert(folded.output.size() == 2 && !folded.output.back().second);
        assert(!folded.pressed_keys[actual].load());
    }
    // Repeated-note gap shortens overlapping releases without delaying attack.
    cfg.playback.REPEATED_NOTE_GAP_MS = 10;
    cfg.playback.noteHandlingMode = midi::NoteHandlingMode::FIFO;
    auto a = e(0,"C4",EventType::Press), b = e(50,"C4",EventType::Press);
    auto c = e(100,"C4",EventType::Release), d = e(150,"C4",EventType::Release);
    p.note_buffer = {&a,&b,&c,&d};
    p.apply_repeated_note_gap();
    assert(a.time == 0ns && b.time == 50ms && c.time == 40ms && d.time == 150ms);
    std::cout << "Passed " << cases << " optimizer configurations plus dispatch, retrigger, folding and gap regressions\n";
}
'''
with tempfile.TemporaryDirectory() as tmp:
    cpp = Path(tmp) / 'regression.cpp'
    binary = Path(tmp) / 'regression'
    cpp.write_text(preamble + event + harness + methods + tests)
    subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++20', '-O0', '-g',
                    '-I', str(SRC), str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
