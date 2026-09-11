# MIDI++ Custom Build update

This repository-ready update is based on MIDI++ v1.0.4.R5 and the previously tested repeated-note-gap/Humanizer build.

## Added / changed

- Main window title changed to **MIDI++ Custom Build**.
- Added **Humanizer** button under Advanced.
- Added in-app Humanizer settings popup with Apply & Save, Defaults, and Close.
- Added **Help** popup with getting-started, controls, Humanizer, timing, and config-safety documentation.
- Humanizer now exposes chord press/release minimum and maximum spreads.
- Chord onset timing is normalized to a chosen target spread so configured minimums are actually visible when the MIDI has room.
- Chord release timing keeps an original-release anchor while other simulated fingers lift early.
- Sequential articulation now applies to ordinary notes as well as chord passages.
- Added configurable `SEQUENTIAL_TRIGGER_WINDOW_MS` (default 200 ms).
- Added sequential min/max gaps (default 8-20 ms).
- All Humanizer millisecond controls and repeated-note gap accept 0-1000 ms.
- Percent controls remain 0-100.
- Out-of-range Humanizer values are clamped and reversed min/max pairs are normalized.
- Config load errors no longer overwrite `config.json`; a backup and error file are created and defaults are used only for that launch.
- Existing repeated-note early-release behavior remains enabled (default 15 ms).
- Existing `RuntimeObject.lib` GitHub linker fix is preserved.

## Tuned defaults

- Chord press spread: 12-36 ms
- Chord release spread: 8-26 ms
- Simultaneous finger chance: 10%
- Sequential trigger: 200 ms
- Sequential gap: 8-20 ms
- Repeated-note gap: 15 ms
