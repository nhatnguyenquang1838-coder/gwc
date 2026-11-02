"""Windows handle-relative, no-reparse, bounded artifact reads.

Security boundary: open the volume root and every component relative to its
verified directory handle, never validate a pathname and then reopen it.
Unsupported path forms and absent native primitives fail closed.

This module deliberately has no POSIX fallback; the caller selects the backend.
"""
from __future__ import annotations

import ntpath
import os
import re


class WindowsSafeReadUnavailable(OSError):
    """The Windows native safe-read backend cannot serve this request."""


class WindowsUnsafePath(OSError):
    """A directory/file handle is a reparse point or has an invalid type."""


def available() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return bool(ctypes.WinDLL("ntdll") and ctypes.WinDLL("kernel32"))
    except (AttributeError, OSError):
        return False


def read_bounded(path: str | os.PathLike[str], max_bytes: int) -> bytes:
    """Read an exact bounded byte stream, rejecting every reparse component.

    Supports local drive paths only. UNC, device namespaces, alternate data
    streams and unexpected native API failures are rejected, not downgraded.
    Files are read through the *same* final handle verified as a regular file.
    """
    if not available():
        raise WindowsSafeReadUnavailable("WINDOWS_SAFE_READ_UNAVAILABLE")
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("invalid max_bytes")

    import ctypes
    from ctypes import wintypes

    native = os.fspath(path)
    if not isinstance(native, str) or "\x00" in native:
        raise WindowsSafeReadUnavailable("PATH_INVALID")
    absolute = ntpath.abspath(native)
    drive, tail = ntpath.splitdrive(absolute)
    if not re.fullmatch(r"[A-Za-z]:", drive) or not tail.startswith(("\\", "/")):
        raise WindowsSafeReadUnavailable("UNSUPPORTED_WINDOWS_PATH")
    parts = [p for p in re.split(r"[\\/]+", tail) if p]
    if not parts or any(p in (".", "..") or ":" in p for p in parts):
        raise WindowsSafeReadUnavailable("UNSUPPORTED_WINDOWS_PATH")

    ntdll = ctypes.WinDLL("ntdll")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    HANDLE = wintypes.HANDLE
    ULONG = wintypes.ULONG

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT),
                    ("MaximumLength", wintypes.USHORT),
                    ("Buffer", wintypes.LPWSTR)]

    class OBJECT_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Length", ULONG), ("RootDirectory", HANDLE),
                    ("ObjectName", ctypes.POINTER(UNICODE_STRING)),
                    ("Attributes", ULONG), ("SecurityDescriptor", ctypes.c_void_p),
                    ("SecurityQualityOfService", ctypes.c_void_p)]

    class IO_STATUS_BLOCK(ctypes.Structure):
        _fields_ = [("Status", ctypes.c_ssize_t), ("Information", ctypes.c_size_t)]

    class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    ntdll.NtCreateFile.argtypes = [
        ctypes.POINTER(HANDLE), ULONG, ctypes.POINTER(OBJECT_ATTRIBUTES),
        ctypes.POINTER(IO_STATUS_BLOCK), ctypes.c_void_p, ULONG,
        ULONG, ULONG, ULONG, ctypes.c_void_p, ULONG,
    ]
    ntdll.NtCreateFile.restype = ctypes.c_long
    kernel32.CloseHandle.argtypes = [HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandle.argtypes = [
        HANDLE, ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.ReadFile.restype = wintypes.BOOL

    FILE_READ_DATA = 0x0001
    FILE_READ_ATTRIBUTES = 0x0080
    SYNCHRONIZE = 0x100000
    FILE_SHARE_ALL = 0x0007
    FILE_OPEN = 0x0001
    FILE_DIRECTORY_FILE = 0x0001
    FILE_NON_DIRECTORY_FILE = 0x0040
    FILE_SYNCHRONOUS_IO_NONALERT = 0x0020
    FILE_OPEN_REPARSE_POINT = 0x00200000
    OBJ_CASE_INSENSITIVE = 0x0040
    FILE_ATTRIBUTE_DIRECTORY = 0x0010
    FILE_ATTRIBUTE_REPARSE_POINT = 0x0400

    handles = []

    def open_component(name: str, parent: HANDLE | None, directory: bool) -> HANDLE:
        data = ctypes.create_unicode_buffer(name)
        size = len(name.encode("utf-16-le"))
        if size >= 65534:
            raise WindowsSafeReadUnavailable("COMPONENT_TOO_LONG")
        unicode_name = UNICODE_STRING(size, size + 2, ctypes.cast(data, wintypes.LPWSTR))
        attrs = OBJECT_ATTRIBUTES(
            ctypes.sizeof(OBJECT_ATTRIBUTES), parent,
            ctypes.pointer(unicode_name), OBJ_CASE_INSENSITIVE, None, None)
        io = IO_STATUS_BLOCK()
        out = HANDLE()
        options = (FILE_SYNCHRONOUS_IO_NONALERT | FILE_OPEN_REPARSE_POINT |
                   (FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE))
        access = FILE_READ_ATTRIBUTES | SYNCHRONIZE | FILE_READ_DATA
        status = ntdll.NtCreateFile(
            ctypes.byref(out), access, ctypes.byref(attrs), ctypes.byref(io),
            None, 0, FILE_SHARE_ALL, FILE_OPEN, options, None, 0)
        if status < 0:
            raise WindowsSafeReadUnavailable(f"NT_CREATE_FILE_FAILED:{status:#x}")
        handles.append(out)
        info = BY_HANDLE_FILE_INFORMATION()
        if not kernel32.GetFileInformationByHandle(out, ctypes.byref(info)):
            raise WindowsSafeReadUnavailable("FILE_INFO_UNAVAILABLE")
        attributes = info.dwFileAttributes
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            raise WindowsUnsafePath("REPARSE_POINT_REJECTED")
        if bool(attributes & FILE_ATTRIBUTE_DIRECTORY) != directory:
            raise WindowsUnsafePath("FILE_TYPE_MISMATCH")
        return out

    try:
        # Root the traversal at the drive itself; no ancestor is reopened by
        # pathname. Relative NtCreateFile handles keep each ancestor pinned.
        volume = open_component("\\??\\" + drive + "\\", None, True)
        parent = volume
        for name in parts[:-1]:
            parent = open_component(name, parent, True)
        final = open_component(parts[-1], parent, False)
        info = BY_HANDLE_FILE_INFORMATION()
        if not kernel32.GetFileInformationByHandle(final, ctypes.byref(info)):
            raise WindowsSafeReadUnavailable("FILE_INFO_UNAVAILABLE")
        size = (info.nFileSizeHigh << 32) | info.nFileSizeLow
        if size > max_bytes:
            raise WindowsUnsafePath("FILE_TOO_LARGE")
        chunks = []
        length = 0
        while length <= max_bytes:
            to_read = min(65536, max_bytes + 1 - length)
            if not to_read:
                break
            buf = ctypes.create_string_buffer(to_read)
            got = wintypes.DWORD()
            if not kernel32.ReadFile(final, buf, to_read, ctypes.byref(got), None):
                raise WindowsSafeReadUnavailable("FILE_READ_FAILED")
            if got.value == 0:
                break
            chunks.append(buf.raw[:got.value])
            length += got.value
            if length > max_bytes:
                raise WindowsUnsafePath("FILE_TOO_LARGE")
        return b"".join(chunks)
    finally:
        for handle in reversed(handles):
            kernel32.CloseHandle(handle)
