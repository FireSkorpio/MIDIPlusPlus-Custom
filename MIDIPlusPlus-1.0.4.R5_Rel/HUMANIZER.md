# MIDI++ Custom Build - Humanizer

The Humanizer modifies MIDI++'s prepared playback queue; it does not rewrite MIDI files.

## Core timing rules

- A Note On is never moved earlier than the source MIDI timestamp.
- A Note Off is never moved later than the source MIDI timestamp.
- Humanization can shorten a note slightly, but never makes it longer than the source MIDI note.
- Sustain events are left alone.
- Requested timing is constrained when a note is too short to support it.
- Millisecond controls accept `0-1000` ms and percentages accept `0-100`.
- Repeated-note protection runs after Humanizer timing.

## Skill presets

- **Professional** - tight, polished timing with subtle natural variation.
- **Intermediate** - controlled hobby-player timing with clearly visible finger separation.
- **Casual** - looser, visible articulation based on the tested Roblox settings.

Casual uses chord detection `50 ms`, press spread `32-78 ms`, release spread `25-64 ms`, sequential gap `40-100 ms`, trigger window `200 ms`, and `10%` simultaneous-finger chance. Exact values remain editable.

## Custom presets

Up to **5** custom presets can be stored in `config.json`. Use **Save As**, **Update/Rename**, or **Delete** in the Humanizer window. Built-ins cannot be overwritten or deleted.

## Automatic rebuild

Selecting a preset immediately saves it and rebuilds the currently loaded MIDI. Manual edits rebuild when **Apply** is pressed. Playback is left paused at the beginning after a rebuild.

## Repeatable performances

When **Different timing each play** is off, `PERFORMANCE_SEED` makes the Humanizer repeatable. **New Performance** creates another repeatable timing pass and rebuilds the MIDI.

## F4 Panic

F4 is **Panic / Release All Notes**. It pauses playback, releases held keys/sustain, and keeps MIDI++ open.

## Config safety

Malformed configs are preserved as `config.invalid.backup.json`, the error is written to `config_error.txt`, and relative config paths resolve beside `MIDI++.exe`.
