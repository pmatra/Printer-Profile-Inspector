"""System typography and scalable, shaded ttk button surfaces."""
import ctypes
import sys
import tkinter as tk
from tkinter import font as tkfont


def system_font(root):
    default = tkfont.nametofont('TkDefaultFont', root=root)
    family, size = default.actual('family'), default.actual('size')
    if sys.platform == 'win32':
        class LogFont(ctypes.Structure):
            _fields_ = [(name, ctypes.c_long) for name in
                        ('height', 'width', 'escapement', 'orientation', 'weight')] + [
                (name, ctypes.c_ubyte) for name in
                ('italic', 'underline', 'strikeout', 'charset', 'outprecision',
                 'clipprecision', 'quality', 'pitch')] + [('face', ctypes.c_wchar * 32)]
        value = LogFont()
        if ctypes.windll.user32.SystemParametersInfoW(0x001F, ctypes.sizeof(value), ctypes.byref(value), 0):
            family = value.face or family
            size = max(9, round(abs(value.height) * 72 / root.winfo_fpixels('1i')))
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont', 'TkCaptionFont'):
        tkfont.nametofont(name, root=root).configure(family=family, size=size)
    root.option_add('*Font', 'TkDefaultFont')
    return family, size


def shaded_buttons(root, style, palette, dark):
    """Nine-slice images keep shadows/borders crisp at any button width."""
    def rgb(color):
        return tuple(int(color[i:i+2], 16) for i in (1, 3, 5))

    def mix(a, b, amount):
        return '#%02x%02x%02x' % tuple(round(x+(y-x)*amount) for x,y in zip(rgb(a),rgb(b)))

    background = palette['bg']
    images = []
    for state in ('normal', 'active', 'pressed', 'disabled'):
        image = tk.PhotoImage(master=root, width=32, height=32)
        image.put(background, to=(0, 0, 32, 32))
        pressed = state == 'pressed'
        base = palette['hover'] if state == 'active' else palette['panel']
        if pressed: base = palette['selected']
        # A soft two-step shadow sits below the actual button surface.
        if not pressed and state != 'disabled':
            image.put(mix(background, '#000000', .12 if dark else .09), to=(2, 4, 31, 31))
            image.put(mix(background, '#000000', .23 if dark else .15), to=(1, 3, 31, 30))
        top, bottom = (2, 29) if pressed else (1, 27)
        image.put(palette['border'], to=(0, top, 31, bottom))
        for y in range(top+1, bottom-1):
            fraction = (y-top)/(bottom-top)
            color = mix(base, '#000000', fraction*(.10 if dark else .035))
            if state == 'disabled': color = palette['bg']
            image.put(color, to=(1, y, 30, y+1))
        image.put(mix(base, '#ffffff', .12 if dark else .65), to=(2, top+1, 29, top+2))
        images.append(image)
    root._button_images = images  # Tcl image elements do not retain Python references.
    element = 'Inspector.shaded'
    if element not in style.element_names():
        style.element_create(element, 'image', images[0],
                             ('disabled', images[3]), ('pressed', images[2]), ('active', images[1]),
                             border=(6, 6, 6, 8), sticky='nsew')
    else:
        # Image specifications cannot be reconfigured: use a new element on theme changes.
        root._button_generation = getattr(root, '_button_generation', 0)+1
        element += str(root._button_generation)
        style.element_create(element, 'image', images[0],
                             ('disabled', images[3]), ('pressed', images[2]), ('active', images[1]),
                             border=(6, 6, 6, 8), sticky='nsew')
    style.layout('TButton', [(element, {'sticky':'nsew', 'children':[
        ('Button.focus', {'sticky':'nsew', 'children':[
            ('Button.padding', {'sticky':'nsew', 'children':[
                ('Button.label', {'sticky':'nsew'})]})]})]})])
    style.configure('TButton', padding=(11, 7, 11, 10), foreground=palette['text'])
    style.map('TButton', foreground=[('disabled', palette['muted']),
                                    ('pressed', palette['selection_text'])])
