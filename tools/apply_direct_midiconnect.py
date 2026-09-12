from pathlib import Path

ROOT = Path("MIDIPlusPlus-1.0.4.R5_Rel")


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: Path, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        if new in text:
            print(f"[skip] {path}: replacement already present")
            return
        raise RuntimeError(f"Expected text not found in {path}:\n{old[:300]}")
    text = text.replace(old, new, 1)
    write(path, text)
    print(f"[ok] {path}")


# -----------------------------------------------------------------------------
# MIDIConnect.hpp: expose the existing Visual Pianos encoder to MIDI++ playback.
# -----------------------------------------------------------------------------
hpp = ROOT / "MIDIConnect.hpp"
replace_once(
    hpp,
    "    void SetActive(bool active);\n    void ReleaseAllNumpadKeys();\n",
    "    void SetActive(bool active);\n"
    "    void ReleaseAllNumpadKeys();\n"
    "    void SendNote(int midiNote, int velocity) noexcept;\n"
    "    void SendSustain(int value) noexcept;\n"
)

text = read(hpp)
footer = """

// Loaded-MIDI playback bridge. When the MIDI++ MidiConnect toggle is active,
// PlaybackCore routes its already-scheduled/humanized MIDI events through the
// same Visual Pianos protocol used by live MIDI input.
bool MidiConnectPlaybackOutputActive() noexcept;
void MidiConnectSendPlaybackNote(int midiNote, int velocity) noexcept;
void MidiConnectSendPlaybackSustain(int value) noexcept;
void MidiConnectReleasePlaybackNotes() noexcept;
"""
if "bool MidiConnectPlaybackOutputActive() noexcept;" not in text:
    text = text.rstrip() + footer + "\n"
    write(hpp, text)
    print(f"[ok] {hpp}: playback bridge declarations")


# -----------------------------------------------------------------------------
# MIDIConnect.cpp: share the encoder between live MIDI and loaded MIDI playback.
# -----------------------------------------------------------------------------
cpp = ROOT / "MIDIConnect.cpp"
replace_once(
    cpp,
    '#include <iostream>\n',
    '#include <iostream>\n#include <mutex>\n'
)

replace_once(
    cpp,
    "namespace {\n    static const uint8_t div12[128] = {",
    "namespace {\n"
    "    std::atomic<MIDIConnect*> g_activeMidiConnect{ nullptr };\n"
    "    std::mutex g_midiConnectStateMutex;\n"
    "    std::array<bool, 128> g_midiConnectNotesDown{};\n\n"
    "    static const uint8_t div12[128] = {"
)

replace_once(
    cpp,
    "MIDIConnect::~MIDIConnect() {\n    CloseDevice();\n}\n",
    "MIDIConnect::~MIDIConnect() {\n"
    "    SetActive(false);\n"
    "    CloseDevice();\n"
    "}\n"
)

old_set_active = """void MIDIConnect::SetActive(bool active) {
    m_isActive.store(active, std::memory_order_release);
    if (active && SyscallNumber == 0) {
        try {
            SyscallNumber = GetNtUserSendInputSyscallNumber();
        }
        catch (const std::exception& e) {
            std::cout << "Failed to load syscall number: " << e.what() << std::endl;
            exit(1);
        }
    }
}
"""
new_set_active = """void MIDIConnect::SetActive(bool active) {
    const bool wasActive = m_isActive.load(std::memory_order_acquire);
    if (!active && wasActive)
        MidiConnectReleasePlaybackNotes();

    m_isActive.store(active, std::memory_order_release);

    if (active) {
        g_activeMidiConnect.store(this, std::memory_order_release);
    }
    else {
        MIDIConnect* expected = this;
        g_activeMidiConnect.compare_exchange_strong(
            expected, nullptr, std::memory_order_acq_rel, std::memory_order_acquire);
    }

    if (active && SyscallNumber == 0) {
        try {
            SyscallNumber = GetNtUserSendInputSyscallNumber();
        }
        catch (const std::exception& e) {
            std::cout << "Failed to load syscall number: " << e.what() << std::endl;
            exit(1);
        }
    }
}
"""
replace_once(cpp, old_set_active, new_set_active)

marker = "void MIDIConnect::ProcessMidiMessage(IMidiMessage const& midiMessage) {\n"
methods = """void MIDIConnect::SendNote(int midiNote, int velocity) noexcept {
    if (!m_isActive.load(std::memory_order_acquire))
        return;
    if (midiNote < 0 || midiNote > 127)
        return;

    velocity = std::clamp(velocity, 0, 127);
    const auto& mapping = m_noteMapping[static_cast<size_t>(midiNote)][static_cast<size_t>(velocity)];
    NtUserSendInputCall(10, const_cast<INPUT*>(mapping.data()), sizeof(INPUT));

    std::lock_guard<std::mutex> lock(g_midiConnectStateMutex);
    g_midiConnectNotesDown[static_cast<size_t>(midiNote)] = (velocity > 0);
}

void MIDIConnect::SendSustain(int value) noexcept {
    if (!m_isActive.load(std::memory_order_acquire))
        return;

    value = std::clamp(value, 0, 127);
    const auto& mapping = m_sustainMapping[static_cast<size_t>(value)];
    NtUserSendInputCall(10, const_cast<INPUT*>(mapping.data()), sizeof(INPUT));
}

"""
text = read(cpp)
if "void MIDIConnect::SendNote(int midiNote, int velocity) noexcept" not in text:
    if marker not in text:
        raise RuntimeError("ProcessMidiMessage marker not found")
    text = text.replace(marker, methods + marker, 1)
    write(cpp, text)
    print(f"[ok] {cpp}: direct send methods")

old_process = """    if (cmd == 0x90 || cmd == 0x80) {
        const BYTE velocity = (cmd == 0x90) ? data2 : 0;
        const auto& mapping = m_noteMapping[data1][velocity];
        NtUserSendInputCall(10, const_cast<INPUT*>(mapping.data()), sizeof(INPUT));
    }
    else if (cmd == 0xB0 && data1 == 64) {
        const auto& mapping = m_sustainMapping[data2];
        NtUserSendInputCall(10, const_cast<INPUT*>(mapping.data()), sizeof(INPUT));
    }
}
"""
new_process = """    if (cmd == 0x90 || cmd == 0x80) {
        const int velocity = (cmd == 0x90) ? data2 : 0;
        SendNote(data1, velocity);
    }
    else if (cmd == 0xB0 && data1 == 64) {
        SendSustain(data2);
    }
}

bool MidiConnectPlaybackOutputActive() noexcept {
    MIDIConnect* output = g_activeMidiConnect.load(std::memory_order_acquire);
    return output && output->IsActive();
}

void MidiConnectSendPlaybackNote(int midiNote, int velocity) noexcept {
    MIDIConnect* output = g_activeMidiConnect.load(std::memory_order_acquire);
    if (output && output->IsActive())
        output->SendNote(midiNote, velocity);
}

void MidiConnectSendPlaybackSustain(int value) noexcept {
    MIDIConnect* output = g_activeMidiConnect.load(std::memory_order_acquire);
    if (output && output->IsActive())
        output->SendSustain(value);
}

void MidiConnectReleasePlaybackNotes() noexcept {
    MIDIConnect* output = g_activeMidiConnect.load(std::memory_order_acquire);
    if (!output || !output->IsActive())
        return;

    std::array<bool, 128> notesToRelease{};
    {
        std::lock_guard<std::mutex> lock(g_midiConnectStateMutex);
        notesToRelease = g_midiConnectNotesDown;
        g_midiConnectNotesDown.fill(false);
    }

    for (int note = 0; note < 128; ++note) {
        if (notesToRelease[static_cast<size_t>(note)])
            output->SendNote(note, 0);
    }
    output->SendSustain(0);
}
"""
replace_once(cpp, old_process, new_process)


# -----------------------------------------------------------------------------
# PlaybackCore.cpp: route scheduled file playback directly to MidiConnect.
# This happens after Humanizer/repeated-note scheduling, preserving those effects.
# -----------------------------------------------------------------------------
playback = ROOT / "PlaybackCore.cpp"
replace_once(
    playback,
    '#include "PlaybackSystem.hpp"\n',
    '#include "PlaybackSystem.hpp"\n#include "MIDIConnect.hpp"\n'
)

old_execute = """void VirtualPianoPlayer::execute_note_event(const NoteEvent& event) noexcept {
    if (!isTrackEnabled(event.trackIndex))
        return;

    if (!event.isSustain) {
"""
new_execute = """void VirtualPianoPlayer::execute_note_event(const NoteEvent& event) noexcept {
    if (!isTrackEnabled(event.trackIndex))
        return;

    // Direct Visual Pianos MidiConnect output. The event has already passed
    // through MIDI parsing, Humanizer 2.0, playability filtering and the
    // repeated-note scheduler, so this only replaces the final QWERTY output.
    if (MidiConnectPlaybackOutputActive()) {
        if (event.isSustain) {
            MidiConnectSendPlaybackSustain(std::clamp(event.sustainValue, 0, 127));
        }
        else {
            const int midiNote = note_name_to_midi(event.note);
            if (midiNote >= 0 && midiNote <= 127) {
                const int velocity = (event.action == EventType::Press)
                    ? std::clamp(event.velocity, 1, 127)
                    : 0;
                MidiConnectSendPlaybackNote(midiNote, velocity);
            }
        }
        return;
    }

    if (!event.isSustain) {
"""
replace_once(playback, old_execute, new_execute)

replace_once(
    playback,
    "void VirtualPianoPlayer::release_all_keys() {\n",
    "void VirtualPianoPlayer::release_all_keys() {\n"
    "    // MidiConnect messages are taps, not held numpad keys, so explicitly\n"
    "    // emit note-off messages for any protocol notes still considered down.\n"
    "    MidiConnectReleasePlaybackNotes();\n"
)


# -----------------------------------------------------------------------------
# UI text: explain that the existing MidiConnect toggle now handles file output.
# -----------------------------------------------------------------------------
ui = ROOT / "MIDI++.cpp"
replace_once(
    ui,
    'AddToolTip(hWnd, ID_BTN_MIDICONNECT, L"Alternate live MIDI input mode using the specialized key injector.");',
    'AddToolTip(hWnd, ID_BTN_MIDICONNECT, L"Send loaded MIDI (and optional live MIDI input) directly through the Visual Pianos MidiConnect protocol.");'
)


# -----------------------------------------------------------------------------
# Notes for the branch.
# -----------------------------------------------------------------------------
notes = Path("UPDATE_NOTES.md")
text = read(notes)
section = """

## Direct MidiConnect playback (Humanizer 2.0 test branch)

- The existing **MidiConnect** toggle can now send loaded MIDI playback directly to Visual Pianos using its four-key base-12 protocol; no external MidiConnect program or virtual MIDI port is required.
- Direct output happens after Humanizer 2.0, playability filtering, repeated-note handling, track mute/solo, speed and seeking, so those scheduler features are preserved.
- Note velocity is sent through the MidiConnect protocol (note-off uses velocity 0), and sustain is sent with the existing control-143 encoding.
- Panic/stop/reset explicitly sends note-off messages for protocol notes still active plus sustain-off to reduce stuck notes.
- Existing physical MIDI input through the MidiConnect button remains available.
"""
if "## Direct MidiConnect playback (Humanizer 2.0 test branch)" not in text:
    write(notes, text.rstrip() + section + "\n")
    print(f"[ok] {notes}")

print("Direct MidiConnect playback patch complete.")
