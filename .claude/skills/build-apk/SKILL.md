---
name: build-apk
description: Build an installable DuckDetector APK for the user's phone and hand it over. Use when the user asks to build, rebuild, update or install the app, wants the latest code on their phone, or a "Build debug APK" GitHub Actions run failed.
---

# Build the DuckDetector APK

## Why the build runs on GitHub, not here

- A cloud session cannot reach `dl.google.com`, which serves the Android SDK, NDK and CMake that
  `:app:assembleDebug` needs, so a local Gradle build fails before compiling anything.
- `.github/workflows/build.yml` (the upstream release build) needs the upstream signing keystore
  and a Telegram bot in a `Telegram` environment; this repository has neither, so it always fails.
- `.github/workflows/debug-apk.yml` builds a debug-signed APK with no secrets and uploads it as the
  `duckdetector-debug-apk` artifact (kept 30 days). It runs on every push to `main` and to the
  session branch listed in its `on.push.branches`, and can also be run manually (workflow_dispatch).
  If you work on a new branch, add it to that list in the same commit, or the push builds nothing.

## Steps

1. Commit and push the change to the designated branch. The push starts "Build debug APK".
2. Find the run: `mcp__github__actions_list` with `method: list_workflow_runs`,
   `resource_id: debug-apk.yml`, and match `head_sha` to the pushed commit.
3. Do not poll. A full build takes about 10 minutes (toolchain install ~2 min, then Gradle and four
   native ABIs). Schedule one check-in with `mcp__claude-code-remote__send_later` (about 15
   minutes) and end the turn; tell the user when you will check.
4. On success: `list_workflow_run_artifacts` for the run, then give the user the run page link
   `https://github.com/<owner>/<repo>/actions/runs/<run_id>` and the install steps below. The
   artifact's blob download URL is on `*.blob.core.windows.net`, which the session proxy blocks, so
   the APK cannot be fetched here and sent as a file; the user downloads it from the run page while
   signed in to GitHub (artifacts require sign-in, even on a public repository).
5. On failure: go to "Diagnosing a failure", fix, push, and check again.

## Install steps to give the user

1. On the phone, open the run page signed in to GitHub, scroll to **Artifacts**, and download
   `duckdetector-debug-apk` (a zip of about 40 MB).
2. Open the zip in the Files app and tap the `.apk` inside.
3. Allow that app to install unknown apps when Android asks, then tap **Install**. Play Protect may
   warn because the build is debug-signed; choose **Install anyway**.
4. A build signed with a different key cannot install over an existing copy (for example the
   official upstream release, or a build from another machine's debug key). Uninstall the old copy
   first. GitHub runners generate a fresh debug key, so successive builds from this workflow may also
   need an uninstall first; if Android says "App not installed" or "package conflicts", that is why.
5. Requirements: Android 10 (API 29) or later; root is not needed.
6. After a scan, the user can tap **Export Report** and upload the file; the `read-scan-report`
   skill explains it.

## Diagnosing a failure

The job log is very large (hundreds of thousands of characters, mostly `##[debug]` lines and
Gradle cache cleanup), and its tail is post-job cleanup, so the default 500-line tail never shows
the error. Fetch it with `mcp__github__get_job_logs` (`job_id`, `return_content: true`,
`tail_lines: 20000`); the result is saved to a file. Filter that file rather than reading it whole:

```bash
python3 -I -c "
import json,sys
d=json.load(open(sys.argv[1]))
t=d.get('logs_content') or d['logs'][0]['logs_content']
for l in t.split('\n'):
    if '##[debug]' not in l and 'Removing empty directory' not in l: print(l[29:330])
" <saved-file> | grep -n -A25 'What went wrong\|##\[error\]'
```

Known causes:

| Symptom | Cause and fix |
| --- | --- |
| `Using multiple versions of the Android Gradle plugin(9.5.1, 9.5.0)` / `Could not resolve project ':uihelper'` | The `uihelper` submodule (an included build) and the app use different AGP versions. Pin `uihelper` to a commit whose `gradle/libs.versions.toml` `agp` matches the app's (`cd uihelper && git checkout <sha> && cd .. && git add uihelper`), or bump the app's `agp` in `gradle/libs.versions.toml` to match, never both halfway. |
| `The uihelper submodule is not checked out` | Checkout without submodules; the workflow's checkout step must keep `submodules: true`. |
| `sdkmanager` install failures | Transient; re-run the job. If persistent, a version in `gradle.properties` (`duckdetector.android.*`) is no longer published. |
| Configuration fails with a module-boundary violation | A code change broke a rule in `.github/policies/module-boundaries.json`; fix the code, not the policy. |
| `ModuleBoundaryValidator` or `checkPublicApi` errors | Only CI's `ci.yml` runs those; `debug-apk.yml` runs only `assembleDebug`. |

Before pushing a code fix, run what can run here: the Python policy checks under
`.github/scripts/` (`python3 -I .github/scripts/check-<name>.py`) need no Android SDK. Gradle
tasks cannot run in this session, so the workflow run is the build check; say so when reporting.

Dependabot opens dependency-bump pull requests in this repository. A bump to `agp` in the app
without the matching `uihelper` bump reintroduces the first failure above.
