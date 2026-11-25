"""Offline release-selection tests and main-thread UI regressions."""
from concurrent.futures import Future
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import inspector as m
import update_checker as u
from test_event_loop import configure_test_events


def release(version='0.9.0', name='ICC-Profile-Inspector-Setup-v0.9.0-x64.exe', **extra):
    return {'tag_name': 'v'+version, 'html_url': f'{u.RELEASES_URL}/tag/v{version}',
            'assets': [{'name': name, 'browser_download_url': f'{u.RELEASES_URL}/download/v{version}/{name}'}], **extra}


def run_checks():
    assert u.version_tuple('v0.10.0') > u.version_tuple('0.9.99')
    assert u.version_tuple('0.9.0-beta.1') is None
    newer = release()
    assert u.select_release([newer], '0.8.0', 'win32', 'AMD64').version == '0.9.0'
    assert u.select_release([newer], '0.9.0', 'win32', 'AMD64') is None
    assert u.select_release([newer], '0.8.0', 'darwin', 'arm64') is None
    assert u.select_release([release(prerelease=True), release(draft=True)], '0.8.0', 'win32', 'AMD64') is None
    assert u.select_release([release(html_url='https://example.com/evil')], '0.8.0', 'win32', 'AMD64') is None
    old = release('0.7.0')
    assert u.select_release([old, newer], '0.8.0', 'win32', 'AMD64').version == '0.9.0'
    mac = release(name='ICC-Profile-Inspector-macOS-arm64-v0.9.0.zip')
    assert u.select_release([mac], '0.8.0', 'darwin', 'arm64').version == '0.9.0'
    assert u.select_release([mac], '0.8.0', 'darwin', 'x86_64') is None
    opener = Mock(return_value=BytesIO(json.dumps([newer]).encode()))
    assert u.check_for_update('0.8.0', system='win32', machine='AMD64', opener=opener).version == '0.9.0'
    assert opener.call_args.kwargs['timeout'] == 6
    assert 'Authorization' not in opener.call_args.args[0].headers
    for error in (URLError('offline'), HTTPError(u.API_URL,403,'limited',{},None)):
        try: u.check_for_update('0.8.0', opener=Mock(side_effect=error))
        except u.UpdateCheckError: pass
        else: raise AssertionError('Expected a useful network error')
    try: u.check_for_update('0.8.0', opener=lambda *a,**k: BytesIO(b'x'*(u.MAX_RESPONSE+1)))
    except u.UpdateCheckError: pass
    else: raise AssertionError('Oversized reply accepted')
    print('PASS: version ordering, stable/platform filtering, trusted release links, timeout, offline/rate-limit handling and response bound', flush=True)

    with tempfile.TemporaryDirectory() as folder, patch.object(m,'SETTINGS_PATH',Path(folder)/'settings.json'), patch.object(m,'DEFAULT_DIRECTORY',Path(folder)):
        app=m.Inspector(background_io=False)
        configure_test_events(app)
        try:
            app.render_mode.set('Basic CPU');app.select_renderer();app.main_tabs.select(app.inspector_tab)
            notebook=app.tags.master.master.master
            notebook.select(app.tags.master.master)
            for i in range(40):app.tags.insert('', 'end', text=f'tag{i}', values=('test','text',20))
            app.update()
            app.tags_scrollbar.event_generate('<Button-1>',x=8,y=max(10,app.tags_scrollbar.winfo_height()-8))
            app.tags_scrollbar.event_generate('<ButtonRelease-1>',x=8,y=max(10,app.tags_scrollbar.winfo_height()-8))
            app.tags.yview_moveto(1)
            app.update()
            assert app.tags.yview()[1] == 1 and app.tags.yview()[0] > 0
            assert app.tags_scrollbar.winfo_x() >= app.tags.winfo_x()+app.tags.winfo_width()
            assert app.gear_button.cget('relief') == 'flat' and int(app.gear_button.cget('borderwidth')) == 0
            assert int(app.gear_button.cget('highlightthickness')) == 0
            for theme in m.THEMES[:2]:
                app.theme_choice.set(theme);app.apply_theme()
                assert app.gear_button.cget('background') == app.colors['bg']
            main_thread=threading.get_ident()
            future=Future();app.update_future=future;app.update_manual=True
            future.set_result(u.Release('0.9.0',newer['html_url'],newer['assets'][0]['name']))
            with patch.object(m.messagebox,'askyesno',side_effect=lambda *a,**k: threading.get_ident()==main_thread) as prompt, patch.object(m.webbrowser,'open',return_value=True) as browser:
                app.finish_update_check();assert prompt.call_count==1;browser.assert_called_once_with(newer['html_url'])
                assert 'Update available: 0.9.0' in app.status.cget('text')
            for manual in (False,True):
                future=Future();future.set_exception(u.UpdateCheckError('offline'));app.update_future=future;app.update_manual=manual
                with patch.object(m.messagebox,'showwarning') as warning:
                    app.finish_update_check();assert warning.call_count == int(manual)
            fake=Future()
            with patch.object(app.io_executor,'submit',return_value=fake) as submit:
                app.check_updates(automatic=True);app.check_updates();assert submit.call_count==1 and app.update_manual
            app.update_future=None
        finally: app.destroy()
    print('PASS: visible tag scrollbar, borderless themed gear, main-thread update prompts, noninterrupting offline startup and duplicate suppression',flush=True)

    fake_app=Mock()
    with patch.object(m,'SingleInstance') as guard, patch.object(m,'Inspector',return_value=fake_app), patch.object(m.sys,'argv',['inspector.py']):
        guard.return_value.acquire.return_value=True;m.main()
    scheduled=[c for c in fake_app.after.call_args_list if c.args[0]==1500]
    assert len(scheduled)==1
    scheduled[0].args[1]();fake_app.check_updates.assert_called_once_with(automatic=True)
    print('PASS: every normal application startup schedules a background update check',flush=True)


if __name__=='__main__':
    run_checks()
