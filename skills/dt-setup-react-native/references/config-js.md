# dynatrace.config.js — Manual Configuration

Use this reference when the user cannot download `dynatrace.config.js` from the Dynatrace console and needs to create it manually.

- [Required Information](#required-information)
- [Base Config](#base-config-always-include)
- [Conditional Additions](#conditional-additions)
  - [3rd gen (Grail) only](#3rd-gen-grail-only)
  - [User Opt-In](#user-opt-in--add-to-both-platforms-when-required)
  - [Debug logging](#debug-logging-for-troubleshooting-only)
- [After Writing the File](#after-writing-the-file)

## Required Information

Collect all of the following before writing the file:

1. `applicationId` — format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
1. `beaconUrl` — format: `https://<environment-id>.live.dynatrace.com/mbeacon` (or a cluster-specific URL)
1. Dynatrace generation: **2nd gen** or **3rd gen (Grail)**
1. User Opt-In mode: check Experience Vitals → Mobile → [Your App] → Settings → Data Privacy

## Base Config (always include)

```js
module.exports = {
  react: {
    autoStart: true,
    userInteraction: true,
    navigation: {
      enabled: true,
    },
    lifecycle: {
      instrument: () => true,
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
    `,
  },
};
```

## Conditional Additions

### 3rd gen (Grail) only

Android — inside `defaultConfig`, after the `autoStart` block:

```
agentBehavior.startupLoadBalancing true
agentBehavior.startupWithGrailEnabled true
```

iOS — after `DTXStartupLoadBalancing` (already in base config):

```
<key>DTXStartupWithGrailEnabled</key>
<true/>
```

These keys enable Grail-optimised startup behaviour and load balancing. Without them the SDK still connects to a Grail tenant, but startup performance is not optimal.

### User Opt-In — add to both platforms when required

Android — inside `defaultConfig`, after the `autoStart` block:

```
userOptIn true
```

or

```
userOptIn false
```

iOS — after `DTXStartupLoadBalancing` (and after `DTXStartupWithGrailEnabled` if present):

```
<key>DTXUserOptIn</key><true/>
```

or

```
<key>DTXUserOptIn</key><false/>
```

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
- If `userOptIn` is `true`: the privacy options call (Step 9) is required — flag it.
- If `userOptIn` is `false`: Step 9 can be skipped.
- Re-run `npx instrumentDynatrace` and reset Metro cache (`npx react-native start --reset-cache`) any time `dynatrace.config.js` is modified.
