"""Generate PyInstaller Windows version resources from the application version."""
from pathlib import Path
import sys
from version import __version__

def write_version_info(path):
    numbers=tuple(map(int,__version__.split('.')))+(0,)
    text=f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f, flags=0,
                   OS=0x40004, fileType=0x1, subtype=0, date=(0,0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Peter Matra'),
    StringStruct('FileDescription', 'ICC Profile Inspector'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('ProductName', 'ICC Profile Inspector'),
    StringStruct('ProductVersion', '{__version__}'),
    StringStruct('LegalCopyright', 'Copyright (c) 2026 Peter Matra')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')

if __name__=='__main__': write_version_info(sys.argv[1])
