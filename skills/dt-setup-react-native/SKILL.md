---
name: dt-setup-react-native
license: Apache-2.0
description: >-
  Integrate the Dynatrace React Native Plugin into a React Native or Expo project —
  dependency setup, dynatrace.config.js, Babel registration, npx instrumentation,
  navigation tracking, user privacy options, and verification. Handles both bare React Native
  and Expo (babel-preset-expo) Babel configuration automatically.
  Trigger: "add Dynatrace to React Native", "React Native plugin setup", "instrument React Native app",
  "integrate Dynatrace RN", "mobile observability React Native", "react-native-plugin",
  "dynatrace react native", "add Dynatrace to Expo", "instrument Expo app", "Dynatrace Expo setup".
  Do NOT use for: querying RN RUM data (use dt-obs-frontends), non-React Native mobile setups,
  or Dynatrace server-side configuration.
---

# Dynatrace React Native Plugin Integration Skill

## Prerequisites

- Node.js 16.0+ and npm available on `PATH`
- An existing React Native project (v0.68+) or Expo project (v45+) with a `package.json` at the project root
- `android/` and `ios/` platform folders present (Expo managed workflow requires `npx expo prebuild` first)
- A Dynatrace environment with access to Experience Vitals (to obtain `applicationId` and `beaconUrl`, or to download `dynatrace.config.js`)
- Console access to Experience Vitals → Mobile to configure app settings (Data Privacy, Enablement and Cost Control)
- macOS with CocoaPods for iOS builds

Work through the steps below in order, interacting with the user at each decision point. Read actual project files before suggesting changes — do not assume the current state.

## Step 1 — Check for existing `dynatrace.config.js`

Before asking the user anything, check whether `dynatrace.config.js` exists at the project root.

- **File exists:** Read it, show the `applicationId` and `beaconUrl`, and confirm they match the target environment. If correct, run the `userOptIn` check below and skip to Step 3 (config is already present — Step 2 is not needed).
- **File does not exist:** Proceed to Step 2.

**`userOptIn` check:**

Inspect the file for `userOptIn` (Android block) and `DTXUserOptIn` (iOS block).

- **Present on both platforms:** Trust the value as-is. If `true`, flag Step 9. If `false`, skip Step 9.
- **Absent from either platform:** Ask the user: **"Do you have User Opt-In mode enabled or disabled?"** (If unsure: Experience Vitals → Mobile → [Your App] → Settings → Data Privacy.) Add the missing value to the relevant platform(s), then flag Step 9 if the final value is `true`.

## Step 2 — Obtain `dynatrace.config.js` (only if Step 1 found no file)

Ask the user which approach they prefer:

**Option A — Download from console (recommended):**

1. Open their Dynatrace environment
1. Navigate to: Experience Vitals → New Frontend → Mobile
1. Enter app name and choose **React Native** as the platform
1. On the **Select capability and settings** screen, configure monitoring features (crash reporting, user action monitoring, etc.)
1. Download `dynatrace.config.js` and place it at the project root (same level as `package.json`)

Once the file is in place, apply the `userOptIn` check from Step 1 and flag Step 9 if needed.

**Option B — Provide credentials manually:**
Read `references/config-js.md` for the full template and conditional blocks. Collect all required values from the user before creating any files, then apply the `userOptIn` check and flag Step 9 if needed.

## Step 3 — Install the plugin

Read `package.json` first.

- **Not present:** Run:
  ```bash
  npm install @dynatrace/react-native-plugin
  ```
- **Already under `dependencies`:** No change needed.
- **Under `devDependencies`:** Remove it and run `npm install @dynatrace/react-native-plugin`. The plugin is required at runtime including in release builds.

Note: `npm install` alphabetically sorts the `dependencies` object in `package.json`. Existing entries may appear reordered after this step — this is expected npm behavior, not an error.

## Step 4 — Install iOS pods (macOS only)

If on macOS and targeting iOS, run:

```bash
cd ios && pod install && cd ..
```

Confirm success before continuing. CocoaPods must be installed (`gem install cocoapods` if missing).

## Step 5 — Register Babel plugin in `babel.config.js`

Read `babel.config.js`. Append `BabelPluginDynatrace` to the `plugins` array, **just before** `react-native-reanimated/plugin` if that plugin is present (reanimated must always be last):

```js
module.exports = {
  presets: ['module:@react-native/babel-preset'],
  plugins: [
    // ... existing plugins ...
    '@dynatrace/react-native-plugin/instrumentation/BabelPluginDynatrace',
    // react-native-reanimated/plugin goes here if present — must stay last
  ],
};
```

- If the plugins array already contains `'@dynatrace/react-native-plugin/instrumentation/BabelPluginDynatrace'`: skip this step.
- If `useLegacyJscodeshift: true` is set in `dynatrace.config.js`: the Babel plugin is already applied internally — skip this step.
- If the project already configures `metro.config.js` with `babelTransformerPath: '@dynatrace/react-native-plugin/lib/dynatrace-transformer'`: that is the legacy Metro transformer approach — auto-instrumentation is already handled; skip this step and Step 6.

Common mistakes to flag and correct:

- Placing the plugin in `presets` instead of `plugins`
- Placing `BabelPluginDynatrace` after `react-native-reanimated/plugin` — reanimated must always be the absolute last plugin

## Step 6 — Register JSX runtime in `babel.config.js`

Read `babel.config.js` and determine which preset the project uses — this controls how the JSX runtime is registered.

### Expo (`babel-preset-expo`)

If `babel-preset-expo` appears in `presets`, set `jsxImportSource` **on the preset itself**. Do not add a separate `@babel/plugin-transform-react-jsx` plugin — Expo's preset already owns the JSX transform, and stacking a second JSX plugin over it breaks the instrumentation.

```js
module.exports = function (api) {
  api.cache(true);
  return {
    presets: [
      ['babel-preset-expo', {
        jsxRuntime: 'automatic',
        jsxImportSource: '@dynatrace/react-native-plugin',
      }],
    ],
    plugins: [
      '@dynatrace/react-native-plugin/instrumentation/BabelPluginDynatrace',
      'react-native-reanimated/plugin',  // stays last
    ],
  };
};
```

- If `babel-preset-expo` already has `jsxImportSource: '@dynatrace/react-native-plugin'`: no change needed.
- If a different `jsxImportSource` is already set: replace it with `'@dynatrace/react-native-plugin'`.
- Remove any existing `@babel/plugin-transform-react-jsx` plugin entry — it must not coexist with the preset-level `jsxImportSource` on `babel-preset-expo`.

### Bare React Native (`@react-native/babel-preset` or `metro-react-native-babel-preset`)

For metro 0.72.0+ (React Native 0.71+), add `@babel/plugin-transform-react-jsx` with the Dynatrace `importSource` **before** `BabelPluginDynatrace` in the plugins array:

```js
module.exports = {
  presets: [
    ['module:@react-native/babel-preset', { unstable_transformProfile: 'hermes-stable' }],
  ],
  plugins: [
    ['@babel/plugin-transform-react-jsx', {
      runtime: 'automatic',
      importSource: '@dynatrace/react-native-plugin',
    }],
    '@dynatrace/react-native-plugin/instrumentation/BabelPluginDynatrace',
    'react-native-reanimated/plugin',  // stays last
  ],
};
```

The required plugin order is:

1. `@babel/plugin-transform-react-jsx` (JSX runtime — first)
1. `BabelPluginDynatrace` (auto-instrumentation — before reanimated)
1. `react-native-reanimated/plugin` (must be absolutely last)

- If the project already has `@babel/plugin-transform-react-jsx` with `importSource: '@dynatrace/react-native-plugin'`: no change needed.
- If a different `importSource` is set: replace it with `'@dynatrace/react-native-plugin'`.

After any Babel change, reset Metro cache on next build:

```bash
npx react-native start --reset-cache
```

## Step 7 — Run `npx instrumentDynatrace`

```bash
npx instrumentDynatrace
```

This reads `dynatrace.config.js` and automatically configures Android `build.gradle` and iOS `Info.plist`. **Must be re-run whenever `dynatrace.config.js` changes.**

Common mistakes to flag and correct:

- Skipping this step after changing `dynatrace.config.js`
- Using `react-native instrument-dynatrace` — same effect but deprecated for RN 0.70+
- Manual edits to `build.gradle` or `Info.plist` — not needed, the script handles it

If `android/` and `ios/` folders exist but automatic plist discovery fails, pass explicit paths:

```bash
npx instrumentDynatrace plist=ios/YourApp/Info.plist
```

**Expo only:** If `android/` and `ios/` folders do not yet exist, run `npx expo prebuild` first, then re-run `npx instrumentDynatrace`.

## Step 7a — Manual SDK startup (only if `autoStart: false`)

**Skip this step if `autoStart` is `true` or absent in `dynatrace.config.js` — the SDK starts automatically.**

Check `dynatrace.config.js` for `autoStart: false` in the `react` block. If present, the SDK will not start on its own and no data will be collected until `Dynatrace.start()` is called explicitly.

Add the startup call at the top level of the app entry file (for example `App.tsx` or `index.js`). Any logic that depends on the SDK being ready goes after the `await`:

```ts
import { Dynatrace, ConfigurationBuilder } from '@dynatrace/react-native-plugin';

await Dynatrace.start(
  new ConfigurationBuilder('<BEACON_URL>', '<APPLICATION_ID>').buildConfiguration()
);
// SDK is initialized — place any SDK-dependent logic here
```

Replace `<BEACON_URL>` and `<APPLICATION_ID>` with **the exact same values** from `dynatrace.config.js` — they must match or the SDK will report to the wrong environment.

**Important:** Even with `autoStart: false`, the `beaconUrl` and `applicationId` must still be present in `dynatrace.config.js` (used by `npx instrumentDynatrace` to configure the native files). The values passed to `ConfigurationBuilder` at runtime take effect — values in the config file are ignored when manual startup is used.

**Tradeoff:** Manual startup causes the SDK to miss the native application start event and any interactions that happen before `start()` is called. Use `autoStart: true` (the default) unless runtime credential injection is a hard requirement.

## Step 8 — Enable navigation tracking

Check `dynatrace.config.js` for the `react.navigation` block and check `package.json` for `@react-navigation/native`.

If `@react-navigation/native` is present and `navigation.enabled` is not set to `true`, add it:

```js
module.exports = {
  react: {
    navigation: {
      enabled: true,  // requires @react-navigation/native v5–v7
    },
    // ...
  },
  // ...
};
```

Then re-run `npx instrumentDynatrace`.

**What this does:** When enabled, the plugin hooks into React Navigation's `NavigationContainer` and detects route changes automatically. Each navigation event is reported to Dynatrace as a view change, with the current route represented as a URL-style path (e.g., `/Home`, `/Home/Details`). This populates the screen timeline in Dynatrace user sessions and associates all events with the currently active screen. This setting is enabled by default in the plugin's own config template.

If `@react-navigation/native` is **not** present: inform the user that automatic view tracking requires `@react-navigation/native`. They can use `Dynatrace.startView("ScreenName")` for manual view tracking instead.

## Step 9 — Privacy options call (only if `userOptIn: true`)

**Skip this step if `userOptIn` was not set to `true` during Steps 1 or 2.**

Read `references/user-opt-in.md` for the full guidance on `DataCollectionLevel`, `crashReportingOptedIn`, and placement options. Ask the user the questions defined there, then apply the call to the relevant file.

## Step 10 — Post-setup summary

Confirm to the user what is active:

**Enabled by default** (when `userOptIn` is `false` or absent):

- ✅ Crash reporting
- ✅ User action tracking (Touchables, Buttons, Pressable, Switch)
- ✅ Network monitoring
- ✅ Error handler
- ✅ Auto-start

> When `userOptIn: true`, all data collection — including crash reporting — is gated on the `applyUserPrivacyOptions(...)` call.

**Configured during this setup:**

- Privacy mode: [userOptIn: true — consent call added / opt-out (SDK default)]
- Navigation tracking: [react.navigation.enabled: true / manual via Dynatrace.startView()]

## Step 11 — Verification

Read `references/verification.md` and show the user the verification checklist. If no data appears after 5 minutes, work through the troubleshooting steps in that file.

## Reference Files

- `references/config-js.md` — Full `dynatrace.config.js` template with Grail and userOptIn conditional blocks
- `references/user-opt-in.md` — `applyUserPrivacyOptions` guidance, `DataCollectionLevel` options, placement options
- `references/verification.md` — Post-setup verification checklist and troubleshooting

## External References

- [@dynatrace/react-native-plugin on npm](https://www.npmjs.com/package/@dynatrace/react-native-plugin) — package changelog, API docs, and latest version
- [Dynatrace React Native Installation Docs](https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/mobile-frontends/react-native) — official setup guide
