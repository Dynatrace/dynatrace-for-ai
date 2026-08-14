# Verification & Troubleshooting

## Verification Checklist

Run through these steps after completing setup:

1. Run the app: `npm run ios` or `npm run android`
1. Interact — tap buttons, navigate between screens, trigger network requests
1. Background or close the app (sessions flush on background/close)
1. Open Dynatrace console → Experience Vitals → select your mobile app
1. A user session should appear within 1–2 minutes
1. Confirm route changes appear as views in the session timeline (if navigation tracking is enabled)

## No Data After 5 Minutes

Work through these checks in order:

**1. Re-run the instrumentation script**

```bash
npx instrumentDynatrace
```

The script must be re-run any time `dynatrace.config.js` is modified. Verify that `build.gradle` and `Info.plist` were updated by checking their timestamps or contents after running the script.

**2. Reset Metro cache**

```bash
npx react-native start --reset-cache
```

Metro caches babel output. After any change to `babel.config.js` or `dynatrace.config.js`, a cache reset is required. Rebuild the app after the cache is cleared.

**3. Verify credentials**

Download the authoritative config from the Dynatrace console and compare or replace your local file:

> Experience Vitals → [Your App] → Instrumentation → Cross Platform → React Native → Download dynatrace.config.js

Either replace `dynatrace.config.js` at the project root with the downloaded file, or open both and confirm `applicationId` and `beaconUrl` match. A trailing slash or wrong environment ID in the beacon URL will silently drop all data.

**4. Check opt-in gate (if `userOptIn: true`)**

If `userOptIn: true` is set, the SDK sends no data until `applyUserPrivacyOptions(...)` is called with a non-`Off` `DataCollectionLevel`. Confirm the call has been reached during the test session — place a breakpoint or `console.log` to verify.

**5. Check Android native config**

Open `android/app/build.gradle` and confirm the Dynatrace `dynatrace {}` block is present with correct `applicationId` and `beaconUrl`. If it is missing, re-run `npx instrumentDynatrace`.

**6. Check iOS plist**

Open `ios/<AppName>/Info.plist` and confirm `DTXApplicationID` and `DTXBeaconURL` are present with correct values. If missing, re-run `npx instrumentDynatrace`.

**7. Check network connectivity**

Confirm the device or simulator can reach the `beaconUrl` host. Corporate proxies or emulator network restrictions can block beacon traffic.

Enable debug logging to see agent activity in the console:

Android — add to `dynatrace.config.js` android block:

```
debug {
  agentLogging true
}
```

iOS — add to `dynatrace.config.js` ios block:

```
<key>DTXLogLevel</key>
<string>ALL</string>
```

Re-run `npx instrumentDynatrace` after adding debug logging. Remove it before production builds.

**8. Verify Babel plugin and JSX runtime are active**

Enable `debugBabelPlugin` temporarily in `dynatrace.config.js`:

```js
react: {
  debugBabelPlugin: true,
}
```

After rebuilding, check `node_modules/@dynatrace/react-native-plugin/build` for `.dtx` files showing the instrumented output. If the folder is empty or the files look uninstrumented, the Babel plugin is not being applied.

Remove `debugBabelPlugin: true` after debugging — it significantly increases build time.

If the Babel plugin is active but user interactions and navigation changes still don't appear, the JSX runtime is likely misconfigured. Check `babel.config.js`:

- **Expo (`babel-preset-expo`):** `jsxImportSource: '@dynatrace/react-native-plugin'` must be set as an option on the `babel-preset-expo` preset entry — NOT via a separate `@babel/plugin-transform-react-jsx` plugin. Having both at the same time breaks instrumentation.
- **Bare RN (`@react-native/babel-preset`):** `@babel/plugin-transform-react-jsx` with `importSource: '@dynatrace/react-native-plugin'` must appear as a plugin entry, before `BabelPluginDynatrace`.
