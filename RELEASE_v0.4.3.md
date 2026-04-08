# Release Notes — v0.4.3

**Date:** 2026-04-02

---

## Summary

v0.4.3 is a version bump to validate the auto-update pipeline introduced
in v0.4.2. No functional changes.

---

## How to test auto-update

1. Publish a **v0.4.2** GitHub release and attach the v0.4.2 `POBuilder.exe`
   as a release asset.
2. Publish a **v0.4.3** GitHub release and attach the v0.4.3 `POBuilder.exe`
   as a release asset. Mark it as the latest release.
3. Launch the v0.4.2 exe. After ~1.5 seconds it will hit the GitHub releases
   API, detect v0.4.3, and show the download-and-install dialog.
4. Click **Yes** and confirm the app downloads, swaps, and relaunches as
   v0.4.3.

---

## Test count

857 (unchanged from v0.4.2)
