"""Native macOS checks and Windows-hosted tests of the platform dispatch."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
import uuid
from PIL import ImageCms
import app_support as support


def run_packaged_check(module=None):
    if module is None:
        import inspector as module
    m=module
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        previous=m.SETTINGS_PATH
        m.SETTINGS_PATH=root/'settings.json'
        profile=root/'sample.icc'
        profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        app=None
        try:
            print('Platform smoke: creating application',flush=True)
            app=m.Inspector(background_io=False)
            app.update()
            print('Platform smoke: loading generated profile',flush=True)
            app.directory=str(root);app.refresh_directory()
            app.load(str(profile),background=False)
            assert app.primary is not None
            app.load(str(profile),compare=True,background=False)
            print('Platform smoke: rendering views',flush=True)
            for view in ('Points','Surface','Wireframe'):
                app.view.set(view);app.draw();app.update()
            for theme in m.THEMES:
                app.theme_choice.set(theme);app.change_theme();app.update()
            print('Platform smoke: checking native integration',flush=True)
            if sys.platform=='darwin':
                assert app.render_mode.get()=='Basic CPU' and app.gpu is None
                assert app.bind('<Command-o>')
                assert app.profile_list.bind('<Control-Button-1>')
                assert app.tk.call('info','commands','::tk::mac::OpenDocument')
                assert isinstance(support.macos_is_dark(),bool)
                # Isolated installation and native Trash of a freshly generated test file.
                with patch.object(support,'installation_directory',return_value=root/'user-profiles'):
                    installed=support.install_profile(profile)
                    assert installed.read_bytes()==profile.read_bytes()
                trash=root/('ICC-Inspector-test-'+uuid.uuid4().hex+'.icc')
                trash.write_bytes(profile.read_bytes());support.recycle_profile(trash)
                assert not trash.exists()
            else:
                assert support.settings_path().name=='settings.json'
            from version import __version__
            return {'platform':sys.platform,'version':__version__,'renderer':app.render_mode.get(),
                    'samples':app.primary['samples'],'themes':list(m.THEMES),'native_trash_test':sys.platform=='darwin'}
        finally:
            if app is not None: app.destroy()
            m.SETTINGS_PATH=previous


def run_checks():
    host=sys.platform
    native_link=os.link
    def publish_link(source,target):
        if host!='win32': return native_link(source,target)
        # Windows sandbox hosts may prohibit hard links. Mock this POSIX API
        # contract here; native Mac CI exercises the real os.link below.
        fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream: stream.write(Path(source).read_bytes())
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        # Platform paths and collision-safe copying can be checked on Windows too.
        with patch.object(support.sys,'platform','darwin'),patch.object(support.Path,'home',return_value=root),patch.object(support.os,'link',side_effect=publish_link):
            assert support.settings_path()==root/'Library/Application Support/PrinterProfileICCInspector/settings.json'
            assert support.color_directory()==Path('/Library/ColorSync/Profiles')
            assert support.installation_directory()==root/'Library/ColorSync/Profiles'
            assert len(support.profile_directories())==3
            source=root/'test.icc';source.write_bytes(b'generated test content')
            destination=support.install_profile(source)
            assert destination.read_bytes()==source.read_bytes()
            assert support.install_profile(source)==destination
            destination.write_bytes(b'other')
            try: support.install_profile(source)
            except FileExistsError: pass
            else: raise AssertionError('Install overwrote a different profile')
            assert not list(destination.parent.glob('.icc-install-*'))
            # Simulate a file appearing just before atomic publication.
            destination.unlink()
            def collide(temporary,target):
                Path(target).write_bytes(b'racing writer');raise FileExistsError('collision')
            with patch.object(support.os,'link',side_effect=collide):
                try: support.install_profile(source)
                except FileExistsError: pass
                else: raise AssertionError('Concurrent collision was not rejected')
            assert destination.read_bytes()==b'racing writer'
            assert not list(destination.parent.glob('.icc-install-*'))
        print('PASS: macOS paths, user-only installation, collision protection and temporary-file cleanup',flush=True)
        # Guard dispatch to native Cocoa without requiring Cocoa on Windows.
        app=Mock();appearance=Mock();appearance.bestMatchFromAppearancesWithNames_.return_value='DarkAqua';app.effectiveAppearance.return_value=appearance
        fake=SimpleNamespace(NSApplication=Mock(),NSAppearance=Mock(),NSAppearanceNameAqua='Aqua',NSAppearanceNameDarkAqua='DarkAqua')
        fake.NSApplication.sharedApplication.return_value=app
        with patch.dict(sys.modules,{'AppKit':fake}):
            assert support.macos_is_dark()
            support.set_macos_appearance('Follow macOS');app.setAppearance_.assert_called_with(None)
            support.set_macos_appearance('Dark');fake.NSAppearance.appearanceNamed_.assert_called_with('DarkAqua')
        if sys.platform=='darwin':
            name='test-'+uuid.uuid4().hex
            settings=root/'guard/settings.json'
            guard=support.SingleInstance(name)
            with patch.object(support,'settings_path',return_value=settings):
                assert guard.acquire()
                code='from pathlib import Path; import sys,app_support as s; s.settings_path=lambda:Path(sys.argv[2]); g=s.SingleInstance(sys.argv[1]); print(g.acquire());g.close()'
                result=subprocess.run([sys.executable,'-c',code,name,str(settings)],env=dict(os.environ,PYTHONPATH=str(Path(__file__).parent.resolve())),capture_output=True,text=True,timeout=20)
                assert result.returncode==0 and result.stdout.strip()=='False',result.stderr
                lock=guard.lock_path();guard.close();assert lock.exists()
                assert guard.acquire();guard.close()
                # OS lock release after a process exits without explicit cleanup.
                code='from pathlib import Path; import sys,os,app_support as s;s.settings_path=lambda:Path(sys.argv[2]);g=s.SingleInstance(sys.argv[1]);assert g.acquire();os._exit(0)'
                result=subprocess.run([sys.executable,'-c',code,name,str(settings)],env=dict(os.environ,PYTHONPATH=str(Path(__file__).parent.resolve())),timeout=20)
                assert result.returncode==0 and guard.acquire();guard.close()
            print('PASS: native macOS cross-process lock, release and crash recovery',flush=True)
        print('PASS: native appearance dispatch and follow-system override reset',flush=True)
    # An unexpected modal would stall unattended CI instead of reporting a failure.
    import inspector as m
    def unexpected_dialog(*args,**kwargs): raise AssertionError('Unexpected dialog: '+str(args))
    with patch.object(m.messagebox,'showerror',side_effect=unexpected_dialog),patch.object(m.messagebox,'showwarning',side_effect=unexpected_dialog):
        print(json.dumps(run_packaged_check(m),indent=2),flush=True)


if __name__=='__main__': run_checks()
