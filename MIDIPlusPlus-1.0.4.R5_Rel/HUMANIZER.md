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


## Humanizer 2.0 experimental branch

Humanizer 2.0 adds a more persistent two-hand model. Track names such as left/right hand or bass/treble staff are treated as strong hints; otherwise MIDI++ follows register, chord shape, and each hand's recent position. This allows a hand to travel across middle C instead of treating C4 as a permanent split.

Advanced features live in `HUMANIZER_ADVANCED` and are intentionally conservative by default:

- `BETTER_HAND_INFERENCE` defaults to `true`.
- `TEMPO_AWARE_ENABLED` defaults to `false`. When enabled, stored preset values are left unchanged, but actual timing is tightened at fast tempos and slightly relaxed at slow tempos.
- `MELODY_PRIORITY_ENABLED` defaults to `false`. When enabled, a likely melodic voice stays on the source Note On while supporting chord tones receive Humanizer spread.
- `VELOCITY_HUMANIZER_ENABLED` defaults to `false`. Modes are `BALANCED`, `MELODY_FOCUS`, and `CHORD_FOCUS`; source velocity dynamics are preserved and only small contextual changes are added.

`PLAYABILITY_OPTIMIZER` is separate and also defaults off. The UI exposes it as **Playability**. When enabled it limits one simultaneous physical attack to at most 5 notes per inferred hand and 10 total, preferring bass, top voice, likely melody, and stronger source notes. Sustain-held notes are not counted as fingers still pressing keys, so more than 10 notes may continue sounding under pedal.
