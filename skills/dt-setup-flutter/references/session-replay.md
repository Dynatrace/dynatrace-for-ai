# Session Replay

Use this reference when the user has chosen to enable Session Replay (Step 8). It needs the replay package, a Grail (3rd gen) environment, and the console capability. With `userOptIn: true` it also needs a runtime consent flag, which is added in Step 9 — see `references/user-opt-in.md`.

If `dynatrace_flutter_plugin_replay` is already in `pubspec.yaml`, only fill in what is missing.

## 1 — Check the generation

Session Replay requires Dynatrace 3rd gen (Grail). Confirm `agentBehavior.startupWithGrailEnabled true` (Android) and `DTXStartupWithGrailEnabled` (iOS) are present in `dynatrace.config.yaml`.

- **Present:** continue.
- **Absent:** ask **"Is this a Grail (3rd gen) environment?"** If yes, add both using the Grail block in `references/config-yaml.md`. If no, tell the user Session Replay is not supported on 2nd gen, treat the answer to Step 8 as no, and stop here.

## 2 — Add the replay package

Read `pubspec.yaml`. If `dynatrace_flutter_plugin_replay` is missing, run:

```bash
flutter pub add dynatrace_flutter_plugin_replay
```

No `registerWith` call or other Dart setup is needed. Flutter registers the plugin automatically and recording starts with `Dynatrace().start(...)`. Do not add one.

## 3 — Re-run the configuration script

Only if `dynatrace.config.yaml` changed in this procedure (for example the Grail flags were added):

```bash
dart run dynatrace_flutter_plugin
```

Do not add a `sessionReplay:` section to the config. It is only an optional build-time switch (`enabled: false` disables recording without removing the package); the package alone enables Session Replay.

## 4 — Console capability

The user must also enable Session Replay in Experience Vitals → [Your App] → Settings → Enablement and Cost Control. If the config was downloaded from the console with Session Replay selected in the wizard, this is already done — confirm with the user. The SDK reads this setting remotely via `applicationId`.
