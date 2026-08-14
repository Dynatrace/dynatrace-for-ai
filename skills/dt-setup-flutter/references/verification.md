# Verification & Troubleshooting

## Verification Checklist

Run through these steps after completing setup:

1. Run the app: `flutter run`
2. Interact — tap buttons, navigate between screens
3. Background or close the app (sessions flush on background/close)
4. Open Dynatrace console → Experience Vitals → select your mobile app
5. A user session should appear within 1–2 minutes
6. Confirm route changes appear as views in the session timeline

## No Data After 5 Minutes

Work through these checks in order:

**1. Re-run the configuration script**
```bash
dart run dynatrace_flutter_plugin
```
The script must be re-run any time `dynatrace.config.yaml` is modified.

**2. Verify credentials**

Download the authoritative config from the Dynatrace console and compare or replace your local file:

> Experience Vitals → [Your App] → Instrumentation → Cross Platform → Flutter → Download dynatrace.config.yaml

Either replace `dynatrace.config.yaml` at the project root with the downloaded file, or open both and confirm `applicationId` and `beaconUrl` match. A trailing slash or wrong environment ID in the beacon URL will silently drop all data.

**3. Check opt-in gate (if `userOptIn: true`)**

If `userOptIn: true` is set, the SDK sends no data until `applyUserPrivacyOptions(...)` is called. Confirm the call has been reached during the test session — place a breakpoint or log statement to verify.

**4. Check network connectivity**

Confirm the device or simulator can reach the `beaconUrl` host. Corporate proxies or emulator network restrictions can block beacon traffic.
