# SPEC-012: Switching off the licence check of your own copy

The patched Android app is re-signed with a key of your own, so the licence client the app carries (Google Play's PairIP) refuses it
and the app closes at start-up. The Android build can disable that check **in the copy it is patching** (`--keep-license-check` leaves
it alone). It is for an app you bought; see [ANDROID.md](../ANDROID.md) and `riviera/android/licensecheck.py`.

The change is one method: `com.pairip.licensecheck.LicenseClient.initializeLicenseCheck()V`. Its instructions become `return-void`
followed by `nop`, in place, so the size and every offset of the dex stay as they are, and the checksum and signature of the header are
recomputed.

## Requirements

- **R-1** The method is found by the name of its class, its own name and its prototype `()V`, in the dex files of the app; a dex that does
  not have it is reported as such.
- **R-2** Only the instructions of that method change: the first unit becomes `return-void` (`0x000E`), the others `nop`; the file has the
  same size, and the only other bytes that change are the checksum and the signature of the header.
- **R-3** After patching, the Adler-32 checksum (bytes 12 to the end) and the SHA-1 signature (bytes 32 to the end) in the header are valid.
- **R-4** Patching a dex that is already patched changes nothing.
- **R-5** A dex without the licence client raises `LicenseCheckNotFound`; something that is not a dex raises `LicenseCheckError`.
