# PO Builder Release Checklist

Use this checklist for every tagged release.

## 1. Confirm Scope

- confirm the release target version
- confirm the intended scope is stable enough to ship
- confirm the release notes file exists or is ready to write

## 2. Update Versioning

- update [`app_version.py`](C:\Users\Cornelio\Desktop\POCreator\app_version.py)
- ensure any version-sensitive UI or startup-update behavior still reads from the internal app version
- prepare the release notes file as `RELEASE_vX.Y.Z.md`

## 3. Verify The Repo State

- review `git status --short`
- confirm no unrelated local changes are being mixed into the release
- confirm generated data files are not being included by mistake

## 4. Run Automated Checks

- run `python -m unittest discover -s tests -q`
- if tests fail, stop and fix them before continuing

## 5. Build The Executable

- run `build.bat`
- confirm `dist\POBuilder.exe` is created successfully
- confirm optional asset behavior is acceptable if `loading.gif`, `loading.wav`, or `icon.ico` are missing

## 6. Smoke Test The Packaged App

Test the built `.exe`, not only source execution.

- launch `dist\POBuilder.exe`
- verify the app opens without blocking startup errors
- load representative X4 CSV exports
- walk through load -> assign -> review -> export
- confirm at least one multi-vendor export succeeds
- confirm maintenance output and session snapshot behavior still work
- if shared-folder behavior changed, test both local and shared data modes

## 7. Finalize Release Notes

Each release note should include:

- release title and date
- summary
- highlights
- functional or workflow detail where needed
- verification notes

## 8. Tag And Publish

- commit the release preparation changes
- create the annotated Git tag `vX.Y.Z`
- push the branch and tag
- create or update the GitHub release using the release notes

## 9. Post-Release Verification

- confirm the GitHub release tag matches the internal app version
- confirm the startup update check points users at the expected latest release
- confirm teammates can download and run the released executable
