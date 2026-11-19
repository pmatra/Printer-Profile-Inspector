# Third-party notices

ICC Profile Inspector v0.6.0 — Windows distribution, prepared 2026-11-19.

The application's original source code is Copyright (c) 2026 Peter Matra and
licensed under [MIT](LICENSE). Third-party components keep their own copyright
notices and license terms. The MIT license does not relicense these components.

**[THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt) contains the complete
collected license texts**, including upstream copyright notices, disclaimers,
exceptions, and bundled-library notices. Keep both files with redistributed
Windows packages. Each section records its source and original-file SHA-256.
Existing notices inside `_internal` are also retained.

## Application dependencies and runtime

| Component | Version | License / notice collection |
| --- | --- | --- |
| Python | 3.12.4 | PSF license and historical/incorporated-software terms |
| Tcl / Tk | 8.6.13 | Tcl/Tk permissive license terms |
| Pillow | 13.0.0 | MIT-CMU; distribution's complete bundled-library notices |
| LittleCMS | 2.19.1, through Pillow | MIT; included in Pillow's license collection |
| NumPy | 2.5.5 | BSD-3-Clause and distribution's bundled code/library licenses |
| HiGHS | 1.12.0, through SciPy | MIT; upstream versioned license included |
| Qhull | Bundled with SciPy | Qhull copyright and permission notice included |
| SciPy | 1.18.1 | BSD-3-Clause and distribution's bundled code/library licenses |
| PyOpenGL | 3.1.10 | BSD-style PyOpenGL license collection |
| pyopengltk | 0.0.4 | MIT |
| Send2Trash | 2.2.0 | BSD-3-Clause |
| pywin32 | 312 | Distribution's win32, COM, PythonWin and other license collection |
| OpenSSL | 3.0.13, through Python | Apache-2.0 |
| Expat | 2.6.2, through Python | MIT |
| libffi | 3.4.4, through Python | Permissive terms reproduced in Python's license collection |
| bzip2 | 1.0.8, through Python | bzip2 license reproduced in Python's license collection |
| liblzma / XZ Utils | 5.2.5, through Python | Public-domain library; upstream COPYING included |
| zlib | 1.3.1, through Python | zlib license |
| freeglut / GLE | Supplied with PyOpenGL 3.1.10 | Upstream COPYING files; GLE source uses its IBM source license alternative |

Pillow's full license file also covers its distribution's Brotli, FreeType,
HarfBuzz, libavif, libjpeg-turbo, libpng, libwebp, OpenJPEG, TIFF, XZ and zlib-ng
components. NumPy/SciPy license collections retain OpenBLAS and compiler-runtime
notices/exceptions and other incorporated-code notices supplied by those wheels.
The collections may describe optional software not loaded by this application.

This software is based in part on the work of the FreeType Team and the
Independent JPEG Group. It includes code from XZ Utils.

Microsoft Windows runtime/API-set DLLs included by the Windows packaging tools
remain Microsoft components under their applicable redistribution terms; they
are not covered by this project's MIT license. Windows system fonts are used
from the installed operating system; no font files are redistributed.

## Build and packaging tools

| Component | Version | License |
| --- | --- | --- |
| PyInstaller | 6.22.3 | GPL-2.0-or-later with bootloader/distribution exception; selected files Apache-2.0 |
| pyinstaller-hooks-contrib | 2026.10 | GPL-2.0-or-later and project distribution exception |
| altgraph | 0.17.5 | MIT |
| packaging | 26.3 | Apache-2.0 or BSD-2-Clause |
| pefile | 2024.8.26 | MIT |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| setuptools | 84.2.1 | MIT |

Their supplied texts are included for completeness. Listing a build dependency
does not mean the entire tool is shipped in the runtime. The PyInstaller
exception permits distribution of the packaged application under its own license.

## Provenance

Most texts were copied from the exact installed distributions listed in
`requirements-lock.txt`. Python and Tk notices came from the Python 3.12.4
installation used to build the executable. Missing wheel-level texts were
obtained from these versioned upstream sources:

- [PyOpenGL 3.1.10 source distribution](https://pypi.org/project/PyOpenGL/3.1.10/#files): `license.txt`.
- [Python v3.12.4 license documentation](https://github.com/python/cpython/blob/v3.12.4/Doc/license.rst): incorporated-software terms and acknowledgements, reproduced in its original reStructuredText form.
- [Tcl 8.6.13](https://github.com/tcltk/tcl/blob/core-8-6-13/license.terms): `license.terms`.
- [OpenSSL 3.0.13](https://github.com/openssl/openssl/blob/openssl-3.0.13/LICENSE.txt): `LICENSE.txt`.
- [Expat 2.6.2](https://github.com/libexpat/libexpat/blob/R_2_6_2/COPYING): `COPYING`.
- [HiGHS 1.12.0](https://github.com/ERGO-Code/HiGHS/blob/v1.12.0/LICENSE.txt): `LICENSE.txt`.
- [XZ Utils 5.2.5](https://github.com/tukaani-project/xz/blob/v5.2.5/COPYING): `COPYING`.
- [zlib 1.3.1](https://github.com/madler/zlib/blob/v1.3.1/LICENSE): `LICENSE`.

When changing dependencies or rebuilding with another runtime, review and refresh
these notices against the actual distributions and native libraries included.
