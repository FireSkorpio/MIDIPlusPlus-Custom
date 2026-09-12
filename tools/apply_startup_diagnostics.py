from pathlib import Path

ROOT = Path("MIDIPlusPlus-1.0.4.R5_Rel")
UI = ROOT / "MIDI++.cpp"
NOTES = Path("UPDATE_NOTES.md")


def read(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")


ui = read(UI)
required = [
    "static std::filesystem::path StartupErrorPath()",
    "static HWND CreateStartupSplash(HINSTANCE hInstance)",
    "static void SetStartupStatus(HWND splash, const wchar_t* status) noexcept",
    "static int ReportStartupFailure(HWND splash, const std::string& stage, const std::string& detail) noexcept",
    "Building interface and scanning MIDI devices...",
]

missing = [item for item in required if item not in ui]
if missing:
    raise RuntimeError("Startup diagnostics are missing from MIDI++.cpp: " + ", ".join(missing))

# Guard against accidentally applying the old patch twice. Each helper must
# have exactly one definition in the source.
for item in required[:4]:
    count = ui.count(item)
    if count != 1:
        raise RuntimeError(f"Expected exactly one startup helper '{item}', found {count}")

notes = read(NOTES)
if "## Startup diagnostics (Humanizer 2.0 test branch)" not in notes:
    raise RuntimeError("Startup diagnostics notes are missing from UPDATE_NOTES.md")

print("[ok] Startup diagnostics already present exactly once; no patching required.")
