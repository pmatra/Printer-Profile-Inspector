# ICC Gamut Inspector

[Download the latest Windows release](https://github.com/pmatra/Printer-Profile-Inspector/releases/latest) · [Release v0.2.0](https://github.com/pmatra/Printer-Profile-Inspector/releases/tag/v0.2.0)

Download the Windows ZIP under **Assets**, extract the entire archive, and run the executable inside the application folder. Each release tag identifies the matching source revision.

Run `ICC Gamut Inspector.exe` in the application folder. No Python installation is needed for the packaged application. You can also pass an ICC/ICM file path on the command line.

Use the **gear button in the upper-right corner → Theme** to select **Windows Light**, **Windows Dark**, or **Follow Windows** (the default). The choice is saved alongside the directory preference in `settings.json`. Follow Windows checks the Windows app appearance setting while the program is open. Text, controls, tables, and the plot background and labels adapt; sampled gamut colors retain their color meaning. Ctrl+, also opens the settings menu.

**High GPU** is the default 3D renderer. It uses hardware OpenGL, interpolated vertex colors, depth testing, and an offscreen render target at up to twice the viewport width and height (four render pixels per displayed pixel), downsampled for smoother edges. The renderer line reports the actual graphics device and render-target resolution. The default sampling grid is 17 per channel; 21 is also available. CMYK grids have N⁴ samples, so higher settings take longer. ICC sampling and hull construction run on the CPU; OpenGL handles the 3D drawing. Gamut colors are interpolated without artificial lighting. Red, gold, and gray axes indicate a*, b*, and L* respectively.

Choose **Basic CPU** for the previous renderer. If hardware OpenGL or the required framebuffer features are unavailable, the application falls back to Basic CPU and displays the reason. Render targets are capped at 4096 pixels per dimension; the reported size reflects any reduction. A graphics driver with OpenGL framebuffer/blit support is required for High GPU. Rendering quality does not turn the sampled convex hull into an exact gamut boundary.

The top tabs switch between **ICC/Gamut Inspector** and **Profile List**. The list initially reads `C:\Windows\System32\spool\drivers\color` and displays directory contents with Filename, Version, Device color space, Created, and Status columns. Created is the ICC header creation date, not the filesystem date. Click a column heading to sort. Double-click a profile to open it in the inspector; double-click a folder to browse into it.

Right-click an ICC/ICM profile in **Profile List** and choose **Delete profile…**. A Yes/No confirmation shows the exact filename and full path, with **No** selected by default. **Yes** permanently deletes that file and refreshes the list. Files that Windows does not permit you to delete show an error and remain listed.

On **Profile List**, use **Open Directory** to browse another folder, then check **Make this directory default** to use that folder on future launches. Unchecking restores the Windows color directory as the startup default. The preference is stored in `settings.json` beside the executable (or beside the Python source when running from source); keep the application in a writable folder. **Refresh** reloads the directory contents. Unreadable profiles remain listed with an explanatory status.

Open a printer profile with **Open profile**. Drag the plot to rotate and scroll to zoom. Use **Compare** to overlay a second profile as a cyan wireframe. Select Surface, Points, or Wireframe and choose a rendering intent or sampling grid. **Export samples** saves the primary profile's D50 CIELAB samples to CSV.

The left panel shows ICC header fields and tag signatures, types, sizes, and raw hexadecimal data. Tag previews are limited to 16 KiB. This is a structural inspector, not an ICC conformance validator.

## Color interpretation

Gamut calculations use Pillow's LittleCMS engine to transform device samples to D50 Lab. RGB, CMYK, and gray profiles are supported for sampling when the profile supplies a usable transform. Other profile types can still be inspected. CMYK sampling covers the full device grid, including high total ink values; it does not apply a separate ink-limit model.

Surface mode displays a **convex hull approximation** of a finite grid of device samples. It may fill concavities and miss narrow features. It is not an exact gamut boundary or a certified measurement. Increase the grid density to examine sampling differences. Gray profiles display a point sequence rather than a volume. Display colors are converted to sRGB and may clip; the plot is not a monitor-calibrated soft proof. Hover reports sampled Lab values, not interpolated surface values. No exact gamut volume or overlap percentage is claimed.

## Source and rebuilding

The complete application is implemented in `inspector.py`; the original reference viewer's executable and DLLs are not its source files.

| File | Purpose |
| --- | --- |
| `inspector.py` | ICC parsing, profile directory browser, desktop interface, color transforms, 3D plotting, and export |
| `gamut_gpu.py` | Hardware OpenGL viewport, smooth vertex-color surfaces, depth testing, and supersampling |
| `check_inspector.py` | Regression checks for profile parsing, color sampling, interface views, and saved defaults |
| `check_gpu.py` | Hardware-rendering smoke test including real framebuffer pixels, view modes, resizing, and renderer switching |
| `preview_list.py` | Launch the application with the Profile List tab selected |
| `build.ps1` | Build the Windows application using PyInstaller |
| `requirements.txt` | Dependency version ranges |
| `requirements-lock.txt` | Exact dependency versions used for the Windows build |
| `.gitignore` | Exclude generated builds, local settings, and virtual environments |

Run the existing regression checks with `python check_inspector.py` after installing the dependencies. These checks open desktop windows and require a graphical desktop. Additional checks use installed Windows printer profiles when available.

Run `python check_gpu.py` to verify actual hardware rendering. This test requires a supported GPU and fails explicitly if the program falls back to CPU rendering. Use `build.ps1` to package the app with dynamically loaded OpenGL modules included.

Source: `inspector.py`. Python 3.12 or later is recommended.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python inspector.py
.venv\Scripts\Activate.ps1
.\build.ps1
```

Built independently using the reference viewer's documented header/tag inspection functions as a feature reference. No reference executable, icon, or DLL was copied into this application.

Libraries: [Pillow / ImageCms](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html), NumPy, SciPy, Tk, and PyInstaller. Dependency licenses are included in the packaged application's `_internal` folder where supplied by their distributions.
