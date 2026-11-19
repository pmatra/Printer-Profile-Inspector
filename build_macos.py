"""Build, smoke-test and ZIP a native macOS .app; run on each target architecture."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from version import __version__
from app_support import BUNDLE_ID


def build():
    if sys.platform!='darwin': raise SystemExit('Build the Mac application on macOS (local Mac or GitHub Actions runner).')
    root=Path(__file__).resolve().parent
    arch=platform.machine()
    if arch not in ('arm64','x86_64'): raise SystemExit('Unsupported Mac architecture: '+arch)
    staging=root/'build/macos';staging.mkdir(parents=True,exist_ok=True)
    from make_macos_notices import collect
    notices=collect(staging/'notices')
    datas=[(str(path),'.') for path in notices.iterdir() if path.is_file()]
    spec=f'''a = Analysis([{str(root/'inspector.py')!r}], pathex=[{str(root)!r}],
    binaries=[], datas={datas!r}, hiddenimports=['AppKit','Foundation','send2trash.mac.modern'],
    excludes=['OpenGL','pyopengltk','win32com','win32api'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ICC Profile Inspector',
    debug=False, strip=False, upx=False, console=False, target_arch={arch!r},
    codesign_identity='-', entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ICC Profile Inspector')
app = BUNDLE(coll, name='ICC Profile Inspector.app', icon=None, bundle_identifier={BUNDLE_ID!r},
    version={__version__!r}, info_plist={{'CFBundleShortVersionString':{__version__!r},
    'CFBundleVersion':{__version__!r},'NSHighResolutionCapable':True,
    'NSRequiresAquaSystemAppearance':False,'LSMinimumSystemVersion':'15.0',
    'CFBundleDocumentTypes':[{{'CFBundleTypeName':'ICC color profile','CFBundleTypeRole':'Viewer',
    'CFBundleTypeExtensions':['icc','icm'],'LSHandlerRank':'Alternate'}}]}})
'''
    specpath=staging/'Inspector-macOS.spec';specpath.write_text(spec,encoding='utf-8')
    dist=root/'dist/macos'
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--distpath',str(dist),
                    '--workpath',str(staging/'pyinstaller'),str(specpath)],check=True)
    application=dist/'ICC Profile Inspector.app';binary=application/'Contents/MacOS/ICC Profile Inspector'
    subprocess.run(['codesign','--verify','--deep','--strict',str(application)],check=True)
    report=staging/'packaged-check.json'
    subprocess.run([str(binary),'--platform-check',str(report)],check=True,timeout=120)
    result=json.loads(report.read_text());assert result['passed'] and result['renderer']=='Basic CPU'
    subprocess.run([str(binary),'--version'],check=True,timeout=30)
    archive=dist/f'ICC-Profile-Inspector-macOS-{arch}-v{__version__}.zip'
    subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(application),str(archive)],check=True)
    (dist/'SHA256SUMS.txt').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n',encoding='ascii')
    (dist/'packaged-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (dist/'README-macOS.txt').write_text(f'ICC Profile Inspector {__version__} — {arch}, macOS 15 or later.\n\nExtract the ZIP, then open ICC Profile Inspector.app. The initial Mac version uses CPU rendering.\nSettings: ~/Library/Application Support/PrinterProfileICCInspector/settings.json\nInstall Profile copies to ~/Library/ColorSync/Profiles without administrator privileges.\n\nThis preview is ad-hoc signed for the macOS loader, NOT Developer ID signed or notarized.\nGatekeeper may prevent opening an Internet download. No Apple developer identity is claimed.\nThe build runner smoke test is not a substitute for interactive testing on your own Mac.\n',encoding='utf-8')
    print('Mac artifact:',archive,flush=True)


if __name__=='__main__': build()
