# Repository update notes

This archive mirrors the GitHub repository layout used during the previous successful cloud build:

```text
.github/workflows/build.yml
MIDIPlusPlus-1.0.4.R5_Rel/
```

The workflow path already points to the nested solution:

```text
MIDIPlusPlus-1.0.4.R5_Rel\MIDI++.sln
```

The project file also already links `RuntimeObject.lib`, the linker change required for the previous GitHub Actions build to succeed.

Use this package to update the existing `MIDIPlusPlus-Custom` repository rather than creating a new repository.
