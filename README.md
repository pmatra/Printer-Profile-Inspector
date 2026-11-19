# ICC Profile Inspector

[![Windows regression checks](https://github.com/pmatra/Printer-Profile-Inspector/actions/workflows/checks.yml/badge.svg)](https://github.com/pmatra/Printer-Profile-Inspector/actions/workflows/checks.yml)

[Download the latest Windows release](https://github.com/pmatra/Printer-Profile-Inspector/releases/latest)

Windows/macOS ICC printer-profile inspection, organization, and interactive D50 CIELAB gamut comparison. Extract the complete Windows ZIP and run **ICC Gamut Inspector.exe**. Keep `_internal` beside it. Python is not required for the packaged app.

## macOS preview

The macOS port uses CPU rendering, native settings/profile locations, user-level installation, Trash, system appearance and single-instance protection. Separate Apple Silicon and Intel app ZIPs are built by [macOS Actions](https://github.com/pmatra/Printer-Profile-Inspector/actions/workflows/macos.yml). See [MACOS.md](MACOS.md) for build/download instructions and the non-notarized preview limitations. Windows release downloads above remain separate.

## Settings and single-instance operation

The normal application permits one instance per Windows user across desktop sessions, including launches from different release folders. A second launch brings the existing window forward; open another profile within that window.

Preferences live at **`%APPDATA%\PrinterProfileICCInspector\settings.json`**. Saves use a same-directory temporary file, flush/fsync, and atomic replacement. `settings.json.bak` retains the previous known-good state. Malformed settings are preserved as `settings.corrupt-*.json`; recovery or a fallback to defaults is explicitly reported.

For the first upgrade from v0.4.0 or earlier, put the old portable `settings.json` beside the new executable before launching. It is imported only if AppData settings do not already exist. The original is preserved. Subsequent upgrades require no preference copying.

**⚙ → Theme** offers Windows Light, Windows Dark, and Follow Windows. Controls use the Windows system font, shaded buttons with soft drop shadows, and bold shaded category headers. Raw hexadecimal bytes retain a monospace font.

## Profile List

The initial folder is the Windows color directory, normally `C:\Windows\System32\spool\drivers\color`. Open Directory chooses another folder; the default checkbox saves it. Columns show filename, ICC version, device color space, ICC creation date, and status. Heading sorts survive refresh, folding, category moves, and restart. Arrows show direction; invalid/unspecified creation dates sort last in either direction. Folder scans read only ICC headers on a worker; full tag parsing occurs when opening an Inspector profile.

**Search** matches list attributes and category names. Clear Search restores all entries. **Check** selects/unselects matching profiles, including matching children inside collapsed groups. Clear checks also clears hidden checks. The checked count includes checked profiles hidden by Search.

- Check profiles and use **Create category from checked…**. With no checks, this creates an empty category.
- Drag a filename onto a category heading or one of its children. Dragging a checked profile moves all checked profiles together; the target highlights and Escape cancels.
- Click a category name to rename inline. Enter saves, Escape cancels; F2, Rename category, and the context menu also work.
- Arrows expand/collapse categories. Membership and expansion state are saved per directory.
- Right-click a category and choose **Remove category… (keep profile files)**. Its profiles return to Uncategorized after confirmation. No ICC files are moved or deleted.
- Missing saved memberships are retained and reported in the list and category headers. Filename matching is exact, so names differing only by case stay distinct. Renamed individual files require reassignment; the warning makes this visible. **Recover categories…** copies a saved old folder location’s assignments into the current folder after a folder rename/move, preserving the old mappings and all files. It does not infer identity from profile contents.
- Right-click a categorized profile and choose Move to Uncategorized to remove only its assignment.

### Recycle Bin

Right-click a profile and select **Move profile to Recycle Bin…**. A filename/path-specific Yes/No confirmation defaults to No. The app uses the Windows Recycle Bin, rejects non-fixed/network/removable drives, and reports permission/recycling errors without falling back to permanent deletion. Restored files may need to be categorized again.

### Install Profile

**Install Profile…** validates an ICC/ICM file, then uses Windows `InstallColorProfileW` to install/copy it into the system color directory. A dedicated helper requests administrator approval if required. A different existing file with the same filename is not overwritten. The operation does not change printer defaults or device associations. The list opens the Windows color folder on success.

## Inspector, tags, and rendering

Double-click a profile or use Open profile. The ICC tags view has human-readable tag names, **Decoded tag** and **Raw bytes** tabs, and actual curve graphs.

Decoders cover descriptions (`text`, `desc`, `mluc`), XYZ white/black points and colorants, adaptation matrices (`sf32`), sampled/gamma and parametric tone curves (`curv`, `para`), and LUTs (`mft1`, `mft2`, `mAB`, `mBA`). LUT details include channel counts, grids, precision, matrices, input/output curves, and initial normalized CLUT values. Long curves are graphed using up to 1,024 displayed points. Unsupported encodings are clearly identified; raw previews retain up to 16 KiB. This is not a conformance validator.

**High GPU** uses hardware OpenGL, smooth colors, depth testing, and up to twice the viewport width/height for cleaner edges, capped at 4,096 pixels per dimension. Actual GPU and resolution are shown. Unsupported hardware falls back to Basic CPU with a reason.

**X-ray comparison** is enabled by default so a smaller cyan comparison wireframe remains visible inside an opaque primary. Turning it off restores normal GPU comparison occlusion; the primary always retains depth testing. The legend names both files and the active mode. Basic CPU uses a wireframe overlay.

Drag to orbit, scroll to zoom, and use Reset view to restore the camera. CPU Points uses at most 4,000 representative samples (1,500 during orbit); GPU Points uses at most 30,000. Display decimation does not affect the complete sampled data, hull, or CSV export. Draw requests are coalesced and render data cached.

Directory scans, profile parsing, ICC sampling/hull construction, volume/intersection calculation and CSV writing run on workers; Tk widgets/rendering stay on the UI thread. **Cancel work** invalidates pending results and cooperatively stops scans/sampling/export. Transforms are processed in batches with progress updates. A native file read, transform build or hull call already running cannot be forcibly interrupted; cancellation is checked around it and its results are not published. Obsolete jobs are ignored. The default grid is 17/channel, with up to 21 available. CMYK has N⁴ samples. Export saves both the primary and active comparison: full Lab values, device values, zero-based grid coordinates/sample indices, density, device space, intent, role, profile path and profile SHA-256. Device columns are R/G/B, C/M/Y/K, or gray in channel order, encoded 0–255; unused columns are blank. CSV writes are atomic and cancellable.

The viewport caveat is always visible in CPU and GPU modes. Quantities are explicitly **sampled convex-hull estimates** in Lab³: primary/comparison volume, intersection volume, and comparison/primary volume ratio. Intersection solves the convex polyhedra, not the actual non-convex printer gamuts. No concave/alpha-shape mode is implemented. Gray/degenerate sets have no 3D volume.

### Color limitations

Pillow/LittleCMS transforms RGB, CMYK, and gray profiles to D50 Lab where supported. Surfaces are finite **sampled convex hulls**, which can fill concavities and miss narrow features. An 8-bit Lab intermediate is used. CMYK has no independent total-ink constraint. Display colors use sRGB and may clip; the plot is not a calibrated soft proof. Higher rendering resolution improves presentation, not colorimetric accuracy. No exact printer-gamut volume/overlap claim is made. Convex-hull estimates can overstate real gamut and overlap.

## Version and Windows distribution

**⚙ → About** displays the application version. `python inspector.py --version` prints it without opening the GUI; the packaged executable also supports `--version` with an inherited output handle/parent console. Windows file properties include FileVersion/ProductVersion generated from `version.py`.

The Windows executable is unsigned. Windows SmartScreen may show an unrecognized-app warning, and security products may flag a PyInstaller build. Checksums verify file integrity; they do not establish publisher identity or replace code signing. A manual trusted-signing workflow is prepared; follow [SIGNING.md](SIGNING.md) to configure an approved Azure signing identity. The current downloadable executable remains unsigned until a verified signed artifact is published. Do not bypass a warning for a download you cannot verify.

## Development

Tested runtime: Python 3.12 on Windows. GUI tests need a graphical desktop; GPU tests need hardware OpenGL. Installation/deletion regression tests mock OS operations rather than changing installed profiles.

| Source | Purpose |
| --- | --- |
| `inspector.py` | UI, ICC parsing, background sampling, CPU renderer, export |
| `app_support.py` | Atomic platform preferences, Windows mutex/macOS file lock, native install/Trash/theme services |
| `ui_style.py` | Windows system typography and shaded button surfaces |
| `icc_tags.py` | Bounded ICC tag/curve/LUT decoders |
| `gamut_gpu.py` | OpenGL rendering, X-ray comparison, supersampling |
| `profile_categories.py` | Groups, checkboxes, sorting, search, drag/drop, category removal |
| `check_inspector.py`, `check_categories.py` | Existing application/category regressions |
| `check_gpu.py` | Real framebuffer pixels, enclosed comparison, CPU point limits, mode/resize checks |
| `check_adversarial.py` | Fixed color fixture, hull intersections, CSV, cancellation, header-only I/O, case/missing categories and hover regressions |
| `version.py`, `make_version_info.py` | Shared version and generated Windows file metadata |
| `.github/workflows/checks.yml` | Windows lint and GUI regression workflow on push/pull request |
| `check_upgrade.py` | Recovery, cross-process mutex, search/sort, background jobs, install contract, tags |
| `preview_list.py` | Normal single-instance startup on Profile List |
| `build.ps1` | Windows packaging with required dynamic modules |
| `build_macos.py`, `make_macos_notices.py` | Native app/ZIP packaging with runner-specific license texts |
| `check_platform.py`, `requirements-macos.txt` | macOS integration checks and pinned Mac dependencies |
| `requirements.txt`, `requirements-lock.txt` | Dependency ranges and tested versions |

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python check_inspector.py
.venv\Scripts\python check_categories.py
.venv\Scripts\python check_upgrade.py
.venv\Scripts\python check_adversarial.py
.venv\Scripts\python check_gpu.py
.venv\Scripts\python inspector.py
.venv\Scripts\Activate.ps1
.\build.ps1
```

CI installs the locked dependencies plus `requirements-dev.txt`, runs Ruff correctness rules and all four functional check scripts. A hosted VM may lack hardware OpenGL; `check_gpu.py` is a separate release check on real hardware. The [first remote CI run passed](https://github.com/pmatra/Printer-Profile-Inspector/actions/runs/44582598712); the live Actions badge above reports subsequent pushes. The fixed color fixture is generated sRGB; vendor printer profiles are not redistributed.

The executable supports `--gpu-check <report.json>` for an isolated diagnostic using temporary preferences.

Built independently; no reference-viewer executable, icon, or DLL was copied. Libraries include Pillow/LittleCMS, NumPy, SciPy, Tk, PyOpenGL, pyopengltk, Send2Trash, pywin32, and PyInstaller. See [Windows installation API](https://learn.microsoft.com/en-us/windows/win32/api/icm/nf-icm-installcolorprofilew), [ICC.1:2022](https://www.color.org/specifications/ICC.1-2022-05.pdf), and [Send2Trash](https://github.com/arsenetar/send2trash). The original application source is licensed under [MIT](LICENSE). See [Third-party notices](THIRD_PARTY_NOTICES.md) and the accompanying [complete license texts](THIRD_PARTY_LICENSES.txt) for dependencies and bundled runtimes. These files are included alongside the Windows executable.

