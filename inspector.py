"""ICC Gamut Inspector — independent profile inspector and sampled gamut viewer."""
import csv
import itertools
import json
import math
import struct
import sys
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from scipy.spatial import ConvexHull
from PIL import Image, ImageCms

INTENTS = ['Perceptual', 'Relative colorimetric', 'Saturation', 'Absolute colorimetric']
DEFAULT_DIRECTORY = Path(r'C:\Windows\System32\spool\drivers\color')
SETTINGS_PATH = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent / 'settings.json'

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

class Inspector(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ICC Gamut Inspector')
        self.geometry('1280x820')
        self.minsize(980, 650)
        self.configure(bg='#111720')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background='#1c2532', foreground='#e3eaf4', font=('Segoe UI', 10))
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
        self.density = tk.StringVar(value='9')
        self.view = tk.StringVar(value='Surface')
        self.main_tabs = ttk.Notebook(self)
        self.main_tabs.pack(fill='both', expand=True, padx=8, pady=8)
        self.inspector_tab = ttk.Frame(self.main_tabs)
        self.list_tab = ttk.Frame(self.main_tabs)
        self.main_tabs.add(self.inspector_tab, text='ICC/Gamut Inspector')
        self.main_tabs.add(self.list_tab, text='Profile List')
        bar = ttk.Frame(self.inspector_tab, padding=12); bar.pack(fill='x')
        ttk.Label(bar, text='ICC / GAMUT INSPECTOR', font=('Segoe UI', 17, 'bold')).pack(side='left', padx=(0, 25))
        ttk.Button(bar, text='Open profile…', command=self.open).pack(side='left', padx=4)
        ttk.Button(bar, text='Compare…', command=lambda: self.open(True)).pack(side='left', padx=4)
        ttk.Button(bar, text='Clear comparison', command=self.clear).pack(side='left', padx=4)
        ttk.Button(bar, text='Export samples…', command=self.export).pack(side='right')
        self.subtitle = ttk.Label(self.inspector_tab, text='Open an ICC / ICM printer or RGB profile to begin.', padding=(16, 4))
        self.subtitle.pack(fill='x')
        controls = ttk.Frame(self.inspector_tab, padding=12); controls.pack(fill='x')
        for label, var, values, width in [('Intent', self.intent, INTENTS, 25), ('Grid / channel', self.density, ['5','9','13'], 5), ('View', self.view, ['Surface','Points','Wireframe'], 12)]:
            ttk.Label(controls, text=label).pack(side='left', padx=(8, 6))
            box = ttk.Combobox(controls, textvariable=var, values=values, state='readonly', width=width)
            box.pack(side='left'); box.bind('<<ComboboxSelected>>', self.changed)
        ttk.Button(controls, text='Reset view', command=self.reset).pack(side='right')
        split = ttk.Panedwindow(self.inspector_tab, orient='horizontal'); split.pack(fill='both', expand=True, padx=12)
        tabs = ttk.Notebook(split); split.add(tabs, weight=1)
        info = ttk.Frame(tabs); tabs.add(info, text='Profile header')
        self.header = tk.Text(info, wrap='word', bg='#16202d', fg='#e3eaf4', relief='flat', width=36, font=('Consolas', 10), padx=12, pady=12)
        self.header.pack(fill='both', expand=True)
        tagpage = ttk.Frame(tabs); tabs.add(tagpage, text='ICC tags')
        self.tags = ttk.Treeview(tagpage, columns=('type','size'), show='tree headings', height=10)
        self.tags.heading('#0', text='Tag'); self.tags.column('#0', width=70)
        for col in ('type','size'):
            self.tags.heading(col, text=col.title()); self.tags.column(col, width=80)
        self.tags.pack(fill='x'); self.tags.bind('<<TreeviewSelect>>', self.tag_selected)
        self.raw = tk.Text(tagpage, bg='#16202d', fg='#c2d3e7', wrap='none', width=36, font=('Consolas',9))
        self.raw.pack(fill='both', expand=True)
        right = ttk.Frame(split); split.add(right, weight=3)
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
        self.directory_label = ttk.Label(self.list_tab, padding=(12, 4), wraplength=1000)
        self.directory_label.pack(fill='x')
        frame = ttk.Frame(self.list_tab, padding=12)
        frame.pack(fill='both', expand=True)
        columns = ('filename', 'version', 'space', 'created', 'status')
        self.profile_list = ttk.Treeview(frame, columns=columns, show='headings', selectmode='browse')
        for column, title, width in zip(columns, ['Filename', 'Version', 'Device color space', 'Created', 'Status'], [340, 85, 150, 180, 230]):
            self.profile_list.heading(column, text=title, command=lambda c=column: self.sort_directory(c))
            self.profile_list.column(column, width=width, minwidth=75)
        vertical = ttk.Scrollbar(frame, orient='vertical', command=self.profile_list.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=self.profile_list.xview)
        self.profile_list.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.profile_list.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns'); horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        self.profile_list.bind('<Double-1>', self.open_list_selection)
        self.profile_list.bind('<Return>', self.open_list_selection)
        self.directory_status = ttk.Label(self.list_tab, padding=12)
        self.directory_status.pack(fill='x')
        self.sort_reverse = {}
        self.refresh_directory()

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
            SETTINGS_PATH.write_text(json.dumps({'default_directory': new_default}, indent=2), encoding='utf-8')
            self.default_directory = new_default
            self.make_default.set(Path(self.directory) == Path(new_default))
            self.directory_status.config(text=f'Default directory saved: {new_default}')
        except OSError as exc:
            self.make_default.set(Path(self.directory) == Path(self.default_directory))
            messagebox.showerror('Default directory could not be saved', str(exc))

    def refresh_directory(self):
        self.directory_label.config(text=self.directory)
        self.list_paths = {}
        for item in self.profile_list.get_children(): self.profile_list.delete(item)
        try:
            rows = directory_entries(self.directory)
            for i, (path, values) in enumerate(rows):
                key = str(i)
                self.list_paths[key] = path
                self.profile_list.insert('', 'end', iid=key, values=values)
            count = sum(values[-1] == 'ICC profile' for _, values in rows)
            self.directory_status.config(text=f'{len(rows)} items • {count} ICC profiles • Double-click a profile to inspect it; double-click a folder to browse.')
        except OSError as exc:
            self.directory_status.config(text=f'Cannot read directory: {exc} • Use Open Directory to choose another folder.')

    def sort_directory(self, column):
        reverse = self.sort_reverse.get(column, False)
        rows = sorted(self.profile_list.get_children(), key=lambda i: self.profile_list.set(i, column).casefold(), reverse=reverse)
        for index, item in enumerate(rows): self.profile_list.move(item, '', index)
        self.sort_reverse[column] = not reverse

    def open_list_selection(self, event=None):
        selected = self.profile_list.selection()
        if not selected: return
        path = self.list_paths[selected[0]]
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

    def load(self, path, compare=False):
        try:
            if not compare:
                data, fields, tags = read_profile(path)
                self.path, self.data, self.tagdata = path, data, tags
                self.primary = None
                self.settext(self.header, '\n\n'.join(f'{k}\n{v}' for k,v in fields))
                for item in self.tags.get_children(): self.tags.delete(item)
                for i,(sig,typ,off,size) in enumerate(tags): self.tags.insert('', 'end', iid=str(i), text=sig, values=(typ,f'{size:,}'))
                self.settext(self.raw, 'Select a tag to inspect its raw bytes.')
                self.subtitle.config(text=Path(path).name)
            self.status.config(text='Sampling ICC transform…'); self.update_idletasks()
            result = sample_gamut(path, INTENTS.index(self.intent.get()), int(self.density.get()))
            if compare: self.comparison = result
            else: self.primary = result
            self.report()
        except Exception as exc:
            messagebox.showerror('Profile could not be plotted', str(exc))
            self.status.config(text=str(exc))
        self.draw()

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

    def clear(self): self.comparison = None; self.report(); self.draw()
    def reset(self): self.yaw, self.pitch, self.zoom = .65, -.35, 1.8; self.draw()
    def rotate(self, e):
        x,y = self.drag; self.yaw += (e.x-x)*.01; self.pitch += (e.y-y)*.01; self.drag=(e.x,e.y); self.draw()
    def wheel(self, e): self.zoom = max(.5, min(8, self.zoom * (1.1 if e.delta>0 else 1/1.1))); self.draw()

    def project(self, points):
        c,s=math.cos(self.yaw),math.sin(self.yaw)
        cp,sp=math.cos(self.pitch),math.sin(self.pitch)
        rotation=np.array([[c,-s,0],[s*sp,c*sp,-cp],[s*cp,c*cp,sp]])
        p=np.asarray(points)@rotation.T
        scale=self.zoom*min(self.canvas.winfo_width()/800,self.canvas.winfo_height()/600)
        p[:,:2]*=scale; p[:,0]+=self.canvas.winfo_width()/2; p[:,1]+=self.canvas.winfo_height()/2
        return p

    def draw(self):
        cv=self.canvas; cv.delete('all'); self.hitpoints=[]
        axes=np.array([[0,0,-50],[110,0,-50],[0,110,-50],[0,0,65]])
        a=self.project(axes)
        for i,label,color in [(1,'a*','#ed8c9c'),(2,'b*','#e5cb73'),(3,'L*','#d4dce6')]:
            cv.create_line(*a[0,:2],*a[i,:2],fill='#455265',arrow='last')
            cv.create_text(*a[i,:2],text=label,fill=color,anchor='sw',font=('Segoe UI',11))
        if not self.primary and not self.comparison:
            cv.create_text(cv.winfo_width()/2,cv.winfo_height()/2,text='Explore the color your profile can reproduce.\n\nOpen a printer ICC profile to see its sampled gamut.',fill='#93a6be',justify='center',font=('Segoe UI',14))
        for result, comparison in [(self.primary,False),(self.comparison,True)]:
            if result is None: continue
            p=self.project(result['points']); hull=result['hull']
            view='Wireframe' if comparison else self.view.get()
            if hull is not None and view != 'Points':
                faces=sorted(hull.simplices,key=lambda t:p[t,2].mean())
                for tri in faces:
                    color='#'+''.join(f'{int(v):02x}' for v in result['rgb'][tri].mean(axis=0))
                    cv.create_polygon(*p[tri,:2].flatten(),fill=color if view=='Surface' else '',outline='#64dce8' if comparison else (color if view=='Surface' else '#677c93'),width=1)
                indices=hull.vertices
            else:
                indices=range(len(p))
                for i in sorted(indices,key=lambda i:p[i,2]):
                    x,y=p[i,:2]; color='#'+''.join(f'{v:02x}' for v in result['rgb'][i])
                    cv.create_oval(x-2,y-2,x+2,y+2,fill=color,outline='')
            if not comparison: self.hitpoints=[(p[i,0],p[i,1],result['lab'][i]) for i in indices]
        cv.create_text(18,18,anchor='nw',text='CIELAB / D50',fill='#d4e3f5',font=('Segoe UI',12,'bold'))
        cv.create_text(18,44,anchor='nw',text='Drag to orbit  ·  Scroll to zoom\nSurface = convex hull of sampled device colors',fill='#8297b0',font=('Segoe UI',10))

    def hover(self,e):
        if not self.hitpoints:return
        best=min(self.hitpoints,key=lambda p:(p[0]-e.x)**2+(p[1]-e.y)**2)
        if (best[0]-e.x)**2+(best[1]-e.y)**2<100:
            l,a,b=best[2]; self.status.config(text=f'Sampled point: L* {l:.2f}   a* {a:.2f}   b* {b:.2f}  •  Display colors use sRGB')

    def tag_selected(self,e):
        selected=self.tags.selection()
        if not selected:return
        sig,typ,off,size=self.tagdata[int(selected[0])]
        raw=self.data[off:off+min(size,16384)]
        lines=[f'{sig} / {typ}\nOffset {off:,} • {size:,} bytes\n']
        for i in range(0,len(raw),16):
            block=raw[i:i+16]; chars=''.join(chr(b) if 32<=b<127 else '.' for b in block)
            lines.append(f'{i:06x}  {block.hex(" "):<47}  {chars}')
        if size>len(raw): lines.append('\nPreview limited to 16 KiB.')
        self.settext(self.raw,'\n'.join(lines))

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

if __name__=='__main__':
    app=Inspector()
    if len(sys.argv)>1: app.after(100,lambda:app.load(sys.argv[1]))
    app.mainloop()
