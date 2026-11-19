# macOS preview

The initial macOS version uses the **Basic CPU** renderer. Rotating/zooming,
points/surfaces/wireframes, comparison overlays, hull estimates, ICC tag curves,
categories, search and full CSV export remain available. The Windows GPU
renderer is unchanged. Native Mac GPU rendering is future work.

## Platform integration

- Settings and backup/recovery files:
  `~/Library/Application Support/PrinterProfileICCInspector/`.
- Default shared profile folder: `/Library/ColorSync/Profiles`.
- **Profile locations** opens My profiles, Shared profiles, or Apple's read-only
  `/System/Library/ColorSync/Profiles` folder.
- **Install Profile** installs only into `~/Library/ColorSync/Profiles`, creating
  it if necessary. It never requests administrator elevation or changes device
  associations. Atomic no-replace publication prevents overwriting a different
  existing profile, including concurrent name collisions.
- **Move profile to Trash** uses Cocoa's native Trash through Send2Trash.
  Errors preserve the source; there is no permanent-delete fallback. The app
  rejects deletion of macOS-managed profiles under `/System`.
- Themes: **Light**, **Dark**, **Follow macOS**. The native window appearance
  follows the selected mode, and Follow macOS responds to system changes.
  Tk's system font is retained; font files are not bundled.
- A per-user advisory file lock prevents another application instance from
  racing category writes. Kernel locks release on crash; the lock file remains
  so inode replacement cannot create a two-instance race. A duplicate launch
  activates the existing process. Finder reopen/open-document events are
  handled by Tk; Command-O, Command-comma and Control-click are supported.

Categories are keyed by directory and exact filename. Moving settings between
Windows and Mac does not automatically translate directory paths. Use Recover
categories to copy a saved old location's assignments to the current folder.

## Build and download

GitHub Actions **macOS builds** uses separate `macos-15` Apple Silicon and
`macos-15-intel` Intel runners. Both run native platform/GUI/category/color
regressions, collect the actual Mac dependency licenses, build a `.app`, verify
its loader signature, and run a packaged smoke test. Successful jobs upload
`macOS-arm64` and `macOS-x86_64` artifacts containing the app ZIP, checksum,
diagnostic report and readme.

This first build targets **macOS 15 or later**. It is **ad-hoc signed for the
loader, not Developer ID signed or notarized**. Gatekeeper may block an Internet
download. No Apple developer account or paid signing service has been set up,
and no trusted publisher identity is claimed. Runner tests do not replace
interactive acceptance testing on a physical Mac, especially appearance,
trackpad behavior and Finder integration.

To build locally on the target Mac architecture:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-macos.txt -r requirements-dev.txt
python check_platform.py
python check_categories.py
python check_adversarial.py
python build_macos.py
```

Use a Python installation with working Cocoa Tcl/Tk, such as current python.org
Python 3.12. Build artifacts go in `dist/macos`. `ditto` preserves app-bundle
symlinks and metadata in the ZIP. Mac notices are collected from that runner's
actual wheels/Python/Tcl/Tk, rather than reusing the Windows runtime notices.

Platform checks create and Trash only their own temporary generated ICC file;
they do not alter any installed profiles.
