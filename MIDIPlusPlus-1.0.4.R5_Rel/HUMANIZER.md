# MIDI++ R5 Humanizer modification

This build replaces the unused/incomplete **Legit Mode** configuration with a playback **Humanizer** and keeps the previously tested repeated-note key-up fix.

## Humanizer rules

The humanizer operates on MIDI++'s prepared playback event queue. It does not rewrite the MIDI file.

- A Note On is never moved earlier than its original MIDI timestamp.
- A Note Off is never moved later than its original MIDI timestamp.
- Humanization therefore never makes a note longer than the source MIDI note.
- Sustain events are not humanized.
- Two-note dyads through five-note chords are supported.
- Six-or-more-note simultaneous groups are split into hands when the register makes that clear; a single inferred hand is not forced to simulate more than five fingers.
- Right-hand strike tendency: **thumb -> middle -> pinky -> index -> ring**.
- Left-hand strike tendency: **pinky -> middle -> thumb -> ring -> index**.
- Fewer-note chords use subsets of the five finger positions; wider two-note intervals use wider finger spans.
- Some fingers intentionally share the same press/release timestamp.
- 3-5 note chords are guaranteed to receive at least a small strike stagger when timing allows.
- Chords are guaranteed to receive at least a small release difference when timing allows.
- Sequential articulation releases the outgoing note slightly early before the next gesture from the same inferred hand. The amount is both speed-aware and interval-aware.
- Same-note repetitions are left to `REPEATED_NOTE_GAP_MS`, which runs after the Humanizer and keeps the tested 15 ms key-up gap.

## Tuned defaults

```json
"HUMANIZER_SETTINGS": {
    "ENABLED": true,
    "CHORD_DETECTION_WINDOW_MS": 3,
    "CHORD_PRESS_MAX_SPREAD_MS": 12,
    "CHORD_RELEASE_MAX_SPREAD_MS": 8,
    "SIMULTANEOUS_FINGER_CHANCE_PERCENT": 28,
    "SEQUENTIAL_ARTICULATION": true,
    "SEQUENTIAL_MAX_GAP_MS": 10,
    "RANDOMIZE_EACH_PLAY": false
},
"REPEATED_NOTE_GAP_MS": 15
```

`RANDOMIZE_EACH_PLAY=false` makes the same MIDI timing humanize consistently between runs, which makes testing easier. Set it to `true` if a slightly different micro-performance is desired each time the playback queue is prepared.

## GitHub Actions build

The repository-ready package includes `.github/workflows/build.yml` and preserves the linker fix needed by the GitHub Windows runner:

```text
RuntimeObject.lib
```

The workflow builds `Release|x64` and packages:

```text
MIDI++.exe
config.json
midi/
```

into the `MIDIPlusPlus-R5-Humanizer` Actions artifact.
