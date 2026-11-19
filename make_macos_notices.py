"""Collect the actual Mac wheels' notices, including their embedded libraries."""
import importlib.metadata as metadata
from pathlib import Path
import platform
import sys
from urllib.request import urlopen
import tkinter as tk


def collect(destination):
    if sys.platform!='darwin': raise SystemExit('Collect macOS notices on the Mac build runner.')
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    sections=[];seen=set();versions=[]
    def add(label,source,data):
        try: text=data.decode('utf-8-sig')
        except UnicodeDecodeError: text=data.decode('latin-1')
        sections.append('\n'+'='*78+f'\n{label}\nSource: {source}\n'+'='*78+'\n\n'+text+'\n')
    for name in ['pillow','numpy','scipy','Send2Trash','pyobjc-core','pyobjc-framework-Cocoa',
                 'pyinstaller','pyinstaller-hooks-contrib','altgraph','packaging']:
        dist=metadata.distribution(name);versions.append((dist.metadata['Name'],dist.version));found=0
        for entry in dist.files or []:
            if not any(token in Path(entry).name.lower() for token in ('license','copying','notice')): continue
            path=Path(dist.locate_file(entry))
            if not path.is_file() or path.resolve() in seen: continue
            seen.add(path.resolve());add(f'{name} {dist.version}',str(entry),path.read_bytes());found+=1
        if not found: raise RuntimeError(f'No license/notice text was found for {name}')
    version=platform.python_version()
    for filename in ('LICENSE','Doc/license.rst'):
        url=f'https://raw.githubusercontent.com/python/cpython/v{version}/{filename}'
        add(f'Python {version}',url,urlopen(url,timeout=60).read())
    root=tk.Tk();root.withdraw()
    try: releases=[('tcl',str(root.tk.call('info','patchlevel'))),('tk',str(root.tk.call('set','tk_patchLevel')))]
    finally: root.destroy()
    for name,release in releases:
        url=f'https://raw.githubusercontent.com/tcltk/{name}/core-{release.replace(".","-")}/license.terms'
        add(f'{name} {release}',url,urlopen(url,timeout=60).read())
    from scipy.optimize._highspy._core import _Highs
    highs=_Highs().version();url=f'https://raw.githubusercontent.com/ERGO-Code/HiGHS/v{highs}/LICENSE.txt'
    add(f'HiGHS {highs}',url,urlopen(url,timeout=60).read())
    source=Path(__file__).parent
    (destination/'LICENSE').write_bytes((source/'LICENSE').read_bytes())
    (destination/'THIRD_PARTY_LICENSES.txt').write_text('macOS build — complete third-party license/notice collections\n'+''.join(sections),encoding='utf-8')
    lines=['# macOS third-party notices','',f'Built using Python {version} on {platform.machine()}.',
           'The application is MIT licensed. Dependencies retain their own licenses; see LICENSE and THIRD_PARTY_LICENSES.txt.',
           'The wheel-supplied collections include incorporated code and native-library notices. Some optional components described by those collections may not be used.',
           'This software is based in part on the work of the FreeType Team and the Independent JPEG Group. It includes Qhull and HiGHS through SciPy.',
           '',*['- '+name+' '+release for name,release in versions],
           '', 'Apple system frameworks and system fonts are supplied by macOS; font files are not redistributed.']
    (destination/'THIRD_PARTY_NOTICES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return destination


if __name__=='__main__': collect(sys.argv[1])
