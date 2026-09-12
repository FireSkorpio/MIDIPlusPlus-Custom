from pathlib import Path

ROOT = Path("MIDIPlusPlus-1.0.4.R5_Rel")
UI = ROOT / "MIDI++.cpp"
NOTES = Path("UPDATE_NOTES.md")


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[skip] {label}: already applied")
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one source block, found {count}")
    print(f"[ok] {label}")
    return text.replace(old, new, 1)


ui = read(UI)

required = [
    "static std::filesystem::path StartupErrorPath()",
    "static HWND CreateStartupSplash(HINSTANCE hInstance)",
    "static void SetStartupStatus(HWND splash, const wchar_t* status) noexcept",
    "static int ReportStartupFailure(HWND splash, const std::string& stage, const std::string& detail) noexcept",
]
missing = [item for item in required if item not in ui]
if missing:
    raise RuntimeError("Startup diagnostics are missing from MIDI++.cpp: " + ", ".join(missing))
for item in required:
    count = ui.count(item)
    if count != 1:
        raise RuntimeError(f"Expected exactly one startup helper '{item}', found {count}")

# WM_CREATE contains the first PopulateMidiInDevices call; Refresh MIDI contains
# another. Replace only the first one so startup makes zero WinMM calls while
# the explicit Refresh MIDI button still performs on-demand enumeration.
old_scan = "        MIDIDeviceUI::PopulateMidiInDevices(cbMidiDev, g_selectedMidiDevice);"
new_scan = """        SendMessageW(cbMidiDev, CB_ADDSTRING, 0,
            reinterpret_cast<LPARAM>(L\"Live MIDI: click Refresh\"));
        SendMessage(cbMidiDev, CB_SETCURSEL, 0, 0);
        g_selectedMidiDevice = -1;"""
if new_scan in ui:
    print("[skip] startup physical MIDI enumeration already deferred")
elif old_scan in ui:
    ui = ui.replace(old_scan, new_scan, 1)
    print("[ok] deferred physical MIDI enumeration until Refresh MIDI")
else:
    raise RuntimeError("Could not find startup PopulateMidiInDevices call")

old_midiconnect = """                if (newState) {
                    if (!g_midiConnect)
                        g_midiConnect = std::make_unique<MIDIConnect>();
                    g_midiConnect->SetActive(true);
                    g_midiConnect->OpenDevice(g_selectedMidiDevice);
                    std::cout << \"[MidiConnect] ENABLED\\n\";
                    FocusRobloxWindow();
                    g_midiConnect->ReleaseAllNumpadKeys();
                }
                else {
                    if (g_midiConnect) {
                        g_midiConnect->SetActive(false);
                        g_midiConnect->CloseDevice();
                    }
                    std::cout << \"[MidiConnect] DISABLED\\n\";
                }
                UpdateWindowFocusability();"""
new_midiconnect = """                if (newState) {
                    if (!g_midiConnect)
                        g_midiConnect = std::make_unique<MIDIConnect>();
                    g_midiConnect->SetActive(true);
                    std::cout << \"[MidiConnect] DIRECT PLAYBACK OUTPUT ENABLED\\n\";
                    FocusRobloxWindow();
                    g_midiConnect->ReleaseAllNumpadKeys();
                }
                else {
                    if (g_midiConnect) {
                        g_midiConnect->SetActive(false);
                        g_midiConnect->CloseDevice();
                    }
                    std::cout << \"[MidiConnect] DIRECT PLAYBACK OUTPUT DISABLED\\n\";
                }
                UpdateWindowFocusability();"""
ui = replace_once(ui, old_midiconnect, new_midiconnect, "make MidiConnect a playback-output toggle")

old_conflict = "(g_midi2key && g_midi2key->IsActive()) || (g_midiConnect && g_midiConnect->IsActive())"
if old_conflict in ui:
    n = ui.count(old_conflict)
    ui = ui.replace(old_conflict, "(g_midi2key && g_midi2key->IsActive())")
    print(f"[ok] removed MidiConnect from {n} live-input conflict checks")
else:
    print("[skip] live-input conflict checks already updated")

old_focus = """    if ((g_midiConnect && g_midiConnect->IsActive()) ||
        (g_midi2key && g_midi2key->IsActive()) ||
        (g_player && g_player->midiFileSelected.load(std::memory_order_acquire) && !g_player->paused.load(std::memory_order_relaxed)))"""
new_focus = """    if ((g_midi2key && g_midi2key->IsActive()) ||
        (g_player && g_player->midiFileSelected.load(std::memory_order_acquire) && !g_player->paused.load(std::memory_order_relaxed)))"""
ui = replace_once(ui, old_focus, new_focus, "do not treat direct MidiConnect output as live input for window focus")

old_reopen_velocity = """                if (g_midiConnect && g_midiConnect->IsActive()) {
                    g_midiConnect->CloseDevice();
                    g_midiConnect->OpenDevice(g_selectedMidiDevice);
                }
"""
if old_reopen_velocity in ui:
    ui = ui.replace(old_reopen_velocity, "", 1)
    print("[ok] removed MidiConnect reopen from velocity-curve change")
else:
    print("[skip] velocity-curve MidiConnect reopen already removed")

old_reopen_device = """                if (g_midiConnect && g_midiConnect->IsActive()) {
                    g_midiConnect->CloseDevice();
                    g_midiConnect->OpenDevice(sel);
                }
"""
if old_reopen_device in ui:
    ui = ui.replace(old_reopen_device, "", 1)
    print("[ok] removed MidiConnect reopen from physical-device selection")
else:
    print("[skip] device-selection MidiConnect reopen already removed")

ui = ui.replace(
    'SetStartupStatus(startupSplash, L"Building interface and scanning MIDI devices...");',
    'SetStartupStatus(startupSplash, L"Building interface...");')
ui = ui.replace(
    "// WM_CREATE populates the controls and enumerates MIDI input devices. If\n"
    "    // that step is slow or blocked, the splash remains visible with this exact\n"
    "    // status instead of making MIDI++ appear to do nothing.\n",
    "// WM_CREATE now avoids Windows MIDI enumeration entirely. Physical MIDI\n"
    "    // devices are enumerated only when Refresh MIDI is explicitly requested.\n")

write(UI, ui)

notes = read(NOTES)
section = """

## Startup MIDI isolation / direct MidiConnect test

- Physical MIDI device enumeration no longer runs during `WM_CREATE`; the device list is populated only when **Refresh MIDI** is pressed.
- The built-in **MidiConnect** toggle is now a loaded-MIDI playback output mode and no longer opens a Windows MIDI input endpoint.
- Autoplay controls remain available while MidiConnect output is enabled.
- Velocity-curve and physical-device selection changes no longer reopen MidiConnect as a MIDI input device.
"""
if "## Startup MIDI isolation / direct MidiConnect test" not in notes:
    write(NOTES, notes.rstrip() + section + "\n")
else:
    print("[skip] UPDATE_NOTES section already present")

print("Startup/MidiConnect isolation patch complete.")
