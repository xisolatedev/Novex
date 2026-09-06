"""
CPU core assignment for the Novex pipeline.

Why bother: on a 4-core machine the camera thread, ORB-SLAM3 and the
GUI all compete for the same cores. When they collide the symptom is
not a clean slowdown - it is the capture thread being descheduled
while ORB-SLAM3 optimises, so frames are missed at the USB layer and
never arrive at all. Measured on this machine under load, cap.grab()
alone took 117 ms per frame when the CPU was oversubscribed.

Pinning fixes that by construction: capture gets a core that SLAM can
never take.

Two Linux facts this relies on, both verified on this machine:

  * os.sched_setaffinity(0, mask) applies to the CALLING THREAD, not
    the whole process. The kernel treats thread ids as process ids for
    this call.
  * A thread inherits its creator's affinity mask.

The second one is what makes this practical. ORB-SLAM3 spawns its own
threads - LocalMapping, LoopClosing, and two ORB extractor threads per
stereo frame - and we never see them from Python. Because they are all
created underneath the SLAM worker thread, they inherit its mask
automatically, so pinning that one thread confines the entire SLAM
system.
"""

import glob
import os
import threading


AVAILABLE = hasattr(os, "sched_setaffinity")


def cpu_count():
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def default_layout(n_cores=None):
    """A sensible split of the machine, given how many cores exist.

    The camera thread is mostly blocked on USB and only needs a few ms
    of decode, so it shares its core with the GUI. Everything else goes
    to SLAM, which is the only genuinely CPU-hungry part.
    """
    n = n_cores or cpu_count()

    if n <= 1:
        return {"camera": [0], "slam": [0], "gui": [0]}
    if n == 2:
        return {"camera": [0], "slam": [1], "gui": [0]}

    # 3+ cores: core 0 for capture and GUI, the rest for SLAM.
    return {
        "camera": [0],
        "slam": list(range(1, n)),
        "gui": [0],
    }


def pin_current_thread(cores, label=""):
    """Pin the calling thread (and anything it later spawns).

    Returns a short status string for the debug panel. Never raises:
    a machine that refuses affinity changes should still run, just
    without the isolation.
    """
    if not AVAILABLE:
        return f"{label}: affinity unsupported on this platform"

    if not cores:
        return f"{label}: not pinned"

    try:
        allowed = os.sched_getaffinity(0)
    except OSError:
        allowed = set(range(os.cpu_count() or 1))

    mask = {int(c) for c in cores if int(c) in allowed}
    if not mask:
        return f"{label}: requested cores {list(cores)} unavailable, not pinned"

    try:
        os.sched_setaffinity(0, mask)
    except OSError as exc:
        return f"{label}: pinning failed ({exc})"

    return f"{label}: tid {threading.get_native_id()} -> cores {sorted(mask)}"


class AffinityReport:
    """Collects what actually got pinned, for the debug panel."""

    def __init__(self):
        self._lock = threading.Lock()
        self._lines = []

    def add(self, line):
        with self._lock:
            self._lines.append(line)

    def lines(self):
        with self._lock:
            return list(self._lines)


def _parse_cpu_list(text):
    """Parse the kernel's 'Cpus_allowed_list' format, e.g. '0-2,5'."""
    cores = set()
    for part in text.strip().split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            cores.update(range(int(a), int(b) + 1))
        else:
            cores.add(int(part))
    return cores


def list_thread_affinities():
    """{tid: (name, {cores})} for every thread in this process."""
    out = {}
    for path in glob.glob("/proc/self/task/*"):
        tid = os.path.basename(path)
        try:
            name = open(os.path.join(path, "comm")).read().strip()
            with open(os.path.join(path, "status")) as fh:
                for line in fh:
                    if line.startswith("Cpus_allowed_list"):
                        out[int(tid)] = (name, _parse_cpu_list(line.split(":", 1)[1]))
                        break
        except (OSError, ValueError):
            continue
    return out


def confine_stray_threads(slam_cores, exempt_tids):
    """Move every thread except the exempt ones onto the SLAM cores.

    This exists because of OpenCV. Its parallel_for_ worker pool is
    created LAZILY, on whichever thread first triggers parallel work -
    in practice the main thread, while building the rectification maps.
    Those pool threads therefore inherit the main thread's unrestricted
    mask, and they are the ones that later execute cv2.remap on behalf
    of the SLAM thread. Verified on this machine: three pool threads
    ran with cores 0-3 despite the SLAM worker being pinned to 1-3,
    which put rectification straight back onto the capture core.

    Thread inheritance cannot fix this, because the pool predates the
    SLAM thread. So the strays are simply reassigned afterwards.

    Returns a list of human-readable changes.
    """
    if not AVAILABLE or not slam_cores:
        return []

    target = {int(c) for c in slam_cores}
    exempt = {int(t) for t in exempt_tids if t}
    changes = []

    for tid, (name, cores) in list_thread_affinities().items():
        if tid in exempt or cores == target:
            continue
        try:
            os.sched_setaffinity(tid, target)
            changes.append(f"moved tid {tid} ({name}) {sorted(cores)} -> {sorted(target)}")
        except OSError as exc:
            changes.append(f"could not move tid {tid} ({name}): {exc}")

    return changes
