"""
21 Oct 2026 (live was OOM-killed twice at 512 MiB, notes live-502-1021.md) — the public map's heavy reads, a few at a time.

One map page load fired about twelve reads at once and then the month figures sixty times; several viewers (or one
reloading) ran them all side by side, emptied the six-connection database pool and took the process from 113 MB to
the limit in six minutes. Each heavy read now takes one of SLOTS slots; the rest wait their turn (a burst queues
instead of every read holding its memory at the same moment). A read still waiting after WAIT_S is answered busy.

Every heavy read prints ONE line: the process memory in use before and after, how long it ran and waited, and how
many others were running and waiting — so the next incident is measured, not inferred.

A heavy read that calls another on the same thread (the bulletin reads the month figures; road-load does too) runs
inside the slot it already holds: no second slot (two outer reads holding both slots would wait on each other for
ever) and no second line.
"""
import os
import sys
import threading
import time
from contextlib import contextmanager

#: heavy reads running at once. 0.5 CPU on Render's Starter plan and one Python process: a third read side by side
#: adds memory, not speed (Python runs one thread's Python code at a time)
SLOTS = 2
#: how long a read waits for a slot before it is answered busy (seconds)
WAIT_S = 90.0

_sem = threading.BoundedSemaphore(SLOTS)
_local = threading.local()
_lock = threading.Lock()
_state = {"running": 0, "waiting": 0}


class Busy(Exception):
    """No slot came free within WAIT_S."""


def memory_mb():
    """The process's memory in use (resident set) in MB, or None where it cannot be read. Linux (Render): /proc;
    Windows (this laptop): the working set."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            import ctypes.wintypes as wt

            class _PMC(ctypes.Structure):
                _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            c = _PMC()
            c.cb = ctypes.sizeof(_PMC)
            k32 = ctypes.WinDLL("kernel32")
            k32.GetCurrentProcess.restype = wt.HANDLE
            gpmi = ctypes.WinDLL("psapi").GetProcessMemoryInfo
            gpmi.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]    # the pseudo-handle overflows an int
            gpmi.restype = wt.BOOL
            if not gpmi(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
                return None
            return c.WorkingSetSize / 1e6
        except Exception:
            return None
    return None


def _mb(v):
    return "?" if v is None else f"{v:.0f}"


def line(name, before, after, ran_s, waited_s, running, waiting):
    """The one log line of a heavy read (a function, so the harness can hold its words)."""
    delta = "" if before is None or after is None else f" ({after - before:+.0f})"
    return (f"🧮 heavy read {name}: memory {_mb(before)} -> {_mb(after)} MB{delta}, ran {ran_s:.2f} s, "
            f"waited {waited_s:.2f} s; others {running} running, {waiting} waiting")


@contextmanager
def slot(name, busy=None):
    """Run the body as heavy read `name`: wait for a slot (at most WAIT_S, then raise busy() or Busy), log one line.
    Re-entrant on one thread: an inner heavy read runs in the outer one's slot."""
    depth = getattr(_local, "depth", 0)
    if depth:
        _local.depth = depth + 1
        try:
            yield
        finally:
            _local.depth = depth
        return
    with _lock:
        _state["waiting"] += 1
    t0 = time.perf_counter()
    got = _sem.acquire(timeout=WAIT_S)
    waited = time.perf_counter() - t0
    with _lock:
        _state["waiting"] -= 1
        if got:
            _state["running"] += 1
        running, waiting = _state["running"], _state["waiting"]
    if not got:
        print(f"🧮 heavy read {name}: no slot after {waited:.0f} s ({running} running, {waiting} waiting), "
              "answered busy", flush=True)
        raise (busy() if busy else Busy(name))
    before = memory_mb()
    t1 = time.perf_counter()
    _local.depth = 1
    try:
        yield
    finally:
        _local.depth = 0
        ran = time.perf_counter() - t1
        after = memory_mb()
        with _lock:
            _state["running"] -= 1
            running, waiting = _state["running"], _state["waiting"]
        _sem.release()
        print(line(name, before, after, ran, waited, running, waiting), flush=True)
