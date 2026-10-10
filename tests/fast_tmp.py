"""Temporary files of the backup and recovery tests on tmpfs.

The code under test fsyncs every state file and directory, as it must. On
Btrfs with a slow flush (the T2 SSD: ~25 ms per fsync) a batch test spent
seconds in ~300 fsyncs. Importing this module points tempfile at /dev/shm
when it is a writable tmpfs; an explicit TMPDIR still wins. unittest
discover imports every test module before running any, so the whole run
uses it.
"""
import os
import tempfile

if "TMPDIR" not in os.environ and os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK | os.X_OK):
    tempfile.tempdir = "/dev/shm"
