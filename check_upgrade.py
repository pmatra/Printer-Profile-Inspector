"""Regression coverage for v0.5 reliability, organization, and decoded tags."""
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import threading
import uuid
from unittest.mock import patch, Mock
import numpy as np
from PIL import ImageCms
import inspector as m
import profile_categories as c
import app_support as support
from icc_tags import decode_tag


with tempfile.TemporaryDirectory() as folder:
    root=Path(folder); settings=root/'preferences'/'settings.json'
    notices=[]; store=support.SettingsStore(settings,notices=notices)
    store.update('profile_categories',{'directory':[{'name':'Keep me'}]})
    store.update('theme','Windows Dark')
    settings.write_text('{broken')
    recovered=store.read()
    assert recovered['profile_categories']['directory'][0]['name']=='Keep me'
    assert notices and list(settings.parent.glob('settings.corrupt-*.json'))
    before=settings.read_bytes()
    replace=support.os.replace
    def reject_primary(source,destination):
        if Path(destination)==settings: raise OSError('Simulated interrupted replacement')
        return replace(source,destination)
    with patch.object(support.os,'replace',side_effect=reject_primary):
        try: store.update('theme','Windows Light')
        except OSError: pass
        else: raise AssertionError('Expected atomic replace failure')
    assert settings.read_bytes()==before
    assert not list(settings.parent.glob('*.tmp'))
    legacy=root/'portable.json'; legacy.write_text(json.dumps({'theme':'Windows Dark','profile_categories':{'old':[]}}))
    migrated=support.SettingsStore(root/'roaming'/'settings.json',legacy,notices)
    assert migrated.read()['theme']=='Windows Dark' and legacy.exists()
    print('PASS: atomic failed-save preservation, backup recovery, corrupt-file preservation and portable migration',flush=True)

    guard=support.SingleInstance('Local\\ICC-test-'+uuid.uuid4().hex)
    assert guard.acquire()
    code='import sys; from app_support import SingleInstance; g=SingleInstance(sys.argv[1]); print(g.acquire()); g.close()'
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parent))
    child=subprocess.run([sys.executable,'-c',code,guard.name],env=env,capture_output=True,text=True,timeout=15)
    assert child.returncode==0 and child.stdout.strip()=='False',child.stderr
    guard.close()
    assert guard.acquire(); guard.close()
    print('PASS: real Windows mutex rejects a second process and releases on close',flush=True)
    with patch.object(m,'SingleInstance') as guard_type,patch.object(m,'raise_existing_window') as raise_window,patch.object(m,'Inspector') as construct:
        guard_type.return_value.acquire.return_value=False
        m.main()
        raise_window.assert_called_once(); construct.assert_not_called()

    profiles=root/'profiles'; profiles.mkdir()
    icc=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for name in ('A.icc','B.icc','C.icc'): (profiles/name).write_bytes(icc)
    m.SETTINGS_PATH=root/'app-settings.json'
    app=m.Inspector(); app.directory=str(profiles); app.refresh_directory()
    app.check_all_profiles()
    with patch.object(c.simpledialog,'askstring',return_value='Papers'): app.create_category()
    group='category:'+app.categories()[0]['id']
    app.sort_directory('filename'); app.sort_directory('filename')
    expected=['C.icc','B.icc','A.icc']
    assert [app.profile_list.set(i,'filename') for i in app.profile_list.get_children(group)]==expected
    app.profile_list.item(group,open=False); app.save_category_expansion()
    app.profile_list.item(group,open=True); app.save_category_expansion(); app.refresh_directory()
    assert [app.profile_list.set(i,'filename') for i in app.profile_list.get_children(group)]==expected
    app.search_text.set('B.icc'); app.apply_search()
    assert [p.name for p in app.list_paths.values()]==['B.icc']
    app.search_text.set('Papers'); app.apply_search()
    assert len(app.list_paths)==3
    with patch.object(c.messagebox,'askyesno',return_value=False): app.remove_category(group)
    assert app.categories()
    with patch.object(c.messagebox,'askyesno',return_value=True): app.remove_category(group)
    assert not app.categories()
    assert all((profiles/name).read_bytes()==icc for name in expected)
    app.search_text.set(''); app.apply_search()
    with patch.object(m,'recycle_profile') as recycle,patch.object(m.messagebox,'askyesno',return_value=True):
        app.delete_profile(profiles/'A.icc')
        recycle.assert_called_once_with(profiles/'A.icc')
    assert (profiles/'A.icc').exists(),'Mocked recycle must never call unlink'
    print('PASS: sorting survives folding/refresh, search matches files/categories, removal keeps files, deletion calls Recycle Bin only',flush=True)

    # Sampling completes off-thread and late results cannot replace newer requests.
    real_sample=m.cached_sample
    release=threading.Event()
    def slow_sample(*args): release.wait(3); return m.sample_gamut(args[0],args[3],args[4])
    app.update()
    with patch.object(m,'cached_sample',side_effect=slow_sample):
        started=time.perf_counter(); app.load(str(profiles/'A.icc'))
        assert time.perf_counter()-started<2 and not app.jobs[0][0].done(),'Submitting sampling should not wait for the ICC transform'
        app.load(str(profiles/'B.icc'))
        release.set()
        deadline=time.monotonic()+10
        while app.jobs and time.monotonic()<deadline: app.update(); time.sleep(.01)
        assert app.primary and Path(app.primary['path']).name=='B.icc'
    fake={'points':np.zeros((194481,3)),'hull':None}
    assert len(m.display_indices(fake,4000))<=4000 and len(fake['points'])==194481
    app.destroy()
    reopened=m.Inspector()
    assert reopened.active_sort_reverse and reopened.active_sort_column=='filename'
    reopened.destroy()
    print('PASS: background sampling returns promptly, obsolete jobs ignored, display decimation retains source samples, sort survives restart',flush=True)

    target=root/'color'; target.mkdir()
    api=Mock()
    api.InstallColorProfileW.side_effect=lambda machine,path: bool(shutil.copy2(path,target/Path(path).name))
    with patch.object(support,'color_directory',return_value=target),patch.object(support.ctypes,'WinDLL',return_value=api):
        installed=support.install_profile(profiles/'B.icc')
        assert installed.read_bytes()==icc
        api.InstallColorProfileW.assert_called_once_with(None,str((profiles/'B.icc').resolve()))
        (target/'C.icc').write_bytes(b'different')
        try: support.install_profile(profiles/'C.icc')
        except FileExistsError: pass
        else: raise AssertionError('Installer must reject filename collisions')
    print('PASS: Windows InstallColorProfileW contract and no overwrite of a different installed profile (mock OS API)',flush=True)

    for filename in ('AdobeRGB1998.icc','CoatedFOGRA39.icc','Epson IJ Printer 07.icc'):
        profile=m.DEFAULT_DIRECTORY/filename
        if not profile.exists(): continue
        data,fields,tags=m.read_profile(profile)
        for signature,kind,offset,size in tags:
            text,curves=decode_tag(signature,data[offset:offset+size])
            if kind in ('curv','para','XYZ ','mft1','mft2','mAB ','mBA ','mluc','desc'):
                assert 'Cannot decode' not in text,(filename,signature,text)
            for _,x,y in curves: assert np.isfinite(y).all() and len(x)==len(y)
    payload=b'curv'+b'\0'*4+struct.pack('>IH',1,563)
    text,curves=decode_tag('rTRC',payload)
    assert 'Gamma' in text and abs(curves[0][2][-1]-1)<1e-9
    text,_=decode_tag('wtpt',b'XYZ '+b'\0'*4+struct.pack('>iii',63190,65536,54061))
    assert 'Chromaticity' in text
    for broken in (b'',b'mft2'+b'\0'*8,b'curv'+b'\0'*4+struct.pack('>I',0xffffffff)):
        text,curves=decode_tag('test',broken)
        assert 'Cannot decode' in text and not curves
    print('PASS: decoded real profile descriptions, white points, curves, LUTs and bounded malformed-payload handling',flush=True)
