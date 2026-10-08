<div align="center">

# xemu-libretro

***An Original Xbox Core for RetroArch, Built from xemu***

[![Version](https://img.shields.io/github/v/tag/EEkebin/xemu-libretro?color=blue&style=for-the-badge)](https://github.com/EEkebin/xemu-libretro/tags)
[![Status](https://img.shields.io/badge/Status-Experimental-orange?style=for-the-badge)](#current-status)

| Social | Donate |
|:---:|:---:|
| [![Discord](https://img.shields.io/static/v1?color=blue&label=Discord&logo=Discord&logoColor=white&style=for-the-badge&message=eekebin)](https://discord.com/users/668262984463810590) | [![PayPal](https://img.shields.io/static/v1?color=blue&label=PayPal&logo=PayPal&style=for-the-badge&message=kebinImports)](https://paypal.me/kebinImports)<br>[![CashApp](https://img.shields.io/static/v1?color=blue&label=CashApp&logo=CashApp&logoColor=green&style=for-the-badge&message=kebinImports)](https://cash.app/$kebinImports) |

</div>

---

xemu-libretro brings [xemu's](https://xemu.app/) original Xbox emulation into
RetroArch. Load the core, provide the required Xbox files, and open your game
through RetroArch. RetroArch handles controller input, video, and audio; the
emulator runs inside the core. A standalone xemu installation is not required.

> **Experimental:** Windows x64 and Linux x86-64 builds have booted Fuzion Frenzy.
> Downloadable core binaries are not published yet; build from source using the
> instructions below. **Restart RetroArch between game sessions.**

## **Table of Contents**

- [Requirements](#requirements)
- [Installation](#installation)
- [Troubleshooting](#troubleshooting)
- [Features](#features)
- [Current Status](#current-status)
- [Building](#building)
- [Updates](#updates)
- [Development](#development)
- [Credits](#credits)
- [Licenses](#licenses)
- [Disclaimers](#disclaimers)

## **Requirements**

- **Windows x64 or Linux x86-64**, with a matching RetroArch installation.
- An **OpenGL 4.0-capable driver**, even if RetroArch uses another video driver.
- Your Xbox **MCPX ROM**, compatible **BIOS**, and writable **HDD image**.
- An Xbox-compatible game image with the **`.iso`** extension.

The core can generate an EEPROM if one is not supplied. Automatic HDD creation
is not implemented yet. See [xemu's required files](https://xemu.app/docs/required-files/)
and [disc image guidance](https://xemu.app/docs/disc-images/) for the supported formats.

## **Installation**

### 1. Build the Core

Follow [Building](#building) for your platform. The native build produces:

| Platform | Core file |
| --- | --- |
| Windows x64 | `build/native-dist/windows-x64/xemu_libretro.dll` |
| Linux x86-64 | `build/native-dist/xemu_libretro.so` |

Windows runs the compiled DLL directly. WSL and Podman are only needed to build it.

### 2. Add the Core to RetroArch

1. Open **Settings > Directory** in RetroArch and check **Cores** and **Core Info**.
2. Copy the matching `.dll` or `.so` into the **Cores** folder shown there.
3. Copy `native/xemu_libretro.info` into the **Core Info** folder.
4. Fully exit and reopen RetroArch so it can pick up the new core information.

### 3. Tell RetroArch Where Your Files Are

> **Loading the core does not configure the Xbox file locations.** Putting
> everything beside the DLL, or in a folder on your Desktop, is not enough:
> RetroArch's directory settings must point to the folders you actually use.

Before loading a game, open **Settings > Directory** and choose explicit paths:

| Setting | Folder to select | Windows example |
| --- | --- | --- |
| **System/BIOS** | Parent folder containing `xemu/bios.bin` and `xemu/mcpx_1.0.bin` | `C:\RetroArch-Win64\system` |
| **Save Files** | Parent folder containing `xemu/xbox_hdd.qcow2` | `C:\RetroArch-Win64\saves` |
| **File Browser / Start Directory** | Your game folder; optional, makes browsing easier | `C:\RetroArch-Win64\games` |

These are **examples**, not required installation paths. On Linux, or with a
Desktop test folder, choose your own folders in the same settings. Create any
folders that do not exist yet, then select them in RetroArch's directory browser.
See RetroArch's [directory guide](https://docs.libretro.com/guides/change-directories/).

**Select the parent `system` and `saves` folders, not their `xemu` subfolders.**
The core adds `xemu` itself. Selecting `saves/xemu` would make it look inside
`saves/xemu/xemu` instead. Use **Save Files**, not **Save States**, for the HDD.

For this layout, open **Settings > Saving** and turn these settings **OFF**:

- **Sort Saves into Folders by Core Name**
- **Sort Saves into Folders by Content Directory**
- **Write Saves to Content Directory**
- **System Files are in Content Directory**

If a setting is hidden, enable **Settings > User Interface > Show Advanced
Settings**. These settings determine which paths RetroArch passes to the core;
sorting can add another folder even when the base Save Files path is correct.
Changing them can also change where your other cores look for files, so keep
track of your existing setup if you use RetroArch for other systems.

Choose **Main Menu > Configuration File > Save Current Configuration**, then
fully exit and reopen RetroArch before continuing.

### 4. Put Each File in the Right Folder

For the Windows example above, the completed layout is:

```text
C:\RetroArch-Win64\
├── cores\
│   └── xemu_libretro.dll
├── info\
│   └── xemu_libretro.info
├── system\
│   └── xemu\
│       ├── mcpx_1.0.bin
│       └── bios.bin
├── saves\
│   └── xemu\
│       ├── xbox_hdd.qcow2
│       └── eeprom.bin             (optional; generated if absent)
└── games\
    └── Fuzion Frenzy (USA).xiso.iso
```

| File | What it is | How it is used |
| --- | --- | --- |
| `xemu_libretro.dll` / `xemu_libretro.so` | The emulator core | Select with **Load Core**. |
| `mcpx_1.0.bin` | 512-byte Xbox MCPX boot ROM | Read automatically from `system/xemu`. |
| `bios.bin` | A compatible Xbox BIOS, renamed to this exact filename | Read automatically from `system/xemu`. |
| `xbox_hdd.qcow2` | A working Xbox hard-drive image | Opened automatically from `saves/xemu`; must be writable. |
| `eeprom.bin` | 256-byte Xbox EEPROM | Used from `saves/xemu`, or generated there if absent. |
| Your game's `.iso` | The game disc image | Select with **Load Content**. |

**The HDD is not the game.** Do not select `xbox_hdd.qcow2` or `bios.bin` as
content, and do not create an empty file with those names. Supply valid Xbox
files as described in [Requirements](#requirements).

The `games` folder is simply a folder **you create** for your disc images.
Games can live elsewhere; browse to their actual location when loading content.
Fuzion Frenzy is the tested example, not a bundled game. Extract an archive
before selecting the compatible `.iso` inside it; renaming an archive to `.iso`
does not convert it.

Use copies of your HDD and EEPROM. Xbox save data can be written into the HDD
image, so retain that same working copy between sessions and back it up.
Do not open the same writable disk in multiple emulator instances.

### 5. Load the Core, Then the Game

1. Choose **Main Menu > Load Core > Xbox (xemu experimental native)**. If the
   menu shows filenames instead, select `xemu_libretro.dll` on Windows or
   `xemu_libretro.so` on Linux.
2. Check that RetroArch displays **xemu (experimental native)** and the core
   version. This confirms the core loaded; it does not yet verify the Xbox files.
3. Choose **Main Menu > Load Content**, browse to your game folder, and select
   the actual `.iso` file. For the example above, select
   `C:\RetroArch-Win64\games\Fuzion Frenzy (USA).xiso.iso`.
4. If asked which core to use, choose **Current Core** or the xemu core.
   RetroArch should now start the Xbox and game. A library scan or playlist is
   not required; see RetroArch's [game-loading guide](https://docs.libretro.com/guides/starting-a-game/).
5. Use your controller through RetroArch's input configuration. If the game is
   running behind the Quick Menu, choose **Resume** to return to it.

**Fully exit and reopen RetroArch before loading another game.** The current
core supports one Xbox machine session per process; **Close Content** alone
does not reset it. Save states, rewind, and runahead are unsupported, even if
RetroArch still displays those menu entries. Use the game's own save system.

## **Troubleshooting**

### "Missing or invalid xemu asset" / "Failed to load content"

Read the **full filename in the first message**. The generic "Failed to load
content" notification may partly cover it. The path identifies the exact file
and directory the core checked.

For example:

```text
Missing or invalid xemu asset:
C:\RetroArch-Win64\saves\xemu\xbox_hdd.qcow2
```

This means the core could not find a usable HDD at **that location**. A copy
on your Desktop will not be used unless **Save Files** points to its parent
save folder.

1. Check **Settings > Directory > Save Files** and the sorting settings in
   [step 3](#3-tell-retroarch-where-your-files-are).
2. Either copy your working HDD to the displayed location, or correct the
   Save Files setting to use the copy you intended. Keep its EEPROM with it.
3. For `mcpx_1.0.bin` or `bios.bin` errors, check **System/BIOS** instead. Check
   the exact filenames, file sizes, and that the files have been extracted.
4. Retry **Load Content** after fixing a missing-file error. That check happens
   before the Xbox starts. If machine initialization already began or the core
   asks you to restart, fully exit RetroArch first.

### Other Common Questions

| What you see | What to do |
| --- | --- |
| No `games` folder | Create one and put your game `.iso` inside, or browse to wherever you already keep it. The core does not create or download games. |
| The file browser opens somewhere unexpected | Browse to the game's actual folder. Set **Settings > Directory > File Browser / Start Directory** to make it easier next time. |
| The error names a different folder than the one you prepared | Check the active directory settings and any core/game overrides that change them. |
| The error contains an extra `xemu` or core-name folder | Select the parent folder and disable save sorting as shown in step 3. The core appends `xemu` to the directory RetroArch supplies. |
| The core only appears as a filename | Check that `xemu_libretro.info` is in the configured **Core Info** folder, then restart RetroArch. |
| "One Xbox machine per process" | Fully exit and reopen RetroArch. Unloading and reloading the core is not enough. |
| You see a diagnostic screen instead of Xbox emulation | Install the native artifact from `build/native-dist/`. The root CMake project builds a separate diagnostic core. |
| Graphics initialization fails | Check that the GPU driver supports OpenGL 4.0. The core requires it even when RetroArch presents through another video driver. |

For an unresolved problem, [open an issue](https://github.com/EEkebin/xemu-libretro/issues)
with your OS, RetroArch/core versions, game name, the exact error, and a
[RetroArch log](https://docs.libretro.com/guides/generating-retroarch-logs/).
Do not attach firmware, games, or HDD/EEPROM images.

## **Features**

| Feature | Details |
| --- | --- |
| Xbox emulation | xemu runs inside the libretro core. |
| Video and audio | Game output goes through RetroArch's frontend interfaces. |
| Controllers | Four RetroPad ports map to Xbox controls, including analog sticks and trigger pressure. |
| EEPROM | Generated automatically when no `eeprom.bin` is supplied. |
| Desktop builds | Native Windows x64 DLL and Linux x86-64 shared library. |

## **Current Status**

Windows and Linux builds have booted **Fuzion Frenzy** and reached player
selection through libretro input. The visible Windows RetroArch build has also
been tested with smooth audio. Broad game compatibility has not been verified.

The current limitations are:

- **One game session per RetroArch process.** Restart RetroArch between sessions.
- **Save states, rewind, runahead, netplay, cheats, and fast-forward** are unsupported.
- Presentation is fixed at **60 Hz / 4:3**. Frame pacing and pause behavior are
  approximate; PAL timing and widescreen negotiation need work.
- Physical controller and rumble coverage, plus full minigame gameplay, need more testing.
- Other platforms, including **PS3**, are not implemented. Running RetroArch on
  a device does not automatically make this core compatible with it.

See [the native core guide](docs/NATIVE.md) for validation details and technical limits.

## **Building**

Clone the repository:

```sh
git clone https://github.com/EEkebin/xemu-libretro.git
cd xemu-libretro
```

Both native builds fetch the xemu revision recorded in `upstream.json`, apply
the integration patch, and compile the core. The first build needs network
access to fetch the toolchain or dependencies.

### Windows x64

Install Git, Windows x64 Python, Ubuntu WSL, and Podman inside Ubuntu. From
PowerShell in the project folder:

```powershell
.\scripts\build_windows.ps1 -Test -Synthetic
```

### Linux x86-64

Install the dependencies listed in [the native build guide](docs/NATIVE.md), then run:

```sh
python3 scripts/build_native.py --build-dir "$HOME/xemu-libretro-build" --test
```

Add `--synthetic` to exercise machine startup with generated test firmware.
These tests check the integration; they do not establish game compatibility.

> **Developer note:** The root CMake project and `scripts/build.py` build a
> separate diagnostic core that does not emulate an Xbox. Use the native build
> above for playing games. See [DIAGNOSTIC.md](docs/DIAGNOSTIC.md).

## **Updates**

Versions use **calendar versioning**: `2026.10.08`, with the Git tag `v2026.10.08`.
Additional releases on the same day append a sequence, such as `2026.10.08.1`.
The `VERSION` file supplies the version reported by both core builds.

An xemu update does not automatically change this core. Each upstream upgrade
needs patch integration, new builds, and testing before a core update is
published. Updating standalone xemu has no effect on an installed core.

To update your core, fully exit RetroArch and replace its core file with the new
build for your platform. Keep your Xbox files separate and back up writable
HDD/EEPROM data before testing an upgrade. The maintainer workflow is in
[UPDATING.md](docs/UPDATING.md).

## **Development**

| Location | Contents |
| --- | --- |
| `native/ui/` | libretro integration and input/audio helpers |
| `patches/xemu-libretro.patch` | Changes to the pinned xemu source |
| `upstream.json` | xemu and libretro header revisions |
| `tests/` | Callback, input/audio, lifecycle, and synthetic boot checks |
| [NATIVE.md](docs/NATIVE.md) | Build instructions, architecture, and validation |
| [PORTING.md](docs/PORTING.md) | Initial source review and porting plan |

## **Credits**

> **[EEkebin](https://github.com/EEkebin)**

This project builds on the work of:

- **[xemu contributors](https://github.com/xemu-project/xemu)** — original Xbox emulation.
- **[QEMU contributors](https://www.qemu.org/)** — the underlying emulation framework.
- **[libretro / RetroArch contributors](https://www.libretro.com/)** — the core interface and frontend.

Additional attribution is recorded in [NOTICE.md](NOTICE.md).

## **Licenses**

> The native core incorporates GPL-licensed xemu/QEMU. See [LICENSE](LICENSE)
> and [NOTICE.md](NOTICE.md) for component licensing and attribution.

The diagnostic foundation and marked helpers retain their
[MIT license](LICENSES/MIT.txt). Upstream dependencies retain their respective licenses.

## **Disclaimers**

> xemu-libretro is an independent project, not an official xemu, libretro,
> or Microsoft release.

> Xbox firmware, games, and disk images are not included.
