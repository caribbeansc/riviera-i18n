"""The Android build: the same script and artwork, patched into the split APKs of the app."""


class AndroidError(Exception):
    """Base of the errors of the Android build: the command line shows their message and stops, without a traceback."""
