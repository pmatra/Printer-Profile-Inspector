"""Crash-safe preferences and native Windows/macOS application services."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

APP_TITLE = 'ICC Profile Inspector'
BUNDLE_ID = 'design.petermatra.icc-profile-inspector'


def settings_path():
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'PrinterProfileICCInspector' / 'settings.json'
    base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    return base / 'PrinterProfileICCInspector' / 'settings.json'


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class SettingsStore:
    def __init__(self, path, legacy=None, notices=None):
        self.path = Path(path)
        self.backup = self.path.with_suffix('.json.bak')
        self.legacy = Path(legacy) if legacy else None
        self.notices = notices if notices is not None else []

    @staticmethod
    def decode(data):
        value = json.loads(data.decode('utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError('Settings must contain a JSON object.')
        return value

    def read(self):
        if not self.path.exists():
            if self.backup.exists():
                try:
                    value = self.decode(self.backup.read_bytes())
                    atomic_write(self.path, self.backup.read_bytes())
                    self.notices.append('The settings file was missing. Settings were restored from the last-known-good backup.')
                    return value
                except (ValueError,UnicodeError):
                    quarantine=self.path.with_name(f'settings.corrupt-backup-{time.time_ns()}.json')
                    atomic_write(quarantine,self.backup.read_bytes())
                    atomic_write(self.path,b'{}')
                    self.notices.append(f'No settings file or usable backup was available. Defaults are in use; the damaged backup was preserved at {quarantine}.')
                    return {}
            if self.legacy and self.legacy.exists() and self.legacy != self.path:
                try:
                    value = self.decode(self.legacy.read_bytes())
                    self.write(value)
                    self.notices.append(f'Existing portable settings were imported into {self.path}.')
                    return value
                except (ValueError, UnicodeError):
                    self.notices.append(f'Portable settings could not be read: {self.legacy}. The original file was preserved.')
            return {}
        try:
            return self.decode(self.path.read_bytes())
        except (ValueError, UnicodeError):
            damaged = self.path.read_bytes()
            quarantine = self.path.with_name(f'settings.corrupt-{time.time_ns()}.json')
            atomic_write(quarantine, damaged)
            try:
                value = self.decode(self.backup.read_bytes())
                atomic_write(self.path, self.backup.read_bytes())
                self.notices.append(f'Malformed settings were recovered from the last-known-good backup. The damaged file was preserved at {quarantine}.')
                return value
            except (OSError, ValueError, UnicodeError):
                # Preserve both damaged files, then explicitly report the reset.
                if self.backup.exists():
                    atomic_write(quarantine.with_suffix('.backup.json'), self.backup.read_bytes())
                atomic_write(self.path, b'{}')
                self.notices.append(f'Settings were malformed and no usable backup was available. Defaults are in use. The damaged file was preserved at {quarantine}.')
                return {}

    def write(self, value):
        encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
        if self.path.exists():
            previous = self.path.read_bytes()
            self.decode(previous)  # Never replace the good backup with corrupt JSON.
            atomic_write(self.backup, previous)
        atomic_write(self.path, encoded)
        if not self.backup.exists():
            atomic_write(self.backup, encoded)

    def update(self, key, value):
        settings = self.read()
        settings[key] = value
        self.write(settings)


class SingleInstance:
    def __init__(self, name=None):
        self.handle = None
        self.lock_file = None
        user = os.environ.get('USERPROFILE', os.environ.get('USERNAME', 'user'))
        token = hashlib.sha256(user.casefold().encode()).hexdigest()[:20]
        self.name = name or 'Global\\PrinterProfileICCInspector-' + token
        if sys.platform=='darwin': self.name=name or BUNDLE_ID

    def acquire(self):
        if self.handle or self.lock_file: return True
        if sys.platform != 'win32':
            import fcntl
            path=self.lock_path()
            path.parent.mkdir(parents=True,exist_ok=True)
            stream=path.open('a+')
            try: fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                stream.close();return False
            except Exception:
                stream.close();raise
            self.lock_file=stream
            stream.seek(0);stream.truncate();stream.write(str(os.getpid()));stream.flush()
            return True
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        ctypes.set_last_error(0)
        self.handle = kernel.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            self.close()
            return False
        return True

    def lock_path(self):
        token=hashlib.sha256(self.name.encode()).hexdigest()[:20]
        return settings_path().parent / ('instance-'+token+'.lock')

    def close(self):
        if self.lock_file:
            import fcntl
            fcntl.flock(self.lock_file.fileno(),fcntl.LOCK_UN)
            self.lock_file.close();self.lock_file=None
            # Never unlink a flock file: another process may already hold its inode.
        if self.handle:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self.handle)
            self.handle = None


def color_directory():
    if sys.platform == 'darwin': return Path('/Library/ColorSync/Profiles')
    if sys.platform == 'win32':
        library = ctypes.WinDLL('mscms', use_last_error=True)
        library.GetColorDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
        length = ctypes.c_uint32(32768)
        buffer = ctypes.create_unicode_buffer(length.value)
        if library.GetColorDirectoryW(None, buffer, ctypes.byref(length)):
            return Path(buffer.value)
    return Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'spool' / 'drivers' / 'color'


def profile_directories():
    if sys.platform=='darwin':
        return [('My profiles',Path.home()/'Library/ColorSync/Profiles'),
                ('Shared profiles',Path('/Library/ColorSync/Profiles')),
                ('Apple profiles (read-only)',Path('/System/Library/ColorSync/Profiles'))]
    return [('Windows color profiles',color_directory())]


def installation_directory():
    return Path.home()/'Library/ColorSync/Profiles' if sys.platform=='darwin' else color_directory()


def install_profile(path):
    path = Path(path).resolve()
    directory=installation_directory()
    destination = directory / path.name
    if destination.exists():
        if destination.read_bytes() == path.read_bytes():
            return destination
        raise FileExistsError(f'A different profile already exists at {destination}. It was not overwritten.')
    if sys.platform=='darwin':
        directory.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(prefix='.icc-install-',suffix='.tmp',dir=directory)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(path.read_bytes());stream.flush();os.fsync(stream.fileno())
            # Atomic publication WITHOUT replacing an existing file, including a
            # collision created by another process while the copy was being written.
            os.link(temporary,destination)
        finally:
            os.unlink(temporary)
        return destination
    library = ctypes.WinDLL('mscms', use_last_error=True)
    library.InstallColorProfileW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    library.InstallColorProfileW.restype = ctypes.c_int
    if not library.InstallColorProfileW(None, str(path)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not destination.exists():
        raise OSError('Windows did not create the installed profile in its color directory.')
    return destination


def recycle_profile(path):
    path = Path(path).absolute()
    if sys.platform=='darwin' and path.resolve().is_relative_to(Path('/System')):
        raise PermissionError('macOS manages the profiles under /System. They cannot be moved to Trash by this application.')
    if sys.platform == 'win32':
        drive_type = ctypes.windll.kernel32.GetDriveTypeW
        drive_type.argtypes = [ctypes.c_wchar_p]
        drive_type.restype = ctypes.c_uint32
        if drive_type(path.anchor) != 3:
            raise OSError('Recycle Bin deletion is only enabled for local fixed drives. The profile was not deleted.')
    try:
        if sys.platform=='win32':
            from send2trash.win.modern import send2trash
        elif sys.platform=='darwin':
            from send2trash.mac.modern import send2trash
        else:
            from send2trash import send2trash
    except ImportError as exc:
        raise OSError('Native Trash/Recycle Bin support is unavailable. The profile was not deleted.') from exc
    send2trash(str(path))  # Errors propagate; there is no permanent-deletion fallback.


def raise_existing_window():
    if sys.platform=='darwin':
        from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
        try:
            pid=int(SingleInstance().lock_path().read_text())
            application=NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
            if application:
                application.unhide()
                return bool(application.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))
        except (OSError,ValueError): pass
        return False
    user = ctypes.windll.user32
    user.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user.FindWindowW.restype = ctypes.c_void_p
    user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user.MessageBoxW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint]
    hwnd = user.FindWindowW(None, APP_TITLE)
    if hwnd:
        user.ShowWindow(hwnd, 9)
        user.SetForegroundWindow(hwnd)
    else:
        user.MessageBoxW(None, 'ICC Profile Inspector is already running. Use its existing window.', APP_TITLE, 0x40)


def macos_is_dark():
    from AppKit import NSApplication, NSAppearanceNameAqua, NSAppearanceNameDarkAqua
    appearance=NSApplication.sharedApplication().effectiveAppearance()
    return appearance.bestMatchFromAppearancesWithNames_([NSAppearanceNameAqua,NSAppearanceNameDarkAqua])==NSAppearanceNameDarkAqua


def set_macos_appearance(mode):
    from AppKit import NSApplication, NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua
    name=NSAppearanceNameDarkAqua if mode=='Dark' else NSAppearanceNameAqua
    NSApplication.sharedApplication().setAppearance_(None if mode=='Follow macOS' else NSAppearance.appearanceNamed_(name))
