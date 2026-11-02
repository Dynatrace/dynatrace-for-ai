# Session Replay

Use this reference when the user has chosen to enable Session Replay (Step 9). It needs the Grail startup flags, a recent plugin, the replay package, an Android build flag, one runtime call, and the console capability. With `userOptIn: true` it also needs a runtime consent flag, added in Step 10 — see `references/user-opt-in.md`.

If `@dynatrace/react-native-session-replay` is already in `package.json`, only fill in what is missing.

- [0 — Requirements](#0--requirements)
- [1 — Check the Grail startup flags](#1--check-the-grail-startup-flags)
- [2 — Check the plugin version](#2--check-the-plugin-version)
- [3 — Add the replay package](#3--add-the-replay-package)
- [4 — Android build flag](#4--android-build-flag)
  - [Opt-in mode is required](#opt-in-mode-is-required)
- [5 — Turn Session Replay on in code](#5--turn-session-replay-on-in-code)
- [6 — Masking](#6--masking-ask-the-user)
- [7 — Console capability](#7--console-capability)
- [8 — Rebuild](#8--rebuild)

## 0 — Requirements

Tell the user up front:

- Session Replay needs React Native 0.67+ (the package's own peer-dependency floor; the core plugin alone supports 0.62+). For Expo this means SDK 45 or newer. Also React 16.11+, Android API 23+, iOS 15+.
- The package is versioned `0.x`: npm's default `^0.x.y` range only takes patch updates, so a newer minor version must be installed by hand.

## 1 — Check the Grail startup flags

React Native apps always run on Dynatrace 3rd gen (Grail) — there is no generation question to ask. Confirm `agentBehavior.startupWithGrailEnabled true` (Android) and `DTXStartupWithGrailEnabled` (iOS) are present in `dynatrace.config.js`; a config downloaded from the console has them.

- **Present:** continue.
- **Absent** (for example an older hand-written config): add both as shown in the base config in `references/config-js.md`, then re-run `npx instrumentDynatrace`.

## 2 — Check the plugin version

The replay package requires `@dynatrace/react-native-plugin` 2.349.1 or newer (peer dependency) and uses the native agent version that the plugin brings — no native version pinning is needed or allowed here.

Read `package.json`. If the plugin is older than 2.349.1, upgrade it first:

```bash
npm install @dynatrace/react-native-plugin@latest
```

After upgrading, re-run `npx instrumentDynatrace` and, on iOS, `cd ios && pod install`.

## 3 — Add the replay package

If `@dynatrace/react-native-session-replay` is missing from `dependencies`, run:

```bash
npm install @dynatrace/react-native-session-replay
cd ios && pod install && cd ..
```

If it is under `devDependencies`, move it to `dependencies` — it is required at runtime, including in release builds. Pods must be reinstalled after adding the package.

## 4 — Android build flag

Android needs Session Replay enabled in the Dynatrace Gradle config (the default is off). Check the `android.config` block of `dynatrace.config.js`. If `sessionReplay.enabled true` is missing, add it inside `defaultConfig`, then re-run `npx instrumentDynatrace`:

```
sessionReplay.enabled true
```

iOS has no build-time Session Replay key. A config downloaded from the console with Session Replay selected already contains the Android line.

Why this matters: without the flag the Android build still succeeds and `SessionReplay.configure({ enabled: true })` throws no error, but the agent reports Session Replay as disabled, so nothing is recorded and `SessionReplay.isEnabled()` returns `false`. The flag also adds the build-time hooks for WebViews, dialogs, popups, scrolling and fragments.

### Opt-in mode is required

The Android Gradle plugin fails the build when `sessionReplay.enabled true` is set without `userOptIn true` (`Property 'userOptIn' must be enabled when Session Replay is used`). So when the user chose Session Replay:

- `userOptIn` is already `true` on Android: nothing to change.
- `userOptIn` is `false` or absent: tell the user that Session Replay requires User Opt-In mode, and that the app then collects no data until it calls `applyUserPrivacyOptions(...)` with their consent. If they accept, set `userOptIn true` (Android) and `<key>DTXUserOptIn</key><true/>` (iOS, to keep both platforms in the same privacy mode), re-run `npx instrumentDynatrace`, and treat Step 10 as required. If they decline, treat the answer to Step 9 as no, remove `sessionReplay.enabled true` if it was added, and stop here.

## 5 — Turn Session Replay on in code

Unlike the native agents, the React Native package records only after an explicit call. Add it once at the app root (for example `App.tsx`):

```ts
import React, { useEffect } from 'react';
import { SessionReplay } from '@dynatrace/react-native-session-replay';

const App = () => {
  useEffect(() => {
    SessionReplay.configure({ enabled: true });
  }, []);

  return <YourAppEntry />; // keep the existing root component content
};
```

- With `autoStart: false` (Step 7a), call `configure` after `await Dynatrace.start(...)`, and build the configuration with `.withUserOptIn(true)` — Session Replay requires opt-in mode.
- `SessionReplay.isEnabled()` reports the effective state — it is `false` when the console capability (section 7) is off, even after `configure({ enabled: true })`.
- Navigation and `FlatList` / `SectionList` reloads are captured automatically. For another moment, `SessionReplay.trackCustomEvent('User logged in')` is available.

## 6 — Masking (ask the user)

Ask: **"Which masking level do you want for Session Replay?"** Until a level is set, the native agent's masking defaults apply.

| Level | What is masked |
|---|---|
| `Safest` | All editable text fields, images, labels, WebViews and switches |
| `Safe` | All editable text fields and WebViews |
| `Custom` | Starts like `Safest`; the app chooses which view types stay masked |

Apply it after `configure`; a call before `SessionReplay.configure({ enabled: true })` is ignored:

```ts
import { SessionReplay, MaskingConfiguration, MaskableView } from '@dynatrace/react-native-session-replay';

SessionReplay.setMaskingConfiguration(MaskingConfiguration.Safest());

// Custom: mask only TextInput fields
SessionReplay.setMaskingConfiguration(
  MaskingConfiguration.Custom()
    .removeAllMaskedViews()
    .addMaskedViews([MaskableView.TextInput]),
);
```

`MaskableView` covers `TextInput`, `Text`, `Image`, `WebView` and `Switch`. `TextInput` components with `secureTextEntry` are always masked. To mask a single component regardless of level, wrap it in `DTMask` or build a masked variant with `DTWithMask`:

```ts
import { Text, TextInput } from 'react-native';
import { DTMask, DTWithMask } from '@dynatrace/react-native-session-replay';

<DTMask>
  <Text>Sensitive data</Text>
</DTMask>;

const MaskedTextInput = DTWithMask(TextInput);
```

## 7 — Console capability

The user must also enable Session Replay in Experience Vitals → [Your App] → Settings → Enablement and Cost Control. If the config was downloaded from the console with Session Replay selected in the wizard, this is already done — confirm with the user. The SDK reads this setting remotely via `applicationId`; turning it off there stops recording even when the code is in place.

## 8 — Rebuild

After any change here, reset the Metro cache and rebuild both platforms:

```bash
npx react-native start --reset-cache
```

Session Replay logs follow the plugin's debug setting: `react: { debug: true }` in `dynatrace.config.js`.
