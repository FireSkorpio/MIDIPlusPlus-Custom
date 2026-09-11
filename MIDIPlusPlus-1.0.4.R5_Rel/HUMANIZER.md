# MIDI++ Custom Build - Humanizer

This build replaces the old/incomplete **Legit Mode** concept with a real playback **Humanizer**, keeps the repeated-note key-up correction, and adds in-app Humanizer and Help popups.

## Core timing rules

The Humanizer modifies MIDI++'s prepared playback queue; it does not rewrite MIDI files.

- A Note On is never moved earlier than the source MIDI timestamp.
- A Note Off is never moved later than the source MIDI timestamp.
- Humanization can shorten a note slightly, but never makes it longer than the source MIDI note.
- Sustain events are left alone.
- Requested timing is automatically constrained when a note is too short to support it.
- All millisecond Humanizer controls accept `0-1000` ms (`1000 ms = 1 second`).
- Percentage controls remain `0-100`.

## Chord / hand behavior

Two-note dyads through five-note one-hand chords are supported.

- Right-hand strike tendency: **thumb -> middle -> pinky -> index -> ring**.
- Left-hand strike tendency: **pinky -> middle -> thumb -> ring -> index**.
- Fewer-note chords remove unused fingers while preserving the hand's strike tendency.
- Wider two-note intervals use wider inferred finger spans.
- Some fingers may intentionally land or lift together.
- Chord presses have a configurable minimum and maximum total spread.
- Chord releases have a separate minimum and maximum spread.
- At least one chord finger can remain until the original MIDI Note Off while other fingers lift earlier.

## Sequential articulation

Humanization also applies to ordinary note-to-note movement, not only chords.

If the next same-hand gesture begins within `SEQUENTIAL_TRIGGER_WINDOW_MS` of the current note's original end, MIDI++ can release the current note early to create a physical key-up gap. The next Note On is never intentionally delayed.

Pitch distance influences the upper end of the gap range: larger jumps can receive more air than small stepwise movement. The configured minimum is treated as the desired floor when the MIDI timing physically allows it.

Same-note repetitions such as `A-A-A` are handled afterward by `REPEATED_NOTE_GAP_MS`, which provides a hard release gap when timing permits.

## Tuned defaults

```json
"HUMANIZER_SETTINGS": {
    "ENABLED": true,
    "CHORD_DETECTION_WINDOW_MS": 3,
    "CHORD_PRESS_MIN_SPREAD_MS": 12,
    "CHORD_PRESS_MAX_SPREAD_MS": 36,
    "CHORD_RELEASE_MIN_SPREAD_MS": 8,
    "CHORD_RELEASE_MAX_SPREAD_MS": 26,
    "SIMULTANEOUS_FINGER_CHANCE_PERCENT": 10,
    "SEQUENTIAL_ARTICULATION": true,
    "SEQUENTIAL_TRIGGER_WINDOW_MS": 200,
    "SEQUENTIAL_MIN_GAP_MS": 8,
    "SEQUENTIAL_MAX_GAP_MS": 20,
    "RANDOMIZE_EACH_PLAY": false
},
"REPEATED_NOTE_GAP_MS": 15
```

These defaults are intentionally more visible on a 60 FPS virtual piano. Users can lower them for subtle performance or raise them—up to 1000 ms—for exaggerated/sloppy timing effects.

## In-app controls

The main window is titled **MIDI++ Custom Build**.

The Advanced section now includes:

- **Humanizer** - opens a popup for changing/saving Humanizer timing without manually editing `config.json`.
- **Help** - opens a read-only quick guide explaining playback, advanced controls, Humanizer settings, timing units, and config safety.

Humanizer popup changes are saved to `config.json`. Reload the current MIDI (or load another song) to rebuild its event queue with the new timing.

## Config safety

If `config.json` is malformed or cannot be loaded, MIDI++ no longer overwrites it automatically.

Instead it:

1. preserves the original as `config.invalid.backup.json`,
2. writes the error to `config_error.txt`, and
3. uses defaults for that launch only.

Humanizer millisecond values are clamped to `0-1000`, percentage values to `0-100`, and reversed min/max pairs are normalized instead of destroying the config.

## GitHub Actions build

The project keeps the `RuntimeObject.lib` linker fix required by the GitHub Windows runner. The workflow builds `Release|x64` and packages `MIDI++.exe` plus `config.json` as an Actions artifact.
