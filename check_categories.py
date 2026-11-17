"""Profile category interaction and persistence regression checks."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import ImageCms
import inspector as m
import profile_categories as categories


def find(app, filename):
    return next(item for item, path in app.list_paths.items() if path.name == filename)


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    m.SETTINGS_PATH = root / 'settings.json'
    profiles = root / 'profiles'
    profiles.mkdir()
    data = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    for name in ('one.icc', 'two.icc', 'three.icm'):
        (profiles / name).write_bytes(data)
    (profiles / 'note.txt').write_text('not a profile')
    app = m.Inspector()
    app.directory = str(profiles)
    app.refresh_directory()
    app.main_tabs.select(app.list_tab)
    app.update()
    tree = app.profile_list
    assert len(app.list_paths) == 4
    for name in ('one.icc', 'two.icc', 'three.icm'):
        assert tree.item(find(app, name), 'text') == '☐'
    app.toggle_profile_check(find(app, 'note.txt'))
    assert not app.checked_profiles
    x, y, w, h = tree.bbox(find(app, 'one.icc'), '#0')
    tree.event_generate('<ButtonPress-1>', x=x+w-12, y=y+h//2)
    tree.event_generate('<ButtonRelease-1>', x=x+w-12, y=y+h//2)
    assert str(profiles/'one.icc') in app.checked_profiles, 'Clicking the checkbox must select the profile'
    app.toggle_profile_check(find(app, 'two.icc'))
    with patch.object(categories.simpledialog, 'askstring', return_value='Photo papers'):
        app.create_category()
    category = app.categories()[0]
    item = 'category:' + category['id']
    assert len(tree.get_children(item)) == 2 and not app.checked_profiles
    assert sorted(category['files']) == ['one.icc', 'two.icc']
    assert tree.parent(find(app, 'three.icm')) == 'uncategorized'
    # Exercise actual mouse-event bindings for dragging the third profile into the accordion.
    app.update()
    x, y, w, h = tree.bbox(find(app, 'three.icm'), 'filename')
    tx, ty, tw, th = tree.bbox(item, 'filename')
    tree.event_generate('<ButtonPress-1>', x=x+25, y=y+h//2)
    tree.event_generate('<B1-Motion>', x=tx+25, y=ty+th//2)
    tree.event_generate('<ButtonRelease-1>', x=tx+25, y=ty+th//2)
    app.update()
    assert len(tree.get_children(item)) == 3, 'Drag/drop must categorize the clicked profile'
    app.begin_category_rename(item)
    app.category_editor.delete(0, 'end')
    app.category_editor.insert(0, 'Fine art papers')
    app.finish_category_rename(item)
    assert app.categories()[0]['name'] == 'Fine art papers'
    with patch.object(categories.simpledialog, 'askstring', return_value='Proofing'):
        app.create_category()
    second = app.categories()[1]
    second_item = 'category:' + second['id']
    app.toggle_profile_check(find(app, 'one.icc'))
    app.toggle_profile_check(find(app, 'two.icc'))
    app.update()
    sx, sy, sw, sh = tree.bbox(find(app, 'one.icc'), 'filename')
    dx, dy, dw, dh = tree.bbox(second_item, 'filename')
    tree.event_generate('<ButtonPress-1>', x=sx+25, y=sy+sh//2)
    tree.event_generate('<B1-Motion>', x=dx+25, y=dy+dh//2)
    tree.event_generate('<ButtonRelease-1>', x=dx+25, y=dy+dh//2)
    app.update()
    assert len(tree.get_children(second_item)) == 2, 'Dragging a checked row must move all checked profiles'
    assert len(tree.get_children(item)) == 1
    assert app.move_profiles_to_category([str(profiles/'one.icc'), str(profiles/'two.icc')], category['id'])
    tree.item(item, open=False)
    app.save_category_expansion()
    app.refresh_directory()
    assert not tree.item(item, 'open'), 'Collapsed state must survive refresh'
    app.check_all_profiles()
    assert len(app.checked_profiles) == 3, 'Select-all must include collapsed category children'
    app.clear_profile_checks()
    assert not app.checked_profiles
    with patch.object(categories.messagebox, 'showerror') as error:
        assert app.category_name('Uncategorized') is None
        assert app.category_name('Fine art papers') is None
        assert error.call_count == 2
    before = app.categories()
    with patch.object(app, 'save_category_settings', side_effect=PermissionError('Read only')), patch.object(categories.messagebox, 'showerror'):
        assert not app.move_profiles_to_category([str(profiles/'one.icc')], None)
    assert app.categories() == before
    # Moving out of a group changes metadata only.
    assert app.move_profiles_to_category([str(profiles/'one.icc')], None)
    assert tree.parent(find(app, 'one.icc')) == 'uncategorized'
    assert all((profiles/name).read_bytes() == data for name in ('one.icc','two.icc','three.icm'))
    other = root / 'other'
    other.mkdir()
    app.directory = str(other)
    app.refresh_directory()
    assert not app.categories(), 'Categories must be scoped to the selected directory'
    app.directory = str(profiles)
    app.refresh_directory()
    assert app.categories()[0]['name'] == 'Fine art papers'
    app.make_default.set(True)
    app.save_default_directory()
    app.theme_choice.set('Windows Light')
    app.change_theme()
    assert m.read_settings()['profile_categories']
    app.destroy()
    reopened = m.Inspector()
    assert reopened.categories()[0]['name'] == 'Fine art papers'
    assert len(reopened.categories()[0]['files']) == 2
    assert not reopened.profile_list.item(item, 'open')
    reopened.destroy()
    print('PASS: checkboxes, checked category creation, actual drag/drop bindings, inline rename, expansion persistence, directory scoping, failed-save rollback, unchanged files and restart persistence')
