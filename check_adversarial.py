"""Regression checks for issue #1. GUI/OS operations use isolated temporary data."""
import csv
import hashlib
from pathlib import Path
from threading import Event, get_ident
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from scipy.spatial import ConvexHull
from test_event_loop import configure_test_events
import inspector as m
from gamut_analysis import hull_metrics
from profile_categories import directory_key


def pump(app, predicate, seconds=15):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:
        app.update(); time.sleep(.01)
    assert predicate(), 'Background operation did not finish in time'


def cube(offset=0, size=2):
    points=np.array([[x+offset,y,z] for x in (0,size) for y in (0,size) for z in (0,size)],dtype=float)
    return {'hull':ConvexHull(points)}


if __name__=='__main__':
    asset=Path(__file__).parent/'tests/fixtures/srgb-reference.icc'
    assert hashlib.sha256(asset.read_bytes()).hexdigest()=='f3aff2ca301bf0b8371e53eb5fde8a0c49e6324a8b81a6f6a52ec065994c464d'
    result=m.sample_gamut(asset,1,3)
    anchors={0:[0,0,0],2:[29.4,68,-112],6:[87.84,-79,81],18:[54.12,81,70],26:[100,0,0]}
    for index,expected in anchors.items(): assert np.allclose(result['lab'][index],expected,atol=1),index
    print('PASS: fixed ICC asset, black/white/primary D50 Lab anchors, public Pillow pixel decoding',flush=True)
    for other,overlap in [(cube(),8),(cube(1),4),(cube(2),0),(cube(3),0),(cube(.5,1),1)]:
        metrics=hull_metrics(cube(),other)
        assert abs(metrics['overlap_volume']-overlap)<1e-6,metrics
    assert hull_metrics({'hull':None})['primary_volume'] is None
    print('PASS: convex-hull volumes/intersections for identical, partial, touching, disjoint and contained hulls',flush=True)
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary); profiles=root/'profiles';profiles.mkdir()
        for name in ('A.icc','B.icc'): (profiles/name).write_bytes(asset.read_bytes())
        # Directory columns only read headers: full parsing is reserved for Inspector.
        with patch.object(m,'read_profile',side_effect=AssertionError('Full parser used by directory list')):
            assert len(m.directory_entries(profiles))==2
        destination=root/'samples.csv'
        assert m.write_samples_csv(destination,[('primary',result),('comparison',result)])==54
        with destination.open(newline='',encoding='utf-8') as stream: rows=list(csv.DictReader(stream))
        assert len(rows)==54 and {r['role'] for r in rows}=={'primary','comparison'}
        assert [rows[26][f'device_{i}'] for i in range(1,5)]==['255','255','255','']
        assert [rows[26][f'grid_{i}'] for i in range(1,5)]==['2','2','2','']
        assert rows[0]['profile_sha256']==hashlib.sha256(asset.read_bytes()).hexdigest()
        token=Event();token.set();before=destination.read_bytes()
        try: m.run_cancellable(m.write_samples_csv,token,None,destination,[('primary',result)])
        except m.WorkCancelled: pass
        else: raise AssertionError('Cancelled export was not stopped')
        assert destination.read_bytes()==before
        token=Event();progress=[]
        def cancel_during_sampling(message):
            progress.append(message)
            if message.startswith('Sampling ICC transform:'): token.set()
        try: m.run_cancellable(m.sample_gamut,token,cancel_during_sampling,asset,1,21)
        except m.WorkCancelled: pass
        else: raise AssertionError('Sampling ignored cancellation token')
        assert any(s.startswith('Sampling ICC transform:') for s in progress)
        print('PASS: header-only listing, complete primary/comparison CSV and cooperative sampling/export cancellation',flush=True)
        m.SETTINGS_PATH=root/'settings.json'
        app=configure_test_events(m.Inspector(background_io=False))
        try:
            app.directory=str(profiles);app.refresh_directory()
            # Simulate distinct names even on a case-insensitive Windows filesystem.
            app.category_store={directory_key(profiles):[
                {'id':'upper','name':'Upper','files':['A.icc','missing.icc'],'open':True},
                {'id':'lower','name':'Lower','files':['a.icc'],'open':True}]}
            sample_rows=[(profiles/name,(name,'4.0.0','RGB',created,'ICC profile')) for name,created in [('A.icc','Unspecified / invalid'),('a.icc','2020-01-01 00:00:00'),('B.icc','2021-01-01 00:00:00')]]
            app.render_library(sample_rows)
            assert app.profile_list.parent('profile:0')=='category:upper'
            assert app.profile_list.parent('profile:1')=='category:lower'
            assert 'missing' in app.category_warning.cget('text')
            for reverse in (False,True):
                app.active_sort_column='created';app.active_sort_reverse=reverse
                # Place invalid and valid timestamps in the same group.
                app.category_store={directory_key(profiles):[]};app.render_library(sample_rows)
                children=app.profile_list.get_children('uncategorized')
                assert app.profile_list.set(children[-1],'created')=='Unspecified / invalid'
                assert ('▼' if reverse else '▲') in app.profile_list.heading('created','text')
            old='C:/old-profile-folder'
            app.category_store={directory_key(old):[{'id':'recovered','name':'Recovered','files':['A.icc'],'open':True}]}
            with patch('profile_categories.simpledialog.askstring',return_value=old): app.recover_categories()
            assert app.categories()[0]['name']=='Recovered' and directory_key(old) in app.category_store
            # A stalled scan cannot block Tk; a cancelled late result cannot replace the list.
            gate=Event();entered=Event();heartbeat=[];original=m.directory_entries
            def slow_scan(directory):
                entered.set();gate.wait(5);return original(directory)
            with patch.object(m,'directory_entries',side_effect=slow_scan):
                start=time.monotonic();app.refresh_directory(background=True)
                assert time.monotonic()-start<.5
                assert entered.wait(1)
                app.after(10,lambda:heartbeat.append(True))
                pump(app,lambda:bool(heartbeat))
                app.cancel_work();gate.set()
                pump(app,lambda:not app.directory_jobs)
            # Parsing, not only ICC sampling, must execute on a worker.
            gate=Event();entered=Event();thread_ids=[];original=m.read_profile
            def slow_profile(path):
                thread_ids.append(get_ident());entered.set();gate.wait(5);return original(path)
            with patch.object(m,'read_profile',side_effect=slow_profile):
                start=time.monotonic();app.load(str(profiles/'B.icc'))
                assert time.monotonic()-start<.5 and entered.wait(1)
                assert all(identifier!=get_ident() for identifier in thread_ids)
                app.cancel_work();gate.set();pump(app,lambda:not app.jobs)
                assert app.primary is None
            app.render_mode.set('Basic CPU');app.select_renderer()
            app.hitpoints=[(float(i),float(i%100),np.array([50,1,2])) for i in range(194481)]
            app.hover(SimpleNamespace(x=100,y=0))
            assert len(app.hover_points)<=5000 and app.hover_tree.n<=5000
            assert 'convex-hull approximation' in app.plot_notice.cget('text')
            print('PASS: case-distinct categories, missing-membership warning/recovery, sort arrows/invalid dates, background scan/parsing, stale cancellation and bounded indexed hover',flush=True)
        finally: app.destroy()
