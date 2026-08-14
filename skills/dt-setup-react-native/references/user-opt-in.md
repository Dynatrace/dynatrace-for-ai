# User Opt-In & Privacy Options

Use this reference when `userOptIn: true` is present in `dynatrace.config.js`. With opt-in mode enabled, the SDK collects **no data** until the app explicitly grants consent via `applyUserPrivacyOptions(...)`.

## Before Placing the Call

Ask the user two questions:

**1. Which `DataCollectionLevel` do you want?**

| Level                              | What is collected                                                         |
| ---------------------------------- | ------------------------------------------------------------------------- |
| `DataCollectionLevel.UserBehavior` | Crashes, performance, and user behaviour (taps, navigation, interactions) |
| `DataCollectionLevel.Performance`  | Crashes and performance only — no user behaviour                          |
| `DataCollectionLevel.Off`          | Nothing — monitoring paused entirely                                      |

**2. Should crash reporting be opted in?**

The second argument to `UserPrivacyOptions` is `crashReportingOptedIn`. Default: `true` (crash reports sent). Set `false` to suppress crash reports.

## Placement Options

### Option 1 — User-facing consent screen (recommended for production)

Call `applyUserPrivacyOptions` when the user accepts your privacy policy or consent prompt.

```ts
import { Dynatrace, DataCollectionLevel, UserPrivacyOptions } from '@dynatrace/react-native-plugin';

Dynatrace.applyUserPrivacyOptions(
  new UserPrivacyOptions(DataCollectionLevel.UserBehavior, true),
);
```

Replace `DataCollectionLevel.UserBehavior` with `DataCollectionLevel.Performance` if chosen.
Replace `true` with `false` to suppress crash reporting.

### Option 2 — Root component `useEffect` (testing only)

```ts
import { useEffect } from 'react';
import { Dynatrace, DataCollectionLevel, UserPrivacyOptions } from '@dynatrace/react-native-plugin';

function App() {
  useEffect(() => {
    Dynatrace.applyUserPrivacyOptions(
      new UserPrivacyOptions(DataCollectionLevel.UserBehavior, true),
    );
  }, []);

  return /* ... */;
}
```

⚠️ Option 2 silently opts in all users without consent. Use for local testing only — move to a proper consent flow before release.

## Checking Current Privacy Options

```ts
import { Dynatrace } from '@dynatrace/react-native-plugin';

Dynatrace.getUserPrivacyOptions().then((currentOptions) => {
  console.log(currentOptions.dataCollectionLevel);
  console.log(currentOptions.crashReportingOptedIn);
});
```

## Updating Privacy Options at Runtime

Options can be changed at any time (for example, when the user changes their consent in Settings):

```ts
import { Dynatrace, DataCollectionLevel, UserPrivacyOptions } from '@dynatrace/react-native-plugin';

// User revokes consent
Dynatrace.applyUserPrivacyOptions(
  new UserPrivacyOptions(DataCollectionLevel.Off, false),
);
```

## After Placing the Call

Apply the chosen placement to the relevant file. Confirm with the user which option they chose so it is reflected in the Step 10 summary.
