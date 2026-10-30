"""Directory-durability helpers shared by checkpoint and settlement writers.

POSIX makes a directory entry durable by ``os.open(dir, O_RDONLY)`` followed by
``os.fsync``. Windows refuses to open a directory through ``os.open``
(``PermissionError`` EACCES), so the same guarantee is obtained with
``FlushFileBuffers`` on a directory handle opened with ``FILE_FLAG_BACKUP_SEMANTICS``
and write access. The helper exists so callers keep the durability guarantee on
every platform instead of silently skipping the flush.
"""
from __future__ import annotations

import os

__all__ = ["flush_directory"]

if os.name == "nt":  # pragma: no cover - platform specific
    import ctypes
    from ctypes import wintypes

    _GENERIC_READ_WRITE = 0x80000000 | 0x40000000
    _FILE_SHARE_ALL = 0x00000001 | 0x00000002 | 0x00000004
    _OPEN_EXISTING = 3
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateFileW.restype = wintypes.HANDLE
    _KERNEL32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    _KERNEL32.FlushFileBuffers.restype = wintypes.BOOL
    _KERNEL32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]


def flush_directory(path) -> None:
    """Flush a directory's own metadata so a completed rename/create is durable.

    Raises ``OSError`` when the platform cannot perform the flush; callers must
    not treat a failed flush as success.
    """
    target = str(path)
    if os.name == "nt":  # pragma: no cover - platform specific
        handle = _KERNEL32.CreateFileW(
            target, _GENERIC_READ_WRITE, _FILE_SHARE_ALL, None,
            _OPEN_EXISTING, _FILE_FLAG_BACKUP_SEMANTICS, None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not _KERNEL32.FlushFileBuffers(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _KERNEL32.CloseHandle(handle)
        return
    fd = os.open(target, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
