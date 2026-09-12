#include "MIDIDeviceUI.hpp"
#include <mmsystem.h>

bool MIDIDeviceUI::TestDeviceAccess(UINT deviceIndex) {
    HMIDIIN hMidiIn;
    MMRESULT result = midiInOpen(&hMidiIn, deviceIndex, 0, 0, CALLBACK_NULL);
    if (result == MMSYSERR_NOERROR) {
        midiInClose(hMidiIn);
        return true;
    }
    return false;
}

void MIDIDeviceUI::PopulateMidiInDevices(HWND combo, int& selectedDevice) {
    SendMessage(combo, CB_RESETCONTENT, 0, 0);

    // Startup must stay non-blocking. The old implementation called
    // midiInOpen() on every device just to test accessibility. A stale or
    // unresponsive Windows MIDI endpoint can block inside midiInOpen(), which
    // freezes WM_CREATE and leaves MIDI++ stuck on the startup splash.
    //
    // Enumerate device names only here. Actual access is deferred until the
    // user enables Midi2Key/MidiConnect and MIDI++ opens the selected device.
    const UINT numDevs = midiInGetNumDevs();
    int addedCount = 0;

    for (UINT i = 0; i < numDevs; ++i) {
        MIDIINCAPS mic{};
        if (midiInGetDevCaps(i, &mic, sizeof(mic)) == MMSYSERR_NOERROR) {
            SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(mic.szPname));
            ++addedCount;
        }
    }

    if (addedCount > 0) {
        // No filtering is performed, so combo indices remain aligned with the
        // WinMM device indices used by the rest of MIDI++.
        if (selectedDevice < 0 || selectedDevice >= addedCount)
            selectedDevice = 0;
        SendMessage(combo, CB_SETCURSEL, selectedDevice, 0);
    }
    else {
        SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"No Devices"));
        SendMessage(combo, CB_SETCURSEL, 0, 0);
        selectedDevice = -1;
    }
}

void MIDIDeviceUI::PopulateChannelList(HWND combo, int& selectedChannel) {
    SendMessage(combo, CB_RESETCONTENT, 0, 0);
    SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(L"All Channels"));

    for (int ch = 0; ch < 16; ch++) {
        wchar_t buf[32];
        swprintf_s(buf, L"Channel %d", ch);
        SendMessageW(combo, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(buf));
    }

    SendMessage(combo, CB_SETCURSEL, 0, 0);
    selectedChannel = -1;
}

UINT MIDIDeviceUI::GetMidiDeviceCount() {
    return midiInGetNumDevs();
}

bool MIDIDeviceUI::GetMidiDeviceName(UINT deviceIndex, wchar_t* name, UINT nameSize) {
    if (!name || nameSize == 0) return false;

    MIDIINCAPS mic{};
    if (midiInGetDevCaps(deviceIndex, &mic, sizeof(mic)) == MMSYSERR_NOERROR) {
        wcsncpy_s(name, nameSize, mic.szPname, _TRUNCATE);
        return true;
    }
    return false;
}
