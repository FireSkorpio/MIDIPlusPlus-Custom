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
