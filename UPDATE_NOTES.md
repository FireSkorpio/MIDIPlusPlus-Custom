# MIDI++ Custom Build update

This repository-ready update is based on MIDI++ v1.0.4.R5 and the previously tested repeated-note-gap/Humanizer build.

## Added / changed

- Main window title changed to **MIDI++ Custom Build**.
- Added **Humanizer** button under Advanced.
- Added in-app Humanizer settings popup and Help popup.
- Humanizer exposes chord press/release minimum and maximum spreads.
- Chord onset timing is normalized to a chosen target spread so configured minimums are actually visible when the MIDI has room.
- Chord release timing keeps an original-release anchor while other simulated fingers lift early.
- Sequential articulation applies to ordinary notes as well as chord passages.
- All Humanizer millisecond controls and repeated-note gap accept 0-1000 ms; percent controls remain 0-100.
- Out-of-range Humanizer values are clamped and reversed min/max pairs are normalized.
- Config load errors preserve the original config, create a backup/error file, and use defaults only for that launch.
- Existing repeated-note early-release behavior remains enabled (default 15 ms).
- Existing `RuntimeObject.lib` GitHub linker fix is preserved.

## Humanizer skill presets

- **Professional** - tight, polished timing with subtle variation.
- **Intermediate** - controlled hobby-player timing with clearly visible finger separation.
- **Casual** - looser, visible articulation based on the tested Roblox settings.

The shipped **Casual** preset uses:

- Chord detection window: 50 ms
- Chord press spread: 32-78 ms
- Chord release spread: 25-64 ms
- Simultaneous finger chance: 10%
- Sequential trigger: 200 ms
- Sequential gap: 40-100 ms
- Repeated-note gap remains a separate global setting: 15 ms

## QoL update

- Professional / Intermediate / Casual Humanizer presets.
- Up to five saved custom Humanizer presets with rename/update/delete.
- Automatic MIDI rebuild on preset changes and Apply.
- Repeatable Humanizer performance seeds and New Performance.
- F4 is now **Panic / Release All Notes** instead of closing MIDI++.
- Added a seek bar and **Reload Current MIDI**.
- Added drag-and-drop MIDI loading and a five-item Recent MIDI list.
- MIDI++ remembers opacity and the last MIDI folder.
- Added tooltips and expanded MIDI details.
- Relative config paths now resolve beside `MIDI++.exe`.
- Older configs using `EMERGENCY_EXIT_KEY` migrate to `PANIC_KEY`.
- Build output now includes `HUMANIZER.md` and a starter `midi` folder.
- Virtual MIDI integration is intentionally not included until the separate add-on is tested.


## QoL round 2

- Added Humanizer preset duplication plus JSON preset export/import.
- F4 Panic now has visible two-second feedback in the Playback panel in addition to the log.
- Added always-visible speed and transpose readouts.
- Added Reset Playback: returns to 0:00, speed 1.00x, transpose +0, and clears track mute/solo without changing Humanizer, Velocity, or Sustain mode.
- Added recursive MIDI browser search across the entire `midi` folder and all subfolders.
- Moved Reload out of an overlapping control position and added a dedicated playback status row.


## Humanizer 2.0 branch

- Better hand inference tracks named bass/treble or left/right piano tracks plus recent hand position.
- Optional Playability Optimizer toggle: max 5 simultaneous physical notes per hand, 10 total; sustain-held sounding notes may exceed 10.
- Optional config-only tempo-aware Humanizer, disabled by default.
- Optional config-only melody-priority timing, disabled by default.
- Optional config-only velocity Humanizer with BALANCED, MELODY_FOCUS, and CHORD_FOCUS modes, disabled by default.
- Humanizer 2.0 remains isolated from `main`; `main` receives only the separately validated QoL changes.

## Direct MidiConnect playback (Humanizer 2.0 test branch)

- The existing **MidiConnect** toggle can now send loaded MIDI playback directly to Visual Pianos using its four-key base-12 protocol; no external MidiConnect program or virtual MIDI port is required.
- Direct output happens after Humanizer 2.0, playability filtering, repeated-note handling, track mute/solo, speed and seeking, so those scheduler features are preserved.
- Note velocity is sent through the MidiConnect protocol (note-off uses velocity 0), and sustain is sent with the existing control-143 encoding.
- Panic/stop/reset explicitly sends note-off messages for protocol notes still active plus sustain-off to reduce stuck notes.
- Existing physical MIDI input through the MidiConnect button remains available.

## Startup diagnostics (Humanizer 2.0 test branch)

- MIDI++ now shows a small startup window immediately so a slow launch no longer looks like nothing happened.
- The startup window reports the current stage, including graphics, playback/config initialization, resources, and interface/MIDI-device enumeration.
- Startup exceptions are caught and shown in a message box instead of terminating silently.
- Startup failures are also written to `startup_error.txt` beside `MIDI++.exe` for easy troubleshooting.
- If the single-instance mutex exists but the previous MIDI++ window cannot be found, MIDI++ now explains that another background instance may still be running.

## Startup MIDI isolation / direct MidiConnect test

- Physical MIDI device enumeration no longer runs during `WM_CREATE`; the device list is populated only when **Refresh MIDI** is pressed.
- The built-in **MidiConnect** toggle is now a loaded-MIDI playback output mode and no longer opens a Windows MIDI input endpoint.
- Autoplay controls remain available while MidiConnect output is enabled.
- Velocity-curve and physical-device selection changes no longer reopen MidiConnect as a MIDI input device.

