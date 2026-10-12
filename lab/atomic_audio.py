"""Atomic audio/training metadata publication with short Windows sharing retries."""
import os
import time


def replace_file(source, destination, timeout=1.0):
    """Keep the previous file complete when a reader temporarily denies share-delete.

    Only native Windows access/sharing/lock violations are retried. An exhausted
    deadline preserves both the previous destination and the fully written part.
    """
    deadline = time.monotonic() + max(0.0, min(1.0, timeout))
    while True:
        try:
            os.replace(source, destination)
            return
        except OSError as error:
            remaining = deadline - time.monotonic()
            if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 32, 33) or remaining <= 0:
                raise
            time.sleep(min(0.01, remaining))
