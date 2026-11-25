"""Bounded, anonymous release checks. Never download or execute update payloads."""
from dataclasses import dataclass
import json
import platform
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

REPOSITORY = 'pmatra/Printer-Profile-Inspector'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases?per_page=30'
MAX_RESPONSE = 2 * 1024 * 1024


class UpdateCheckError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    asset_name: str


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value or '')
    return tuple(map(int, match.groups())) if match else None


def select_release(releases, current, system=None, machine=None):
    """Choose the highest newer stable version with a download for this OS/CPU."""
    installed = version_tuple(current)
    if installed is None:
        raise UpdateCheckError('The installed version is not a supported release version.')
    if not isinstance(releases, list):
        raise UpdateCheckError('GitHub returned an unexpected release response.')
    system, machine = system or sys.platform, (machine or platform.machine()).lower()
    compatible = []
    for release in releases:
        if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
            continue
        version = version_tuple(release.get('tag_name'))
        if version is None or version <= installed:
            continue
        url = release.get('html_url', '')
        parsed = urlsplit(url)
        prefix = f'/{REPOSITORY}/releases/tag/'
        if parsed.scheme != 'https' or parsed.netloc != 'github.com' or not parsed.path.startswith(prefix):
            continue
        assets = release.get('assets', [])
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get('name', '')).lower()
            download = urlsplit(str(asset.get('browser_download_url', '')))
            if download.scheme != 'https' or download.netloc != 'github.com' or not download.path.startswith(f'/{REPOSITORY}/releases/download/'):
                continue
            if system == 'win32':
                matches = (machine in ('amd64', 'x86_64', 'arm64', 'aarch64') and
                           ((name.startswith('icc-profile-inspector-setup-') and name.endswith('-x64.exe')) or
                            (name.startswith('icc-gamut-inspector-windows-') and name.endswith('.zip'))))
            elif system == 'darwin':
                arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x86_64' if machine in ('x86_64', 'amd64') else None
                matches = arch is not None and name.startswith(f'icc-profile-inspector-macos-{arch}-') and name.endswith('.zip')
            else:
                matches = False
            if matches:
                compatible.append((version, Release('.'.join(map(str, version)), url, asset['name'])))
                break
    return max(compatible, key=lambda pair: pair[0])[1] if compatible else None


def check_for_update(current, *, system=None, machine=None, opener=None):
    request = Request(API_URL, headers={'Accept': 'application/vnd.github+json',
                      'User-Agent': f'ICC-Profile-Inspector/{current}',
                      'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with (opener or urlopen)(request, timeout=6) as response:
            payload = response.read(MAX_RESPONSE + 1)
        if len(payload) > MAX_RESPONSE:
            raise UpdateCheckError('GitHub returned an unexpectedly large release response.')
        releases = json.loads(payload)
        return select_release(releases, current, system, machine)
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise UpdateCheckError('GitHub temporarily limited update requests. Try again later.') from None
        raise UpdateCheckError(f'GitHub could not be reached (HTTP {exc.code}).') from None
    except (URLError, OSError, TimeoutError) as exc:
        raise UpdateCheckError('Could not connect to GitHub. Check your internet connection and try again.') from exc
    except (ValueError, TypeError) as exc:
        raise UpdateCheckError('GitHub returned an unreadable release response.') from exc
