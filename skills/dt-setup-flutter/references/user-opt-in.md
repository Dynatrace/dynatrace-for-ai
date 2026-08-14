# User Opt-In & Privacy Options

Use this reference when `userOptIn: true` is present in `dynatrace.config.yaml`. With opt-in mode enabled, the SDK collects **no data** until the app explicitly grants consent via `applyUserPrivacyOptions(...)`.

## Before Placing the Call

Ask the user two questions:

**1. Which `DataCollectionLevel` do you want?**

| Level | What is collected |
|---|---|
| `DataCollectionLevel.UserBehavior` | Crashes, performance, and user behaviour (taps, navigation, interactions) |
| `DataCollectionLevel.Performance` | Crashes and performance only — no user behaviour |

**2. Should crash reporting be opted in?**

The second argument to `UserPrivacyOptions` is `crashReportingOptedIn`. Default: `true` (crash reports sent). Set `false` to suppress crash reports.

## Placement Options

### Option 1 — User-facing consent screen (recommended for production)

Call `applyUserPrivacyOptions` when the user accepts your privacy policy or consent prompt.

```dart
Dynatrace().applyUserPrivacyOptions(
  UserPrivacyOptions(DataCollectionLevel.UserBehavior, true),
);
```

Replace `DataCollectionLevel.UserBehavior` with `DataCollectionLevel.Performance` if chosen.
Replace `true` with `false` to suppress crash reporting.

### Option 2 — Root widget `initState` (testing only)

```dart
@override
void initState() {
  super.initState();
  Dynatrace().applyUserPrivacyOptions(
    UserPrivacyOptions(DataCollectionLevel.UserBehavior, true),
  );
}
```

⚠️ Option 2 silently opts in all users without consent. Use for local testing only — move to a proper consent flow before release.

## After Placing the Call

Apply the chosen placement to the relevant file. Confirm with the user which option they chose so it is reflected in the Step 10 summary.
