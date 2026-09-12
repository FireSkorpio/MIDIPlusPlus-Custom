# Third-Party Notices

This repository is a modified build of MIDI++ and includes or depends on components with their own licensing terms.

## MIDI++ upstream

Upstream project: https://github.com/Zephkek/MIDIPlusPlus

This customized repository is based on MIDI++ v1.0.4 R5. The project is distributed under the GNU General Public License version 3. A complete copy of the GPL v3 is provided in the repository root as `LICENSE` and again under `LICENSES/GPL-3.0.txt`.

Modifications in this repository are marked through Git history, update notes, and the custom-build documentation.

## nlohmann/json 3.11.3

The vendored single-header file `MIDIPlusPlus-1.0.4.R5_Rel/json.hpp` is JSON for Modern C++, version 3.11.3, by Niels Lohmann.

License: MIT

Copyright: 2013-2023 Niels Lohmann

The complete MIT license text is included at `LICENSES/nlohmann-json-MIT.txt`. The vendored header also contains its SPDX copyright and license identifiers.

Project: https://github.com/nlohmann/json

## Microsoft / Windows platform components

MIDI++ uses Microsoft Windows platform APIs and toolchain components, including Win32, Windows multimedia/MIDI APIs, C++/WinRT interfaces, GDI+, Common Controls, and libraries supplied by the Windows SDK / Visual C++ toolchain. These are platform/build dependencies and are governed by Microsoft's applicable license terms; they are not relicensed by this repository's GPL license.

## Assets and upstream documentation

Some documentation and image links retained in `MIDIPlusPlus-1.0.4.R5_Rel/README.md` originate from the upstream MIDI++ project. Rights and attribution remain with their respective original owners/contributors.

## Notes for distributors

If you redistribute binaries of this modified GPL-covered program, make the corresponding source code and GPL license terms available as required by the GPL. Preserve applicable third-party copyright and license notices, including the nlohmann/json MIT notice.

This file is an attribution/notice summary and is not legal advice. The actual license texts control.
