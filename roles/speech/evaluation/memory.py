"""Optional process memory measurement; evaluation must also import on Windows."""
from __future__ import annotations

import sys


def peak_process_rss_mib() -> float | None:
    """Return Linux process high-water RSS in MiB, or None when unavailable.

    Linux getrusage reports KiB. Other platforms are left unmeasured rather than
    assuming their units or adding a runtime dependency solely for diagnostics.
    https://man7.org/linux/man-pages/man2/getrusage.2.html
    """
    if not sys.platform.startswith('linux'):
        return None
    try:
        import resource
        return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024
    except (ImportError, OSError):
        return None
