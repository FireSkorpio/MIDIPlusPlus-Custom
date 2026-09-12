# MIDI++ Custom Build

A customized Windows build of [MIDI++](https://github.com/Zephkek/MIDIPlusPlus) focused on virtual-piano playback, Humanizer improvements, quality-of-life features, and direct MidiConnect playback.

> **Upstream attribution:** This is **not the original MIDI++ project**. The original MIDI++ codebase was created by **Zephkek** and contributors. This repository is a revision/custom build based on MIDI++ v1.0.4 R5 and maintained by **FireSkorpio**. FireSkorpio does not claim authorship of the original MIDI++ codebase. See [NOTICE.md](NOTICE.md) for the attribution notice.

This modified build remains licensed under the GNU GPL v3. See [LICENSE](LICENSE), [NOTICE.md](NOTICE.md), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## What this build adds

- Humanizer presets: Professional, Intermediate, Casual, plus custom presets.
- Humanizer 2.0 hand inference, optional tempo-aware timing, melody priority, and velocity humanization.
- Optional Playability Optimizer with practical per-hand/simultaneous-note limits.
- Repeated-note gap handling for cleaner retriggers.
- Direct loaded-MIDI output to Visual Pianos through the built-in MidiConnect protocol.
- No external MidiConnect program or virtual MIDI-port add-on is required for Visual Pianos playback.
- MIDI browser search, recent files, drag-and-drop loading, reload, seek, speed display, transpose display, panic feedback, and Reset Playback.
- Physical MIDI input remains available through Midi2Key, but physical devices are not scanned during startup.

## Requirements

- Windows 10 or Windows 11, 64-bit.
- An x64 CPU with AVX2 support.
- Roblox/your target virtual piano if you are using the autoplay or MidiConnect features.
- A physical MIDI keyboard is optional and is only needed for live MIDI input features.

MIDI++ is currently a Windows application. Experimental macOS work is kept on the separate `feature/macos-port` branch and is not part of the Windows release.

## Download

The repository's GitHub Actions workflow builds the current `main` branch as a Release x64 package.

1. Open the repository's **Actions** tab.
2. Open **Build MIDI++ Custom Build**.
3. Open the newest successful run.
4. Download the `MIDIPlusPlus-Custom-Build` artifact.
5. Extract the ZIP before launching the program.

Do not run `MIDI++.exe` from inside the ZIP archive.

## Installation

MIDI++ is portable; there is no installer.

Extract the package to a normal folder you can write to, for example:

```text
C:\Users\<you>\Documents\MIDIPlusPlus\
```

Keep these files together:

```text
MIDI++.exe
config.json
HUMANIZER.md
README.md
NOTICE.md
LICENSE
THIRD_PARTY_NOTICES.md
LICENSES\
midi\
```

The `midi` folder is optional. You can also drag `.mid` or `.midi` files directly onto MIDI++.

If Windows SmartScreen warns about the executable, verify that you downloaded or built it from this repository before choosing to run it. The project does not currently ship with a commercial code-signing certificate.

## Basic use

### Standard virtual-piano playback

1. Launch `MIDI++.exe`.
2. Add MIDI files to the `midi` folder, drag a MIDI onto the app, or browse/search from the MIDI list.
3. Load the song.
4. Configure Humanizer, velocity, sustain, tracks, transpose, or Playability as desired.
5. Open/focus the target piano in Roblox.
6. Press **Play/Pause**.

MIDI++ will use its normal QWERTY/keyboard playback path unless MidiConnect output is enabled.

### Visual Pianos: direct MidiConnect playback

For Visual Pianos, you do **not** need the old external MidiConnect program and you do **not** need the experimental virtual MIDI-port add-on.

1. Join/open Visual Pianos in Roblox.
2. Enable the in-game **MidiConnect** toggle.
3. In MIDI++, load the MIDI you want to play.
4. Enable MIDI++'s **MidiConnect** button.
5. Press **Play/Pause**.

The playback scheduler sends the already-processed notes directly through the Visual Pianos MidiConnect protocol. Humanizer timing, Playability filtering, track mute/solo, velocity, sustain, speed, seeking, and repeated-note handling remain in the playback path.

### Physical MIDI keyboard / Midi2Key

Physical MIDI input is optional and separated from loaded-file playback.

1. Connect your MIDI keyboard.
2. Launch MIDI++.
3. Press **Refresh MIDI** to scan for physical MIDI input devices.
4. Select the device and MIDI channel.
5. Enable **Midi2Key** for live MIDI-to-keyboard input.

MIDI++ intentionally does not scan physical MIDI devices during startup, so a slow or broken MIDI driver cannot prevent the main interface from opening.

## Humanizer

Press **Humanizer** under Advanced to select or edit timing presets.

Built-in presets include:

- **Professional** — tight timing with subtle human variation.
- **Intermediate** — more noticeable articulation while remaining controlled.
- **Casual** — looser timing with clearly visible finger separation.

You can save up to five custom presets, duplicate presets, rename/update them, and import/export Humanizer presets as JSON.

Humanizer 2.0 also contains optional advanced settings in `config.json` for tempo-aware timing, melody-priority timing, and velocity humanization. See [HUMANIZER.md](MIDIPlusPlus-1.0.4.R5_Rel/HUMANIZER.md) for details.

## Useful controls

- **Play/Pause** — start or pause loaded MIDI playback.
- **Restart** — restart the song.
- **Skip+10 / Rew-10** — move through the loaded song.
- **Speed++ / Speed--** — adjust playback speed.
- **Reload** — rebuild the currently loaded MIDI using the current settings.
- **Reset Playback** — return to 0:00, speed 1.00x, transpose +0, and clear track mute/solo while preserving Humanizer, Velocity, and Sustain mode.
- **F4** — Panic: release all currently held notes without closing MIDI++.
- **Playability** — optional Humanizer 2.0 optimizer for physically plausible simultaneous attacks.
- **MidiConnect** — send loaded MIDI directly using the Visual Pianos MidiConnect protocol.
- **Refresh MIDI** — scan for physical MIDI devices only when needed.

## Configuration and files

`config.json` lives beside `MIDI++.exe`. MIDI++ resolves its normal relative paths from the executable directory, so keeping the package together is recommended.

Important files:

- `config.json` — playback, Humanizer, UI, mappings, and advanced options.
- `HUMANIZER.md` — Humanizer settings reference.
- `UPDATE_NOTES.md` — development/update history in the source repository.
- `NOTICE.md` — explicit upstream authorship and revision notice.
- `startup_error.txt` — created beside the executable if a caught startup error occurs.

## Troubleshooting

If MIDI++ does not start or behaves unexpectedly:

1. Make sure only one `MIDI++.exe` instance is running.
2. Keep `config.json` beside the executable.
3. Try a clean extracted copy of the newest build.
4. Check `startup_error.txt` if one was created.
5. If a physical MIDI-device refresh hangs, disconnect problem devices/drivers and retry; normal loaded-MIDI playback does not require physical MIDI enumeration.
6. When reporting a bug, include your Windows version, the build/commit you tested, steps to reproduce, relevant log text, and `startup_error.txt` when available.

## Building from source

The current Windows project is a Visual Studio C++/Win32 solution.

Typical Release build:

```powershell
msbuild "MIDIPlusPlus-1.0.4.R5_Rel\MIDI++.sln" /m /p:Configuration=Release /p:Platform=x64
```

The GitHub Actions workflow performs the same Release x64 build automatically.

## macOS support

There is no production macOS build yet. Experimental porting work is isolated on `feature/macos-port`.

The MIDI parser, scheduler, Humanizer, Playability logic, configuration logic, and much of the playback state machine are portable C++, but the Windows application also relies on Win32 UI, GDI+/Common Controls, C++/WinRT MIDI APIs, Windows scan codes, and Windows input injection. The macOS work is replacing those platform-specific layers while reusing the portable playback logic.

## Support / contact

For bugs, installation problems, feature requests, or compatibility reports, open an issue in this repository:

https://github.com/FireSkorpio/MIDIPlusPlus-Custom/issues

Maintainer of this revision: **FireSkorpio** on GitHub.

Please include enough information to reproduce the problem. For crashes or startup failures, attach the relevant log/error text but remove any personal paths or information you do not want to share publicly.

## License and attribution

The original MIDI++ project is by **Zephkek and contributors**. This repository is a modified/revision build and is not presented as original authorship by FireSkorpio.

MIDI++ and this modified build are distributed under the **GNU General Public License version 3**. See [LICENSE](LICENSE).

This repository includes third-party code under compatible licenses. See [NOTICE.md](NOTICE.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and the [LICENSES](LICENSES) directory.

Upstream project: https://github.com/Zephkek/MIDIPlusPlus
