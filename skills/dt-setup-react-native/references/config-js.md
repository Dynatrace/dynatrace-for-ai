# dynatrace.config.js — Manual Configuration

Use this reference when the user cannot download `dynatrace.config.js` from the Dynatrace console and needs to create it manually.

- [Required Information](#required-information)
- [Base Config](#base-config-always-include)
- [Conditional Additions](#conditional-additions)
  - [User Opt-In](#user-opt-in--add-to-both-platforms-when-required)
  - [Session Replay](#session-replay-only-if-the-user-enabled-it-in-step-9)
  - [Manual startup](#manual-startup-autostart-false)
  - [Debug logging](#debug-logging-for-troubleshooting-only)
- [After Writing the File](#after-writing-the-file)

## Required Information

Collect all of the following before writing the file:

1. `applicationId` — format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
1. `beaconUrl` — format: `https://<environment-id>.live.dynatrace.com/mbeacon` (or a cluster-specific URL)
1. User Opt-In mode: check Experience Vitals → Mobile → [Your App] → Settings → Data Privacy

## Base Config (always include)

React Native apps always report to Dynatrace 3rd gen (Grail), so the Grail startup flags are part of every config — there is no 2nd gen variant to ask about.

```js
module.exports = {
  react: {
    autoStart: true,
    userInteraction: true,
    navigation: {
      enabled: true,
    },
    lifecycle: {
      // Plugin/console default: no component lifecycle instrumentation.
      // Return true (or filter by filename) only for components the user wants to see.
      instrument: () => false,
      includeUpdate: false,
    },
    input: {
      instrument: () => true,
      actionNamePrivacy: false,
    },
    errorHandler: {
      enabled: true,
      reportFatalErrorAsCrash: true,
    },
  },
  android: {
    config: `
      dynatrace {
        configurations {
          defaultConfig {
            autoStart {
              applicationId '<APPLICATION_ID>'
              beaconUrl '<BEACON_URL>'
            }
            agentBehavior.startupLoadBalancing true
            agentBehavior.startupWithGrailEnabled true
          }
        }
      }
    `,
  },
  ios: {
    config: `
      <key>DTXApplicationID</key>
      <string><APPLICATION_ID></string>
      <key>DTXBeaconURL</key>
      <string><BEACON_URL></string>
      <key>DTXStartupLoadBalancing</key>
      <true/>
      <key>DTXStartupWithGrailEnabled</key>
      <true/>
    `,
  },
};
```

## Conditional Additions

### Session Replay (only if the user enabled it in Step 9)

Android — inside `defaultConfig`:

```
sessionReplay.enabled true
```

This requires `userOptIn true` on Android — the build fails otherwise. iOS has no build-time Session Replay key. See `references/session-replay.md`.

### User Opt-In — add to both platforms when required

Android — inside `defaultConfig`, after the `autoStart` block:

```
userOptIn true
```

or

```
userOptIn false
```

iOS — after `DTXStartupWithGrailEnabled`:

```
<key>DTXUserOptIn</key><true/>
```

or

```
<key>DTXUserOptIn</key><false/>
```

### Manual startup (`autoStart: false`)

Only if the user needs runtime credential injection (see Step 7a in `SKILL.md`). Set `react.autoStart: false` and remove `applicationId` / `beaconUrl` from both native blocks — `npx instrumentDynatrace` rejects them on iOS when `DTXAutoStart` is `false`:

- Android: replace the `autoStart { ... }` block with `autoStart.enabled false` inside `defaultConfig`. Keep the other settings (`agentBehavior.*`, `userOptIn`, `sessionReplay.enabled true`) — they are still applied at build time.
- iOS: `<key>DTXAutoStart</key><false/>` is the only key the plugin guarantees for manual startup; pass opt-in mode at runtime with `ConfigurationBuilder.withUserOptIn(true)`.

### Debug logging (for troubleshooting only)

Android — inside `defaultConfig`:

```
debug {
  agentLogging true
}
```

iOS — add to the iOS config block:

```
<key>DTXLogLevel</key>
<string>ALL</string>
```

Remove debug logging before production builds.

## After Writing the File

- Run `npx instrumentDynatrace` to apply the config to native files.
- If `userOptIn` is `true`: the privacy options call (Step 10) is required — flag it.
- If `userOptIn` is `false`: Step 10 can be skipped.
- Re-run `npx instrumentDynatrace` and reset Metro cache (`npx react-native start --reset-cache`) any time `dynatrace.config.js` is modified.
