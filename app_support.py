"""Crash-safe preferences, Windows single-instance guard, and profile operations."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

APP_TITLE = 'ICC Profile Inspector'


def settings_path():
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
        user = os.environ.get('USERPROFILE', os.environ.get('USERNAME', 'user'))
        token = hashlib.sha256(user.casefold().encode()).hexdigest()[:20]
        self.name = name or 'Global\\PrinterProfileICCInspector-' + token

    def acquire(self):
        if sys.platform != 'win32':
            raise OSError('This build supports single-instance operation on Windows only.')
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

    def close(self):
        if self.handle:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(self.handle)
            self.handle = None


def color_directory():
    if sys.platform == 'win32':
        library = ctypes.WinDLL('mscms', use_last_error=True)
        library.GetColorDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
        length = ctypes.c_uint32(32768)
        buffer = ctypes.create_unicode_buffer(length.value)
        if library.GetColorDirectoryW(None, buffer, ctypes.byref(length)):
            return Path(buffer.value)
    return Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32' / 'spool' / 'drivers' / 'color'


def install_profile(path):
    path = Path(path).resolve()
    destination = color_directory() / path.name
    if destination.exists():
        if destination.read_bytes() == path.read_bytes():
            return destination
        raise FileExistsError(f'A different profile already exists at {destination}. It was not overwritten.')
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
    if sys.platform == 'win32':
        drive_type = ctypes.windll.kernel32.GetDriveTypeW
        drive_type.argtypes = [ctypes.c_wchar_p]
        drive_type.restype = ctypes.c_uint32
        if drive_type(path.anchor) != 3:
            raise OSError('Recycle Bin deletion is only enabled for local fixed drives. The profile was not deleted.')
    try:
        if sys.platform=='win32':
            from send2trash.win.modern import send2trash
        else:
            from send2trash import send2trash
    except ImportError as exc:
        raise OSError('Recycle Bin support is unavailable. The profile was not deleted.') from exc
    send2trash(str(path))  # Errors propagate; there is no permanent-deletion fallback.


def raise_existing_window():
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
