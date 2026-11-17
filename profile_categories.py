"""Virtual profile categories, checkbox selection, and tree drag-and-drop."""
from copy import deepcopy
from pathlib import Path
import os
import uuid
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox


def directory_key(directory):
    return os.path.normcase(os.path.abspath(directory))


class ProfileCategories:
    def setup_categories(self, stored):
        self.category_store = stored if isinstance(stored, dict) else {}
        self.checked_profiles = set()
        self.category_rows = {}
        self.category_editor = None
        self.profile_drag = None
        self.drop_target = None
        tree = self.profile_list
        tree.bind('<Button-1>', self.library_click)
        tree.bind('<B1-Motion>', self.library_drag)
        tree.bind('<ButtonRelease-1>', self.library_drop)
        tree.bind('<Double-1>', self.library_double_click)
        tree.bind('<space>', self.library_space)
        tree.bind('<F2>', self.rename_selected_category)
        tree.bind('<Escape>', self.cancel_profile_drag)
        tree.bind('<<TreeviewOpen>>', self.remember_category_expansion)
        tree.bind('<<TreeviewClose>>', self.remember_category_expansion)

    def categories(self):
        raw = self.category_store.get(directory_key(self.directory), [])
        if not isinstance(raw, list):
            return []
        result = []
        used = set()
        for value in raw:
            if not isinstance(value, dict):
                continue
            key, name, files = value.get('id'), value.get('name'), value.get('files', [])
            if not isinstance(key, str) or not key or key in used or not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(files, list):
                files = []
            result.append({'id': key, 'name': name, 'files': [f for f in files if isinstance(f, str) and Path(f).name == f],
                           'open': bool(value.get('open', True))})
            used.add(key)
        return result

    def commit_categories(self, categories):
        candidate = deepcopy(self.category_store)
        candidate[directory_key(self.directory)] = categories
        try:
            self.save_category_settings(candidate)
        except OSError as exc:
            messagebox.showerror('Categories could not be saved', str(exc), parent=self)
            return False
        self.category_store = candidate
        return True

    def render_library(self, rows):
        tree = self.profile_list
        self.library_rows = list(rows)
        if tree.exists('uncategorized'):
            self.uncategorized_open = bool(tree.item('uncategorized', 'open'))
        self.cancel_category_editor()
        for item in tree.get_children():
            tree.delete(item)
        self.list_paths = {}
        self.category_rows = {}
        categories = self.categories()
        membership = {}
        for category in categories:
            item = 'category:' + category['id']
            self.category_rows[item] = category['id']
            tree.insert('', 'end', iid=item, values=(category['name'], '', '', '', 'Category'), open=category['open'])
            for filename in category['files']:
                membership.setdefault(filename.casefold(), item)
        tree.insert('', 'end', iid='uncategorized', values=('Uncategorized', '', '', '', 'Default group'),
                    open=getattr(self, 'uncategorized_open', True))
        present = set()
        for index, (path, values) in enumerate(self.library_rows):
            item = 'profile:' + str(index)
            is_profile = path.suffix.lower() in ('.icc', '.icm') and path.is_file()
            parent = membership.get(path.name.casefold(), 'uncategorized') if is_profile else 'uncategorized'
            self.list_paths[item] = path
            present.add(str(path))
            mark = ('☑' if str(path) in self.checked_profiles else '☐') if is_profile else ''
            tree.insert(parent, 'end', iid=item, text=mark, values=values)
        self.checked_profiles.intersection_update(present)
        for item in [*self.category_rows, 'uncategorized']:
            count = len(tree.get_children(item))
            tree.set(item, 'status', f'{count} items' if item == 'uncategorized' else f'Category • {count} profiles')
        self.update_checked_label()

    def update_checked_label(self):
        self.checked_label.config(text=f'{len(self.checked_profiles)} checked')

    def toggle_profile_check(self, item):
        path = self.list_paths.get(item)
        if path is None or path.suffix.lower() not in ('.icc', '.icm') or not path.is_file():
            return
        key = str(path)
        if key in self.checked_profiles:
            self.checked_profiles.remove(key)
        else:
            self.checked_profiles.add(key)
        self.profile_list.item(item, text='☑' if key in self.checked_profiles else '☐')
        self.update_checked_label()

    def check_all_profiles(self):
        items = [item for item, path in self.list_paths.items() if path.suffix.lower() in ('.icc', '.icm') and path.is_file()]
        should_check = any(str(self.list_paths[item]) not in self.checked_profiles for item in items)
        for item in items:
            path = str(self.list_paths[item])
            self.checked_profiles.add(path) if should_check else self.checked_profiles.discard(path)
            self.profile_list.item(item, text='☑' if should_check else '☐')
        self.update_checked_label()

    def clear_profile_checks(self):
        self.checked_profiles.clear()
        for item, path in self.list_paths.items():
            if path.suffix.lower() in ('.icc', '.icm') and path.is_file():
                self.profile_list.item(item, text='☐')
        self.update_checked_label()

    def category_name(self, name, exclude=None):
        if name is None:
            return None
        name = name.strip()
        if not name or len(name) > 100:
            messagebox.showerror('Invalid category name', 'Enter a category name between 1 and 100 characters.', parent=self)
            return None
        if name.casefold() == 'uncategorized' or any(c['id'] != exclude and c['name'].casefold() == name.casefold() for c in self.categories()):
            messagebox.showerror('Category already exists', 'Choose a different category name.', parent=self)
            return None
        return name

    def create_category(self):
        name = self.category_name(simpledialog.askstring('Create category',
            f'Category name:\n{len(self.checked_profiles)} checked profile(s) will be added.', parent=self))
        if name is None:
            return
        categories = self.categories()
        selected = {Path(p).name.casefold() for p in self.checked_profiles}
        for category in categories:
            category['files'] = [f for f in category['files'] if f.casefold() not in selected]
        category = {'id': uuid.uuid4().hex, 'name': name,
                    'files': sorted(Path(p).name for p in self.checked_profiles), 'open': True}
        categories.append(category)
        if self.commit_categories(categories):
            self.checked_profiles.clear()
            self.refresh_directory()
            self.profile_list.selection_set('category:' + category['id'])

    def move_profiles_to_category(self, paths, category_id):
        categories = self.categories()
        if category_id is not None and not any(c['id'] == category_id for c in categories):
            return False
        available = {str(p): p for p in self.list_paths.values() if p.is_file() and p.suffix.lower() in ('.icc', '.icm')}
        filenames = {available[str(p)].name for p in paths if str(p) in available}
        if not filenames:
            return False
        selected = {name.casefold() for name in filenames}
        for category in categories:
            category['files'] = [f for f in category['files'] if f.casefold() not in selected]
            if category['id'] == category_id:
                category['files'].extend(sorted(filenames))
                category['open'] = True
        if self.commit_categories(categories):
            self.checked_profiles.difference_update(str(p) for p in paths)
            self.refresh_directory()
            return True
        return False

    def library_click(self, event):
        tree = self.profile_list
        item = tree.identify_row(event.y)
        column = tree.identify_column(event.x)
        self.profile_drag = None
        if not item:
            return
        if item in self.list_paths:
            path = self.list_paths[item]
            if column == '#0':
                tree.selection_set(item)
                tree.focus(item)
                self.toggle_profile_check(item)
                return 'break'
            if path.is_file() and path.suffix.lower() in ('.icc', '.icm'):
                self.profile_drag = (item, event.x, event.y, False)
        elif item in self.category_rows and column == '#1':
            tree.selection_set(item)
            tree.focus(item)
            self.begin_category_rename(item)
            return 'break'

    def library_space(self, event):
        self.toggle_profile_check(self.profile_list.focus())
        return 'break'

    def library_double_click(self, event):
        tree = self.profile_list
        item = tree.identify_row(event.y)
        if tree.identify_column(event.x) == '#0':
            return 'break'
        if item in self.category_rows or item == 'uncategorized':
            tree.item(item, open=not tree.item(item, 'open'))
            self.remember_category_expansion()
            return 'break'
        if item in self.list_paths:
            tree.selection_set(item)
            self.open_list_selection()
        return 'break'

    def library_drag(self, event):
        if self.profile_drag is None:
            return
        item, x, y, started = self.profile_drag
        if not started and abs(event.x-x) + abs(event.y-y) < 8:
            return
        self.profile_drag = (item, x, y, True)
        tree = self.profile_list
        tree.configure(cursor='fleur')
        self.drop_target = self.drop_destination(event)
        for group in [*self.category_rows, 'uncategorized']:
            tree.item(group, tags=('drop_target',) if group == self.drop_target else ())
        if event.y < 35:
            tree.yview_scroll(-1, 'units')
        elif event.y > tree.winfo_height()-25:
            tree.yview_scroll(1, 'units')
        return 'break'

    def library_drop(self, event):
        drag, target = self.profile_drag, self.drop_destination(event)
        self.profile_drag = self.drop_target = None
        tree = self.profile_list
        tree.configure(cursor='')
        for group in [*self.category_rows, 'uncategorized']:
            if tree.exists(group):
                tree.item(group, tags=())
        if drag and drag[3] and target:
            path = self.list_paths.get(drag[0])
            if path:
                paths = list(self.checked_profiles) if str(path) in self.checked_profiles else [str(path)]
                self.move_profiles_to_category(paths, self.category_rows.get(target))
            return 'break'

    def drop_destination(self, event):
        tree = self.profile_list
        if not (0 <= event.x < tree.winfo_width() and 0 <= event.y < tree.winfo_height()):
            return None
        target = tree.identify_row(event.y)
        if target in self.list_paths:
            target = tree.parent(target)
        return target if target in self.category_rows or target == 'uncategorized' else None

    def cancel_profile_drag(self, event=None):
        self.profile_drag = self.drop_target = None
        self.profile_list.configure(cursor='')
        for group in [*self.category_rows, 'uncategorized']:
            if self.profile_list.exists(group):
                self.profile_list.item(group, tags=())
        return 'break'

    def rename_selected_category(self, event=None):
        selected = self.profile_list.selection()
        if selected and selected[0] in self.category_rows:
            self.begin_category_rename(selected[0])
        return 'break'

    def begin_category_rename(self, item):
        self.cancel_category_editor()
        bounds = self.profile_list.bbox(item, 'filename')
        if not bounds:
            return
        editor = ttk.Entry(self.profile_list)
        editor.insert(0, self.profile_list.set(item, 'filename'))
        editor.place(x=bounds[0], y=bounds[1], width=bounds[2], height=bounds[3])
        self.category_editor = editor
        editor.focus_set()
        editor.select_range(0, 'end')
        editor.bind('<Return>', lambda e: self.finish_category_rename(item))
        editor.bind('<Escape>', lambda e: self.cancel_category_editor())
        editor.bind('<FocusOut>', lambda e: self.finish_category_rename(item))

    def cancel_category_editor(self):
        editor, self.category_editor = self.category_editor, None
        if editor is not None:
            editor.destroy()

    def finish_category_rename(self, item):
        if self.category_editor is None:
            return 'break'
        value = self.category_editor.get()
        self.cancel_category_editor()
        key = self.category_rows.get(item)
        name = self.category_name(value, exclude=key)
        if name is not None:
            categories = self.categories()
            for category in categories:
                if category['id'] == key:
                    category['name'] = name
            if self.commit_categories(categories):
                self.profile_list.set(item, 'filename', name)
        return 'break'

    def remember_category_expansion(self, event=None):
        self.after_idle(self.save_category_expansion)

    def save_category_expansion(self):
        if not self.winfo_exists():
            return
        categories = self.categories()
        changed = False
        for category in categories:
            item = 'category:' + category['id']
            if self.profile_list.exists(item):
                opened = bool(self.profile_list.item(item, 'open'))
                if category['open'] != opened:
                    category['open'] = opened
                    changed = True
        if changed and self.commit_categories(categories):
            # Rebuild after folding so Tk repaints complete rows on Windows,
            # including checkbox glyphs and column text below a collapsed group.
            selected = self.profile_list.selection()
            position = self.profile_list.yview()[0]
            self.render_library(self.library_rows)
            for item in selected:
                if self.profile_list.exists(item):
                    self.profile_list.selection_set(item)
            self.profile_list.yview_moveto(position)
