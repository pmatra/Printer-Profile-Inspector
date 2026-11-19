"""ICC Gamut Inspector — independent profile inspector and sampled gamut viewer."""
import csv
import itertools
import json
import math
import struct
import sys
import os
import time
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from scipy.spatial import ConvexHull
from PIL import Image, ImageCms
from profile_categories import ProfileCategories
from app_support import SettingsStore, settings_path, SingleInstance, raise_existing_window, APP_TITLE, color_directory, recycle_profile, install_profile
from icc_tags import decode_tag, TAG_NAMES
from ui_style import system_font, shaded_buttons
try:
    from gamut_gpu import GamutGPU
    GPU_IMPORT_ERROR = ''
except ImportError as exc:
    GamutGPU = None
    GPU_IMPORT_ERROR = str(exc)

INTENTS = ['Perceptual', 'Relative colorimetric', 'Saturation', 'Absolute colorimetric']
DEFAULT_DIRECTORY = color_directory()
LEGACY_SETTINGS_PATH = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent / 'settings.json'
SETTINGS_PATH = settings_path()
SETTINGS_NOTICES = []
THEMES = ('Windows Light', 'Windows Dark', 'Follow Windows')

def read_settings():
    try:
        return SettingsStore(SETTINGS_PATH, LEGACY_SETTINGS_PATH if SETTINGS_PATH == settings_path() else None, SETTINGS_NOTICES).read()
    except OSError as exc:
        SETTINGS_NOTICES.append(f'Settings could not be read at {SETTINGS_PATH}: {exc}. Existing files were preserved; defaults are in use.')
        return {}

def save_setting(key, value):
    SettingsStore(SETTINGS_PATH, LEGACY_SETTINGS_PATH if SETTINGS_PATH == settings_path() else None, SETTINGS_NOTICES).update(key, value)

def windows_is_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
    except (ImportError, OSError):
        return False

def created_date(data):
    parts = struct.unpack_from('>6H', data, 24)
    try:
        return datetime(*parts).strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        return 'Unspecified / invalid'

def directory_entries(directory):
    rows = []
    for path in sorted(Path(directory).iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
        version = space = created = ''
        status = 'Folder' if path.is_dir() else 'Other file'
        if path.is_file() and path.suffix.lower() in ('.icc', '.icm'):
            try:
                data, fields, tags = read_profile(path)
                version = dict(fields)['Version']
                space = dict(fields)['Device color space']
                created = created_date(data)
                status = 'ICC profile'
            except (OSError, ValueError, struct.error) as exc:
                status = f'Unreadable profile: {exc}'
        rows.append((path, (path.name, version, space, created, status)))
    return rows

def read_profile(path):
    data = Path(path).read_bytes()
    if len(data) < 132 or data[36:40] != b'acsp':
        raise ValueError('This is not a complete ICC profile (missing acsp signature).')
    u32 = lambda p: struct.unpack_from('>I', data, p)[0]
    size = u32(0)
    if size < 132 or size > len(data):
        raise ValueError('Invalid declared profile size.')
    count = u32(128)
    if count > (size - 132) // 12:
        raise ValueError('Tag table extends beyond the profile.')
    tags = []
    for i in range(count):
        p = 132 + i * 12
        sig = data[p:p+4].decode('ascii', 'replace')
        off, length = u32(p+4), u32(p+8)
        if off < 128 or off + length > size or length < 8:
            raise ValueError(f'Tag {sig} has invalid bounds.')
        tags.append((sig, data[off:off+4].decode('ascii', 'replace'), off, length))
    text = lambda p: data[p:p+4].decode('ascii', 'replace').strip()
    fields = [('File', str(path)), ('Profile size', f'{size:,} bytes'),
              ('Version', f'{data[8]}.{data[9] >> 4}.{data[9] & 15}'),
              ('Device class', text(12)), ('Device color space', text(16)),
              ('Connection space', text(20)), ('Created', created_date(data)),
              ('Platform', text(40)), ('Manufacturer', text(48)), ('Model', text(52)),
              ('Default intent', str(u32(64))), ('Creator', text(80)), ('Tag count', str(count))]
    return data, fields, tags

def sample_gamut(path, intent=1, density=9):
    data, fields, tags = read_profile(path)
    mode = data[16:20].decode('ascii').strip()
    channels = {'RGB': 3, 'CMYK': 4, 'GRAY': 1}.get(mode)
    if channels is None:
        raise ValueError(f'3D sampling supports RGB, CMYK and GRAY; this profile uses {mode}. Header and tags remain available.')
    pilmode = 'L' if mode == 'GRAY' else mode
    values = np.rint(np.linspace(0, 255, density)).astype(np.uint8)
    device = np.array(list(itertools.product(values, repeat=channels)), dtype=np.uint8)
    image = Image.frombytes(pilmode, (len(device), 1), device.tobytes())
    labprofile = ImageCms.createProfile('LAB')
    transform = ImageCms.buildTransform(str(path), labprofile, pilmode, 'LAB', renderingIntent=intent)
    encoded = ImageCms.applyTransform(image, transform)
    packed = np.asarray(encoded).reshape(-1, 3)
    lab = packed.astype(float)
    lab[:, 0] *= 100 / 255
    # Pillow's NumPy buffer exposes a/b as signed bytes stored in uint8,
    # unlike getpixel(), which returns the ICC offset-binary representation.
    lab[:, 1:] = packed[:, 1:].view(np.int8).astype(float)
    rgb_transform = ImageCms.buildTransform(labprofile, ImageCms.createProfile('sRGB'), 'LAB', 'RGB')
    rgb = np.asarray(ImageCms.applyTransform(encoded, rgb_transform)).reshape(-1, 3)
    # Lab plotting coordinates: a*, b*, L* centered at 50.
    points = lab[:, [1, 2, 0]].copy()
    points[:, 2] -= 50
    hull = None
    if channels > 1:
        hull = ConvexHull(points)
    return {'path': str(path), 'lab': lab, 'points': points, 'rgb': rgb,
            'hull': hull, 'samples': len(points), 'intent': intent}

@lru_cache(maxsize=4)
def cached_sample(path, modified, size, intent, density):
    return sample_gamut(path, intent, density)

def display_indices(result, maximum):
    cache = result.setdefault('display_indices', {})
    if maximum not in cache:
        count = len(result['points'])
        hull = result['hull']
        boundary = hull.vertices if hull is not None else np.array([], dtype=int)
        if len(boundary) >= maximum:
            indices = boundary[np.linspace(0,len(boundary)-1,maximum).astype(int)]
        elif count > maximum:
            regular = np.linspace(0,count-1,maximum-len(boundary)).astype(int)
            indices = np.unique(np.concatenate((boundary,regular)))
        else:
            indices = np.arange(count)
        cache[maximum] = indices
    return cache[maximum]

class Inspector(ProfileCategories, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='icc-sampling')
        self.jobs = []
        self.job_generation = {'primary':0, 'comparison':0}
        self.closing = False
        self.draw_pending = None
        self.detail_pending = None
        self.interacting = False
        self.tag_curves = []
        self.geometry('1280x820')
        self.minsize(980, 650)
        self.configure(bg='#111720')
        preference = read_settings().get('theme', 'Follow Windows')
        self.theme_choice = tk.StringVar(value=preference if preference in THEMES else 'Follow Windows')
        self.active_dark = None
        style = ttk.Style(self)
        self.ui_family, self.ui_size = system_font(self)
        style.theme_use('clam')
        style.configure('.', background='#1c2532', foreground='#e3eaf4', font=(self.ui_family, self.ui_size))
        style.configure('TButton', padding=8)
        style.map('TCombobox', fieldbackground=[('readonly', '#26374b')], foreground=[('readonly','#e3eaf4')])
        style.configure('TNotebook.Tab', background='#26374b', padding=(10, 7))
        style.map('TNotebook.Tab', background=[('selected','#34577c')])
        style.configure('Treeview', background='#16202d', fieldbackground='#16202d', rowheight=27)
        style.map('Treeview', background=[('selected', '#34577c')])
        self.primary = self.comparison = None
        self.path = None
        self.yaw, self.pitch, self.zoom = .65, -.35, 1.8
        self.intent = tk.StringVar(value=INTENTS[1])
        self.density = tk.StringVar(value='17')
        self.render_mode = tk.StringVar(value='High GPU')
        self.gpu = None
        self.view = tk.StringVar(value='Surface')
        self.xray = tk.BooleanVar(value=True)
        self.main_tabs = ttk.Notebook(self)
        self.main_tabs.pack(fill='both', expand=True, padx=8, pady=8)
        self.inspector_tab = ttk.Frame(self.main_tabs)
        self.list_tab = ttk.Frame(self.main_tabs)
        self.main_tabs.add(self.inspector_tab, text='ICC/Gamut Inspector')
        self.main_tabs.add(self.list_tab, text='Profile List')
        bar = ttk.Frame(self.inspector_tab, padding=12); bar.pack(fill='x')
        ttk.Label(bar, text='ICC / GAMUT INSPECTOR', font=(self.ui_family, 17, 'bold')).pack(side='left', padx=(0, 25))
        ttk.Button(bar, text='Open profile…', command=self.open).pack(side='left', padx=4)
        ttk.Button(bar, text='Compare…', command=lambda: self.open(True)).pack(side='left', padx=4)
        ttk.Button(bar, text='Clear comparison', command=self.clear).pack(side='left', padx=4)
        ttk.Button(bar, text='Export samples…', command=self.export).pack(side='right')
        self.subtitle = ttk.Label(self.inspector_tab, text='Open an ICC / ICM printer or RGB profile to begin.', padding=(16, 4))
        self.subtitle.pack(fill='x')
        controls = ttk.Frame(self.inspector_tab, padding=12); controls.pack(fill='x')
        for label, var, values, width in [('Intent', self.intent, INTENTS, 25), ('Grid / channel', self.density, ['5','9','13','17','21'], 5), ('View', self.view, ['Surface','Points','Wireframe'], 12)]:
            ttk.Label(controls, text=label).pack(side='left', padx=(8, 6))
            box = ttk.Combobox(controls, textvariable=var, values=values, state='readonly', width=width)
            box.pack(side='left'); box.bind('<<ComboboxSelected>>', self.changed)
        ttk.Button(controls, text='Reset view', command=self.reset).pack(side='right')
        render_controls = ttk.Frame(self.inspector_tab, padding=(20, 0, 12, 6))
        render_controls.pack(fill='x')
        ttk.Label(render_controls, text='Renderer').pack(side='left', padx=(0, 8))
        renderer_box = ttk.Combobox(render_controls, textvariable=self.render_mode,
                                   values=['High GPU', 'Basic CPU'], state='readonly', width=14)
        renderer_box.pack(side='left')
        renderer_box.bind('<<ComboboxSelected>>', self.select_renderer)
        ttk.Checkbutton(render_controls, text='X-ray comparison', variable=self.xray, command=self.draw).pack(side='left', padx=10)
        self.gpu_label = ttk.Label(render_controls, text='Initializing hardware OpenGL…', padding=(12, 0))
        self.gpu_label.pack(side='left')
        self.legend = ttk.Label(self.inspector_tab, padding=(20,4), wraplength=1100)
        self.legend.pack(fill='x')
        split = ttk.Panedwindow(self.inspector_tab, orient='horizontal'); split.pack(fill='both', expand=True, padx=12)
        tabs = ttk.Notebook(split); split.add(tabs, weight=1)
        info = ttk.Frame(tabs); tabs.add(info, text='Profile header')
        self.header = tk.Text(info, wrap='word', bg='#16202d', fg='#e3eaf4', relief='flat', width=36, font=(self.ui_family, self.ui_size), padx=12, pady=12)
        self.header.pack(fill='both', expand=True)
        tagpage = ttk.Frame(tabs); tabs.add(tagpage, text='ICC tags')
        self.tags = ttk.Treeview(tagpage, columns=('description','type','size'), show='tree headings', height=5)
        self.tags.heading('#0', text='Tag'); self.tags.column('#0', width=70)
        for col in ('description','type','size'):
            self.tags.heading(col, text=col.title()); self.tags.column(col, width=80)
        self.tags.column('description',width=145)
        self.tags.pack(fill='x'); self.tags.bind('<<TreeviewSelect>>', self.tag_selected)
        details_tabs = ttk.Notebook(tagpage)
        details_tabs.pack(fill='both',expand=True)
        decoded = ttk.Frame(details_tabs); raw_frame = ttk.Frame(details_tabs)
        details_tabs.add(decoded,text='Decoded tag'); details_tabs.add(raw_frame,text='Raw bytes')
        self.tag_details = tk.Text(decoded, wrap='word', width=36, height=6, font=(self.ui_family, self.ui_size))
        self.tag_details.grid(row=0,column=0,sticky='nsew')
        self.tag_plot = tk.Canvas(decoded,height=150,highlightthickness=0)
        self.tag_plot.grid(row=1,column=0,sticky='nsew')
        decoded.columnconfigure(0,weight=1)
        decoded.rowconfigure(0,weight=1); decoded.rowconfigure(1,weight=2)
        self.tag_plot.bind('<Configure>',lambda e:self.render_tag_plot())
        self.raw = tk.Text(raw_frame, bg='#16202d', fg='#c2d3e7', wrap='none', width=36, font=('Consolas',9))
        self.raw.pack(fill='both', expand=True)
        right = ttk.Frame(split); split.add(right, weight=3)
        self.render_host = right
        self.canvas = tk.Canvas(right, bg='#0c121c', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<ButtonPress-1>', lambda e: setattr(self, 'drag', (e.x, e.y)))
        self.canvas.bind('<B1-Motion>', self.rotate)
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Motion>', self.hover)
        self.status = ttk.Label(self.inspector_tab, text='Drag to rotate • Scroll to zoom • Hover a point for Lab values', padding=12)
        self.status.pack(fill='x')
        self.bind('<Control-o>', lambda e: self.open())
        self.build_list_tab()
        self.settings_menu = tk.Menu(self, tearoff=False)
        self.theme_menu = tk.Menu(self.settings_menu, tearoff=False)
        for name in THEMES:
            self.theme_menu.add_radiobutton(label=name, variable=self.theme_choice, value=name,
                                           command=self.change_theme)
        self.settings_menu.add_cascade(label='Theme', menu=self.theme_menu)
        self.gear_button = ttk.Button(self, text='⚙', width=3, command=self.show_settings,
                                      takefocus=True)
        self.gear_button.place(relx=1, x=-14, y=10, anchor='ne')
        self.bind('<Control-comma>', lambda e: self.show_settings())
        self.apply_theme()
        self.select_renderer()
        self.after(1500, self.watch_windows_theme)
        self.after(30, self.poll_jobs)
        self.after_idle(self.report_settings_recovery)

    def report_settings_recovery(self):
        if SETTINGS_NOTICES:
            notices = list(dict.fromkeys(SETTINGS_NOTICES)); SETTINGS_NOTICES.clear()
            messagebox.showwarning('Settings recovery / migration', '\n\n'.join(notices), parent=self)

    def destroy(self):
        self.closing = True
        for future, *_ in self.jobs: future.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    def schedule_draw(self):
        if self.draw_pending is None:
            self.draw_pending = self.after(25, self.flush_draw)

    def point_indices(self,result,maximum):
        return display_indices(result,maximum)

    def flush_draw(self):
        self.draw_pending = None
        self.draw()

    def show_settings(self):
        self.settings_menu.tk_popup(self.gear_button.winfo_rootx(),
                                    self.gear_button.winfo_rooty() + self.gear_button.winfo_height())

    def select_renderer(self, event=None):
        if self.render_mode.get() == 'High GPU':
            if GamutGPU is None:
                self.gpu_failed(f'OpenGL libraries are unavailable: {GPU_IMPORT_ERROR}')
                return
            if self.gpu is None:
                try:
                    self.gpu = GamutGPU(self.render_host, self)
                except Exception as exc:
                    self.gpu_failed(str(exc))
                    return
            if self.gpu.failed:
                self.gpu_failed('The OpenGL viewport could not initialize. Restart after updating your graphics driver.')
                return
            self.canvas.pack_forget()
            self.gpu.pack(fill='both', expand=True)
        else:
            if self.gpu is not None:
                self.gpu.pack_forget()
            self.canvas.pack(fill='both', expand=True)
            self.gpu_label.config(text='Basic CPU • Flat triangle rendering')
        self.draw()

    def gpu_failed(self, reason):
        self.render_mode.set('Basic CPU')
        self.select_renderer()
        self.gpu_label.config(text=f'Basic CPU fallback • {reason}', wraplength=650)

    def viewport_size(self):
        widget = self.gpu if self.render_mode.get() == 'High GPU' and self.gpu is not None else self.canvas
        return max(1, widget.winfo_width()), max(1, widget.winfo_height())

    def change_theme(self):
        try:
            save_setting('theme', self.theme_choice.get())
        except OSError as exc:
            messagebox.showerror('Theme preference could not be saved', str(exc))
        self.apply_theme()

    def watch_windows_theme(self):
        if self.theme_choice.get() == 'Follow Windows':
            dark = windows_is_dark()
            if dark != self.active_dark:
                self.apply_theme()
        self.after(1500, self.watch_windows_theme)

    def apply_theme(self):
        self.active_dark = (windows_is_dark() if self.theme_choice.get() == 'Follow Windows'
                            else self.theme_choice.get() == 'Windows Dark')
        if self.active_dark:
            self.colors = dict(bg='#202020', panel='#292929', field='#1b1b1b', text='#f2f2f2',
                               muted='#bfbfbf', border='#555555', hover='#3c3c3c', selected='#005a9e',
                               selection_text='#ffffff', plot='#181818', axis='#999999', wire='#aaaaaa',
                               compare='#61d6e8')
        else:
            self.colors = dict(bg='#f3f3f3', panel='#fafafa', field='#ffffff', text='#202020',
                               muted='#595959', border='#b5b5b5', hover='#e5e5e5', selected='#cce8ff',
                               selection_text='#202020', plot='#ffffff', axis='#707070', wire='#626262',
                               compare='#006879')
        p = self.colors
        style = ttk.Style(self)
        style.configure('.', background=p['bg'], foreground=p['text'], bordercolor=p['border'],
                        lightcolor=p['bg'], darkcolor=p['border'], font=(self.ui_family, self.ui_size))
        style.configure('TButton', background=p['panel'], foreground=p['text'], padding=8)
        shaded_buttons(self, style, p, self.active_dark)
        style.configure('TNotebook', background=p['bg'])
        style.configure('TNotebook.Tab', background=p['panel'], foreground=p['text'], padding=(10,7))
        style.map('TNotebook.Tab', background=[('selected',p['selected']), ('active',p['hover'])],
                  foreground=[('selected',p['selection_text'])])
        style.configure('Treeview', background=p['field'], fieldbackground=p['field'],
                        foreground=p['text'], rowheight=27)
        style.configure('Treeview.Heading', background=p['panel'], foreground=p['text'])
        style.map('Treeview', background=[('selected',p['selected'])],
                  foreground=[('selected',p['selection_text'])])
        style.map('Treeview.Heading', background=[('active',p['hover'])])
        style.configure('TCombobox', fieldbackground=p['field'], foreground=p['text'], arrowcolor=p['text'])
        style.map('TCombobox', fieldbackground=[('readonly',p['field'])],
                  foreground=[('readonly',p['text']), ('disabled',p['muted'])],
                  selectbackground=[('readonly',p['selected'])], selectforeground=[('readonly',p['selection_text'])])
        style.configure('TCheckbutton', background=p['bg'], foreground=p['text'])
        style.configure('TEntry', fieldbackground=p['field'], foreground=p['text'], insertcolor=p['text'])
        style.map('TCheckbutton', background=[('active',p['hover'])])
        style.configure('Vertical.TScrollbar', background=p['panel'], troughcolor=p['bg'], arrowcolor=p['text'])
        style.configure('Horizontal.TScrollbar', background=p['panel'], troughcolor=p['bg'], arrowcolor=p['text'])
        self.configure(bg=p['bg'])
        for text in (self.header, self.raw, self.tag_details):
            text.configure(bg=p['field'], fg=p['text'], insertbackground=p['text'],
                           selectbackground=p['selected'], selectforeground=p['selection_text'])
        self.canvas.configure(bg=p['plot'])
        self.tag_plot.configure(bg=p['field'])
        self.render_tag_plot()
        self.profile_list.tag_configure('category_header', background=('#343b43' if self.active_dark else '#e7edf3'),
                                        foreground=p['text'], font=(self.ui_family,self.ui_size,'bold'))
        self.profile_list.tag_configure('drop_target', background=p['selected'], foreground=p['selection_text'])
        for menu in (self.settings_menu, self.theme_menu, self.profile_menu):
            menu.configure(background=p['panel'], foreground=p['text'], activebackground=p['selected'],
                           activeforeground=p['selection_text'], selectcolor=p['text'])
        self.option_add('*TCombobox*Listbox.background', p['field'])
        self.option_add('*TCombobox*Listbox.foreground', p['text'])
        self.option_add('*TCombobox*Listbox.selectBackground', p['selected'])
        self.option_add('*TCombobox*Listbox.selectForeground', p['selection_text'])
        self.update_idletasks()
        if sys.platform == 'win32':
            try:
                import ctypes
                get_parent = ctypes.windll.user32.GetParent
                get_parent.argtypes = [ctypes.c_void_p]
                get_parent.restype = ctypes.c_void_p
                hwnd = get_parent(self.winfo_id())
                dark = ctypes.c_int(self.active_dark)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20,
                                                          ctypes.byref(dark), ctypes.sizeof(dark))
            except (AttributeError, OSError):
                pass
        self.draw()

    def build_list_tab(self):
        self.default_directory = str(DEFAULT_DIRECTORY)
        try:
            settings = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
            saved = settings.get('default_directory')
            if isinstance(saved, str) and saved:
                self.default_directory = saved
        except (OSError, ValueError, AttributeError):
            pass
        self.directory = self.default_directory
        toolbar = ttk.Frame(self.list_tab, padding=12)
        toolbar.pack(fill='x')
        ttk.Button(toolbar, text='Open Directory…', command=self.open_directory).pack(side='left')
        self.make_default = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text='Make this directory default', variable=self.make_default,
                        command=self.save_default_directory).pack(side='left', padx=16)
        ttk.Button(toolbar, text='Refresh', command=self.refresh_directory).pack(side='left')
        ttk.Button(toolbar, text='Open selected profile', command=self.open_list_selection).pack(side='right')
        search_bar = ttk.Frame(self.list_tab,padding=(12,0,12,6)); search_bar.pack(fill='x')
        ttk.Label(search_bar,text='Search').pack(side='left',padx=(0,8))
        self.search_text = tk.StringVar()
        ttk.Entry(search_bar,textvariable=self.search_text).pack(side='left',fill='x',expand=True)
        ttk.Button(search_bar,text='Clear',command=lambda:self.search_text.set('')).pack(side='left',padx=8)
        ttk.Button(search_bar,text='Install Profile…',command=self.install_selected_profile).pack(side='right')
        self.search_pending = None
        self.search_text.trace_add('write',self.search_changed)
        category_bar = ttk.Frame(self.list_tab, padding=(12, 0, 12, 6))
        category_bar.pack(fill='x')
        ttk.Button(category_bar, text='Create category from checked…', command=self.create_category).pack(side='left')
        ttk.Button(category_bar, text='Rename category', command=self.rename_selected_category).pack(side='left', padx=8)
        ttk.Button(category_bar, text='Clear checks', command=self.clear_profile_checks).pack(side='left')
        self.checked_label = ttk.Label(category_bar, text='0 checked', padding=(12, 0))
        self.checked_label.pack(side='left')
        self.directory_label = ttk.Label(self.list_tab, padding=(12, 4), wraplength=1000)
        self.directory_label.pack(fill='x')
        frame = ttk.Frame(self.list_tab, padding=12)
        frame.pack(fill='both', expand=True)
        columns = ('filename', 'version', 'space', 'created', 'status')
        self.profile_list = ttk.Treeview(frame, columns=columns, show='tree headings', selectmode='browse')
        self.profile_list.heading('#0', text='Check', command=self.check_all_profiles)
        self.profile_list.column('#0', width=85, minwidth=70, stretch=False)
        for column, title, width in zip(columns, ['Filename', 'Version', 'Device color space', 'Created', 'Status'], [340, 85, 150, 180, 230]):
            self.profile_list.heading(column, text=title, command=lambda c=column: self.sort_directory(c))
            self.profile_list.column(column, width=width, minwidth=75)
        vertical = ttk.Scrollbar(frame, orient='vertical', command=self.profile_list.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.profile_list.xview)
        self.profile_list.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.profile_list.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns'); horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        self.profile_list.bind('<Return>', self.open_list_selection)
        self.profile_menu = tk.Menu(self, tearoff=False)
        self.profile_list.bind('<Button-3>', self.show_profile_menu)
        self.directory_status = ttk.Label(self.list_tab, padding=12)
        self.directory_status.pack(fill='x')
        self.sort_reverse = {}
        saved_sort = read_settings().get('profile_sort',{})
        self.active_sort_column = saved_sort.get('column','filename') if isinstance(saved_sort,dict) else 'filename'
        if self.active_sort_column not in columns: self.active_sort_column = 'filename'
        self.active_sort_reverse = bool(saved_sort.get('reverse',False)) if isinstance(saved_sort,dict) else False
        self.sort_clicked = bool(saved_sort)
        self.setup_categories(read_settings().get('profile_categories', {}))
        self.refresh_directory()

    def save_category_settings(self, value):
        save_setting('profile_categories', value)

    def search_changed(self,*args):
        if self.search_pending is not None: self.after_cancel(self.search_pending)
        self.search_pending = self.after(150,self.apply_search)

    def apply_search(self):
        self.search_pending = None
        self.render_library(self.library_rows)
        self.directory_status.config(text=f'{len(self.list_paths)} matching items • {len(self.checked_profiles)} checked (including hidden matches). Clear Search to show every profile.')

    def install_selected_profile(self):
        selected = filedialog.askopenfilename(title='Install ICC profile into Windows', filetypes=[('ICC profiles','*.icc *.icm')])
        if not selected: return
        path = Path(selected).resolve()
        try:
            read_profile(path); ImageCms.getOpenProfile(str(path))
            destination = install_profile(path)
        except PermissionError:
            if messagebox.askyesno('Administrator approval required', 'Windows requires administrator approval to install this profile. Request approval now?', default=messagebox.NO,parent=self):
                self.install_elevated(path)
            return
        except Exception as exc:
            messagebox.showerror('Profile was not installed',str(exc),parent=self); return
        self.install_finished(destination)

    def install_finished(self,destination):
        self.directory = str(DEFAULT_DIRECTORY)
        self.search_text.set('')
        self.make_default.set(Path(self.directory)==Path(self.default_directory))
        self.refresh_directory()
        messagebox.showinfo('Profile installed',f'Installed in the Windows color directory:\n\n{destination}\n\nNo printer default or device association was changed.',parent=self)

    def install_elevated(self,path):
        import ctypes
        result = Path(tempfile.mkdtemp(prefix='icc-install-'))/'result.json'
        args = (['--install-profile',str(path),'--install-result',str(result)] if getattr(sys,'frozen',False)
                else [str(Path(__file__).resolve()),'--install-profile',str(path),'--install-result',str(result)])
        shell = ctypes.WinDLL('shell32',use_last_error=True)
        shell.ShellExecuteW.argtypes = [ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]
        shell.ShellExecuteW.restype = ctypes.c_void_p
        code = shell.ShellExecuteW(None,'runas',sys.executable,subprocess.list2cmdline(args),None,0)
        if not code or code<=32:
            messagebox.showerror('Profile was not installed','Administrator approval was cancelled or unavailable.',parent=self); return
        def poll(deadline):
            if result.exists():
                report=json.loads(result.read_text(encoding='utf-8'))
                if report['ok']: self.install_finished(report['destination'])
                else: messagebox.showerror('Profile was not installed',report['error'],parent=self)
            elif time.monotonic()<deadline: self.after(300,lambda:poll(deadline))
            else: messagebox.showerror('Install status unavailable','Windows did not return an installation result. Refresh the profile list before trying again.',parent=self)
        poll(time.monotonic()+120)

    def open_directory(self):
        selected = filedialog.askdirectory(title='Open profile directory', initialdir=self.directory)
        if selected:
            self.directory = selected
            # Choosing a folder does not silently overwrite a saved default.
            self.make_default.set(Path(selected) == Path(self.default_directory))
            self.refresh_directory()

    def save_default_directory(self):
        new_default = self.directory if self.make_default.get() else str(DEFAULT_DIRECTORY)
        try:
            save_setting('default_directory', new_default)
            self.default_directory = new_default
            self.make_default.set(Path(self.directory) == Path(new_default))
            self.directory_status.config(text=f'Default directory saved: {new_default}')
        except OSError as exc:
            self.make_default.set(Path(self.directory) == Path(self.default_directory))
            messagebox.showerror('Default directory could not be saved', str(exc))

    def refresh_directory(self):
        self.directory_label.config(text=self.directory)
        try:
            rows = directory_entries(self.directory)
            self.render_library(rows)
            count = sum(values[-1] == 'ICC profile' for _, values in rows)
            self.directory_status.config(text=f'{len(rows)} items • {count} ICC profiles • Check profiles to create a category, or drag profiles onto a category. Click a category name to rename; use its arrow to expand/collapse.')
        except OSError as exc:
            self.render_library([])
            self.directory_status.config(text=f'Cannot read directory: {exc} • Use Open Directory to choose another folder.')

    def sort_directory(self, column):
        self.active_sort_reverse = (not self.active_sort_reverse) if self.sort_clicked and column==self.active_sort_column else False
        self.active_sort_column = column; self.sort_clicked = True
        self.apply_library_sort()
        try: save_setting('profile_sort',{'column':column,'reverse':self.active_sort_reverse})
        except OSError as exc: messagebox.showerror('Sort preference could not be saved',str(exc),parent=self)

    def show_profile_menu(self, event):
        item = self.profile_list.identify_row(event.y)
        if not item:
            return
        self.profile_list.selection_set(item)
        self.profile_list.focus(item)
        self.profile_menu.delete(0, 'end')
        if item in self.category_rows:
            self.profile_menu.add_command(label='Rename category…', command=lambda: self.begin_category_rename(item))
            self.profile_menu.add_command(label='Remove category… (keep profile files)', command=lambda:self.remove_category(item))
            try:
                self.profile_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.profile_menu.grab_release()
            return
        path = self.list_paths.get(item)
        if path is None or path.suffix.lower() not in ('.icc', '.icm') or not path.is_file():
            return
        if self.profile_list.parent(item) != 'uncategorized':
            self.profile_menu.add_command(label='Move to Uncategorized', command=lambda p=path: self.move_profiles_to_category([str(p)], None))
        # Capture the clicked file so selection changes cannot redirect deletion.
        self.profile_menu.add_command(label='Move profile to Recycle Bin…', command=lambda p=path: self.delete_profile(p))
        try:
            self.profile_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.profile_menu.grab_release()

    def delete_profile(self, path):
        path = Path(path)
        if path.suffix.lower() not in ('.icc', '.icm') or not path.is_file():
            messagebox.showerror('Cannot delete profile', f'The profile is no longer available:\n\n{path}', parent=self)
            self.refresh_directory()
            return
        if not messagebox.askyesno('Delete profile?',
                                  f'Move this specific profile to the Recycle Bin?\n\n{path.name}\n\n{path}\n\nYou can restore it from the Windows Recycle Bin.',
                                  icon='warning', default=messagebox.NO, parent=self):
            return
        try:
            recycle_profile(path)
        except OSError as exc:
            messagebox.showerror('Profile could not be deleted', f'{path}\n\n{exc}', parent=self)
            return
        self.checked_profiles.discard(str(path))
        for future,slot,generation,job_path in self.jobs:
            if Path(job_path)==path:
                self.job_generation[slot]+=1; future.cancel()
        categories = self.categories()
        for category in categories:
            category['files'] = [f for f in category['files'] if f.casefold() != path.name.casefold()]
        if categories:
            self.commit_categories(categories)
        if self.path and Path(self.path) == path:
            self.path = None
            self.primary = None
            self.data = b''
            self.tagdata = []
            self.settext(self.header, 'The loaded profile was deleted.')
            self.settext(self.raw, '')
            self.settext(self.tag_details,'The loaded profile was moved to the Recycle Bin.')
            self.tag_curves=[]; self.render_tag_plot()
            for item in self.tags.get_children():
                self.tags.delete(item)
            self.subtitle.config(text='Open an ICC / ICM printer or RGB profile to begin.')
            self.status.config(text=f'Deleted profile: {path.name}')
        if self.comparison and Path(self.comparison['path']) == path:
            self.comparison = None
        self.refresh_directory()
        self.directory_status.config(text=f'Moved to Recycle Bin: {path.name}')
        self.draw()

    def open_list_selection(self, event=None):
        selected = self.profile_list.selection()
        if not selected: return
        if selected[0] in self.category_rows or selected[0] == 'uncategorized':
            self.profile_list.item(selected[0], open=not self.profile_list.item(selected[0], 'open'))
            self.remember_category_expansion()
            return
        path = self.list_paths.get(selected[0])
        if path is None:
            return
        if path.is_dir():
            self.directory = str(path)
            self.make_default.set(path == Path(self.default_directory))
            self.refresh_directory()
        elif path.suffix.lower() in ('.icc', '.icm'):
            self.main_tabs.select(self.inspector_tab)
            self.load(str(path))

    def settext(self, widget, text):
        widget.config(state='normal'); widget.delete('1.0','end'); widget.insert('1.0', text); widget.config(state='disabled')

    def open(self, compare=False):
        path = filedialog.askopenfilename(title='Choose comparison profile' if compare else 'Open ICC profile', initialdir=self.directory, filetypes=[('ICC profiles','*.icc *.icm'),('All files','*.*')])
        if path: self.load(path, compare)

    def load(self, path, compare=False, background=True):
        try:
            path = str(Path(path).resolve())
            slot = 'comparison' if compare else 'primary'
            self.job_generation[slot] += 1
            generation = self.job_generation[slot]
            for future, old_slot, *_ in self.jobs:
                if old_slot == slot: future.cancel()
            if not compare:
                data, fields, tags = read_profile(path)
                self.path, self.data, self.tagdata = path, data, tags
                self.primary = None
                self.settext(self.header, '\n\n'.join(f'{k}\n{v}' for k,v in fields))
                for item in self.tags.get_children(): self.tags.delete(item)
                for i,(sig,typ,off,size) in enumerate(tags): self.tags.insert('', 'end', iid=str(i), text=sig, values=(TAG_NAMES.get(sig,'ICC tag'),typ,f'{size:,}'))
                self.settext(self.raw, 'Select a tag to inspect its raw bytes.')
                self.settext(self.tag_details,'Select an ICC tag to see decoded data and curves.')
                self.tag_curves=[]; self.render_tag_plot()
                self.subtitle.config(text=Path(path).name)
            else:
                read_profile(path)
                self.comparison = None
            self.status.config(text='Sampling ICC transform…'); self.update_idletasks()
            stat = Path(path).stat()
            args=(path,stat.st_mtime_ns,stat.st_size,INTENTS.index(self.intent.get()),int(self.density.get()))
            if background:
                self.jobs.append((self.executor.submit(cached_sample,*args),slot,generation,path))
            else:
                result = cached_sample(*args)
                setattr(self,slot,result); self.report()
        except Exception as exc:
            messagebox.showerror('Profile could not be plotted', str(exc))
            self.status.config(text=str(exc))
        self.draw()

    def poll_jobs(self):
        if self.closing: return
        if SETTINGS_NOTICES: self.report_settings_recovery()
        remaining=[]
        for future,slot,generation,path in self.jobs:
            if not future.done(): remaining.append((future,slot,generation,path)); continue
            if future.cancelled() or generation!=self.job_generation[slot]: continue
            try:
                setattr(self,slot,future.result()); self.report(); self.draw()
            except Exception as exc:
                self.status.config(text=f'Could not sample {Path(path).name}: {exc}')
                messagebox.showerror('Profile could not be plotted',f'{path}\n\n{exc}',parent=self)
        self.jobs=remaining
        self.after(30,self.poll_jobs)

    def report(self):
        if self.primary:
            p = self.primary
            extra = f" • Comparison: {Path(self.comparison['path']).name} (cyan wireframe)" if self.comparison else ''
            self.status.config(text=f"{p['samples']:,} device samples • D50 CIELAB • Convex hull approximation{extra}")

    def changed(self, event=None):
        if event and event.widget.cget('textvariable') == str(self.view): self.draw(); return
        other = self.comparison['path'] if self.comparison else None
        self.comparison = None
        if self.path: self.load(self.path)
        if other: self.load(other, True)

    def clear(self):
        self.job_generation['comparison'] += 1
        self.comparison = None; self.report(); self.draw()
    def reset(self): self.yaw, self.pitch, self.zoom = .65, -.35, 1.8; self.draw()
    def rotate(self, e):
        x,y = self.drag; self.yaw += (e.x-x)*.01; self.pitch += (e.y-y)*.01; self.drag=(e.x,e.y)
        self.interacting=True; self.schedule_draw()
        if self.detail_pending is not None: self.after_cancel(self.detail_pending)
        self.detail_pending=self.after(140,self.end_interaction)
    def wheel(self, e):
        self.zoom = max(.5, min(8, self.zoom * (1.1 if e.delta>0 else 1/1.1))); self.schedule_draw()
    def end_interaction(self):
        self.detail_pending=None; self.interacting=False; self.schedule_draw()

    def project(self, points):
        c,s=math.cos(self.yaw),math.sin(self.yaw)
        cp,sp=math.cos(self.pitch),math.sin(self.pitch)
        rotation=np.array([[c,-s,0],[s*sp,c*sp,-cp],[s*cp,c*cp,sp]])
        p=np.asarray(points)@rotation.T
        width, height = self.viewport_size()
        scale=self.zoom*min(width/800,height/600)
        p[:,:2]*=scale; p[:,0]+=width/2; p[:,1]+=height/2
        return p

    def draw(self):
        if not hasattr(self,'legend'): return
        primary=Path(self.primary['path']).name if self.primary else 'No primary gamut loaded'
        comparison_mode = ('CPU overlay' if self.render_mode.get()=='Basic CPU' else ('X-ray' if self.xray.get() else 'depth-tested'))
        comparison=(f"Comparison: {Path(self.comparison['path']).name} • cyan wireframe • "+comparison_mode) if self.comparison else 'No comparison'
        self.legend.config(text=f'Primary: {primary}  |  {comparison}')
        if self.render_mode.get() == 'High GPU' and self.gpu is not None:
            self.gpu.request_draw()
            return
        cv=self.canvas; cv.delete('all'); self.hitpoints=[]
        palette = getattr(self, 'colors', dict(axis='#999999', text='#f2f2f2', muted='#bfbfbf', wire='#aaaaaa', compare='#61d6e8'))
        axes=np.array([[0,0,-50],[110,0,-50],[0,110,-50],[0,0,65]])
        a=self.project(axes)
        for i,label,color in [(1,'a*','#ed8c9c'),(2,'b*','#e5cb73'),(3,'L*','#d4dce6')]:
            cv.create_line(*a[0,:2],*a[i,:2],fill=palette['axis'],arrow='last')
            cv.create_text(*a[i,:2],text=label,fill=palette['text'],anchor='sw',font=(self.ui_family,11))
        if not self.primary and not self.comparison:
            cv.create_text(cv.winfo_width()/2,cv.winfo_height()/2,text='Explore the color your profile can reproduce.\n\nOpen a printer ICC profile to see its sampled gamut.',fill=palette['muted'],justify='center',font=(self.ui_family,14))
        for result, comparison in [(self.primary,False),(self.comparison,True)]:
            if result is None: continue
            p=self.project(result['points']); hull=result['hull']
            view='Wireframe' if comparison else self.view.get()
            if hull is not None and view != 'Points':
                faces=sorted(enumerate(hull.simplices),key=lambda pair:p[pair[1],2].mean())
                if 'cpu_face_colors' not in result:
                    result['cpu_face_colors']=['#'+''.join(f'{int(v):02x}' for v in result['rgb'][tri].mean(axis=0)) for tri in hull.simplices]
                for face_index,tri in faces:
                    color=result['cpu_face_colors'][face_index]
                    cv.create_polygon(*p[tri,:2].flatten(),fill=color if view=='Surface' else '',outline=palette['compare'] if comparison else (color if view=='Surface' else palette['wire']),width=1)
                indices=hull.vertices
            else:
                indices=display_indices(result,1500 if self.interacting else 4000)
                for i in sorted(indices,key=lambda i:p[i,2]):
                    x,y=p[i,:2]; color='#'+''.join(f'{v:02x}' for v in result['rgb'][i])
                    cv.create_oval(x-2,y-2,x+2,y+2,fill=color,outline='')
            if not comparison: self.hitpoints=[(p[i,0],p[i,1],result['lab'][i]) for i in indices]
        cv.create_text(18,18,anchor='nw',text='CIELAB / D50',fill=palette['text'],font=(self.ui_family,12,'bold'))
        cv.create_text(18,44,anchor='nw',text='Drag to orbit  ·  Scroll to zoom\nSurface = convex hull of sampled device colors',fill=palette['muted'],font=(self.ui_family,10))

    def hover(self,e):
        if not self.hitpoints:return
        best=min(self.hitpoints,key=lambda p:(p[0]-e.x)**2+(p[1]-e.y)**2)
        if (best[0]-e.x)**2+(best[1]-e.y)**2<100:
            l,a,b=best[2]; self.status.config(text=f'Sampled point: L* {l:.2f}   a* {a:.2f}   b* {b:.2f}  •  Display colors use sRGB')

    def tag_selected(self,e):
        selected=self.tags.selection()
        if not selected:return
        sig,typ,off,size=self.tagdata[int(selected[0])]
        description,self.tag_curves=decode_tag(sig,self.data[off:off+size])
        self.settext(self.tag_details,description)
        self.render_tag_plot()
        raw=self.data[off:off+min(size,16384)]
        lines=[f'{sig} / {typ}\nOffset {off:,} • {size:,} bytes\n']
        for i in range(0,len(raw),16):
            block=raw[i:i+16]; chars=''.join(chr(b) if 32<=b<127 else '.' for b in block)
            lines.append(f'{i:06x}  {block.hex(" "):<47}  {chars}')
        if size>len(raw): lines.append('\nPreview limited to 16 KiB.')
        self.settext(self.raw,'\n'.join(lines))

    def render_tag_plot(self):
        if not hasattr(self,'tag_plot'): return
        plot=self.tag_plot; plot.delete('all')
        palette=getattr(self,'colors',{'text':'#202020','axis':'#777777'})
        width,height=max(plot.winfo_width(),220),max(plot.winfo_height(),150)
        if not self.tag_curves:
            plot.create_text(width/2,height/2,text='Curve graph appears for TRC and LUT curve tags.',fill=palette['text'],width=width-24)
            return
        left,top,right,bottom=42,22,width-12,height-40
        plot.create_line(left,top,left,bottom,right,bottom,fill=palette['axis'])
        plot.create_text(left,top-10,text='Output',fill=palette['text'],anchor='w')
        plot.create_text(right,bottom+14,text='Input 0 → 1',fill=palette['text'],anchor='e')
        colors=['#e05555','#329b66','#528be8','#bd67c6','#b88718','#30a0ad']
        lo=min(0,min(float(np.min(y)) for _,x,y in self.tag_curves)); hi=max(1,max(float(np.max(y)) for _,x,y in self.tag_curves))
        for i,(name,x,y) in enumerate(self.tag_curves):
            coordinates=np.column_stack((left+x*(right-left),bottom-(y-lo)/(hi-lo)*(bottom-top)))
            plot.create_line(*coordinates.flatten(),fill=colors[i%len(colors)],width=2)
        names=', '.join(name for name,_,_ in self.tag_curves)
        plot.create_text(left,height-12,text=f'{names} • output {lo:.3g}…{hi:.3g}',fill=palette['text'],anchor='w',width=width-55)

    def export(self):
        if not self.primary: return messagebox.showinfo('Export','Open a supported profile first.')
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if path:
            try:
                with open(path,'w',newline='',encoding='utf-8') as f:
                    writer=csv.writer(f); writer.writerow(['L_D50','a_D50','b_D50','intent','profile'])
                    for row in self.primary['lab']: writer.writerow([*row,INTENTS[self.primary['intent']],self.primary['path']])
                self.status.config(text=f'Exported {len(self.primary["lab"]):,} Lab samples to {path}')
            except OSError as exc: messagebox.showerror('Export failed',str(exc))

def main(initial_list=False):
    guard=SingleInstance()
    if not guard.acquire():
        raise_existing_window(); return
    try:
        app=Inspector()
        if initial_list: app.main_tabs.select(app.list_tab)
        if len(sys.argv)>1: app.after(100,lambda:app.load(sys.argv[1]))
        app.mainloop()
    finally:
        guard.close()

if __name__=='__main__':
    if len(sys.argv)==5 and sys.argv[1]=='--install-profile' and sys.argv[3]=='--install-result':
        try:
            read_profile(sys.argv[2]); ImageCms.getOpenProfile(sys.argv[2])
            report={'ok':True,'destination':str(install_profile(sys.argv[2]))}
        except Exception as exc: report={'ok':False,'error':str(exc)}
        from app_support import atomic_write
        atomic_write(Path(sys.argv[4]),json.dumps(report).encode('utf-8'))
        sys.exit(0 if report['ok'] else 1)
    if len(sys.argv) == 3 and sys.argv[1] == '--gpu-check':
        from check_gpu import run_check
        try:
            result = run_check(sys.modules[__name__])
            Path(sys.argv[2]).write_text(json.dumps({'passed': True, **result}, indent=2), encoding='utf-8')
        except Exception as exc:
            Path(sys.argv[2]).write_text(json.dumps({'passed': False, 'error': str(exc)}, indent=2), encoding='utf-8')
            sys.exit(1)
        sys.exit(0)
    main()
