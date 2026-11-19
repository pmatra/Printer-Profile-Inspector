import importlib.util
import tempfile
from unittest.mock import patch
from pathlib import Path
import numpy as np
from PIL import ImageCms

source = Path(__file__).resolve().parent / 'inspector.py'
spec = importlib.util.spec_from_file_location('inspector', source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
    path = Path(d) / 'sRGB.icc'
    path.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    m.SETTINGS_PATH = Path(d) / 'settings.json'
    result = m.sample_gamut(path)
    assert result['samples'] == 729
    assert np.isfinite(result['lab']).all()
    assert result['lab'][0, 0] < 1
    assert result['lab'][-1, 0] > 99
    assert np.abs(result['lab'][-1, 1:]).max() <= 1, 'Neutral white must have near-zero chroma'
    assert result['lab'][:, 1].min() < -50 and result['lab'][:, 1].max() > 50
    assert result['hull'].volume > 0
    for broken in [b'', path.read_bytes()[:150]]:
        bad = Path(d) / 'bad.icc'; bad.write_bytes(broken)
        try: m.read_profile(bad)
        except ValueError: pass
        else: raise AssertionError('Malformed ICC accepted')
    app = m.Inspector(background_io=False)
    for theme in m.THEMES:
        app.theme_choice.set(theme)
        app.change_theme()
        app.update()
        assert app.canvas.cget('background') == app.colors['plot']
    app.theme_choice.set('Windows Dark')
    app.change_theme()
    assert app.directory == str(m.DEFAULT_DIRECTORY)
    assert len(app.main_tabs.tabs()) == 2
    app.directory = d
    app.refresh_directory()
    entries = [app.profile_list.item(i, 'values') for i in app.list_paths]
    srgb_row = next(row for row in entries if row[0] == 'sRGB.icc')
    assert srgb_row[1] and srgb_row[2] == 'RGB' and len(srgb_row[3]) == 19
    assert any(row[0] == 'bad.icc' and row[-1].startswith('Unreadable') for row in entries)
    app.make_default.set(True)
    app.save_default_directory()
    assert m.SETTINGS_PATH.exists()
    app.load(str(path), background=False)
    assert app.primary is not None
    app.load(str(path), True, background=False)
    for view in ['Points', 'Surface', 'Wireframe']:
        app.view.set(view); app.draw(); app.update()
    app.clear(); app.reset()
    victim = Path(d) / 'delete-test.icc'
    victim.write_bytes(path.read_bytes())
    app.refresh_directory()
    with patch.object(m.messagebox, 'askyesno', return_value=False) as question:
        app.delete_profile(victim)
        assert victim.exists(), 'No must preserve the file'
        assert str(victim) in question.call_args.args[1]
        assert question.call_args.kwargs['default'] == m.messagebox.NO
    with patch.object(m.messagebox, 'askyesno', return_value=True), patch.object(m, 'recycle_profile', side_effect=PermissionError('Access denied')), patch.object(m.messagebox, 'showerror') as error:
        app.delete_profile(victim)
        assert victim.exists()
        error.assert_called_once()
    app.load(str(victim), background=False)
    with patch.object(m.messagebox, 'askyesno', return_value=True), patch.object(m, 'recycle_profile', side_effect=lambda p:Path(p).unlink()):
        app.delete_profile(victim)
    assert not victim.exists() and app.primary is None and app.path is None
    assert victim not in app.list_paths.values()
    assert path.exists(), 'Deleting one profile must preserve the other profiles'
    with patch.object(m.messagebox, 'askyesno') as question, patch.object(m.messagebox, 'showerror'):
        app.delete_profile(Path(d) / 'settings.json')
        question.assert_not_called()
    print('PASS: delete confirmation No/Yes, exact path, permission failure, list refresh and loaded-profile cleanup')
    app.destroy()
    reopened = m.Inspector(background_io=False)
    assert reopened.theme_choice.get() == 'Windows Dark'
    assert reopened.active_dark
    assert reopened.directory == d, 'Default directory must survive restart'
    reopened.make_default.set(False)
    reopened.save_default_directory()
    assert reopened.default_directory == str(m.DEFAULT_DIRECTORY)
    assert m.read_settings()['theme'] == 'Windows Dark', 'Directory save must preserve theme'
    m.windows_is_dark = lambda: False
    reopened.theme_choice.set('Follow Windows')
    reopened.change_theme()
    assert not reopened.active_dark
    m.windows_is_dark = lambda: True
    reopened.watch_windows_theme()
    assert reopened.active_dark, 'Follow Windows must respond to system theme changes'
    reopened.destroy()
    print('PASS: top-level tabs, directory metadata, malformed-file rows, saved default and reset')
    print('PASS: all themes, preference persistence, directory preference coexistence and live system theme changes')
    print('PASS: sRGB endpoints, sampling, hull, malformed profiles, GUI loading, comparison and rendering modes')
for filename in ['CoatedFOGRA39.icc', 'Epson IJ Printer 07.icc', 'AdobeRGB1998.icc']:
    path = Path('C:/Windows/System32/spool/drivers/color') / filename
    if path.exists():
        for intent in range(4):
            r = m.sample_gamut(path, intent, 5)
            assert np.isfinite(r['lab']).all()
        print('PASS:', filename, 'all four intents')
