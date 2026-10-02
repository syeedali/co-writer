"""Cancellation shared by streaming and staged research operations."""

import threading


class JobCancelled(Exception):
    pass


class AIJob:
    def __init__(self, page=None):
        self.page = page
        self.cancelled = threading.Event()
        self.response = None
        self.error_callback = None

    def check(self):
        if self.cancelled.is_set():
            raise JobCancelled()

    def cancel(self):
        self.cancelled.set()
        if self.response is not None:
            # Closing a transport can block. Never do that on GTK's thread.
            threading.Thread(target=self._close_response, daemon=True).start()

    def _close_response(self):
        try:
            self.response.close()
        except Exception:
            pass
