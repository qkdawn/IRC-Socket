"""Helpers for testing queued socket delivery without a live listener."""

import threading


def start_writer(test, session):
    worker = threading.Thread(target=session._write_loop, daemon=True)
    worker.start()

    def cleanup():
        session.close()
        worker.join(2)
        test.assertFalse(worker.is_alive(), "session writer did not stop")

    test.addCleanup(cleanup)
    return worker
