---
name: dt-obs-ios
description: 'Set up the Dynatrace iOS SDK (OneAgent) in an iOS project using Swift Package Manager. Automates adding the SPM dependency, creating a Dynatrace.plist configuration file, adding the import statement, adding privacy opt-in code, and building the project. Use this skill when the user wants to integrate, install, add, or set up Dynatrace monitoring in their iOS app. Keywords: Dynatrace, iOS, SDK, OneAgent, setup, install, integrate, SPM, Swift Package Manager, Info.plist, DTXApplicationID, DTXBeaconURL, mobile monitoring, RUM.'
license: Apache-2.0
compatibility: Requires macOS, Xcode 16+, and the Xcode MCP server
argument-hint: Paste your dynatrace-ios-setup-config block, or provide DTXApplicationID and DTXBeaconURL
metadata:
  author: dynatrace
  version: '1.0'
---

# Dynatrace iOS SDK Setup

This skill sets up the Dynatrace iOS SDK (OneAgent) in the user's iOS project — from zero to first event. It follows the official setup flow from the [Dynatrace documentation](https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/mobile-frontends/ios/id-01-initial-setup).

## When to use this skill

- The user wants to add Dynatrace monitoring to their iOS app
- The user asks to integrate, install, or set up the Dynatrace iOS SDK
- The user wants to instrument their iOS app with Dynatrace
- The user pastes a setup prompt copied from the Experience Vitals wizard

## Pre-filled values

When invoked from the Experience Vitals wizard, the user's message will contain
pre-filled configuration values in a fenced block labeled
`dynatrace-ios-setup-config`. Example:

````text
```dynatrace-ios-setup-config
DTXApplicationID: ABC-123
DTXBeaconURL: https://example.dynatrace.com/mbeacon
Product: DynatraceSessionReplay
DTXUserOptIn: true
```
````

When these values are present:

- **Skip step 2** (Collect application identification keys) — use the provided
  `DTXApplicationID` and `DTXBeaconURL`.
- **Skip the product question in step 3** — use the provided `Product` value
  (`Dynatrace` or `DynatraceSessionReplay`).
- **Use `DTXUserOptIn`** to determine whether to add the privacy opt-in code in
  step 5. If `true`, add the opt-in code. If `false`, skip step 5.

All other steps (prerequisites, SPM dependency, plist creation, import, build,
verify) proceed as normal.

## Procedure

### 1. Check prerequisites

Actively verify each prerequisite before proceeding. If any check fails, inform the user and stop.

**a) Xcode MCP server is available**
This is a hard requirement. The skill uses the Xcode MCP server to interact with the Xcode project (adding SPM dependencies, building, etc.). Verify that Xcode MCP tools are accessible (e.g., `mcp_xcode_XcodeListWindows`). If not available, tell the user to install and enable the Xcode MCP server before proceeding.

**b) iOS deployment target >= 12.0**
The `.pbxproj` file is not accessible through the Xcode MCP server (it's project metadata, not a navigator file). Use `grep` in the terminal instead:

```bash
grep 'IPHONEOS_DEPLOYMENT_TARGET' <path/to/project.pbxproj>
```

Check that all deployment target values are >= 12.0. If any are below 12.0, tell the user to update them.

**c) Xcode version >= 16.0**
Run `xcodebuild -version` in the terminal to verify. If below 16.0, tell the user to update Xcode.

**d) Ruby + `xcodeproj` gem**
Needed by [scripts/add_spm_dependency.rb](./scripts/add_spm_dependency.rb) in step 3. Check:

```bash
ruby -e 'require "xcodeproj"; puts Xcodeproj::VERSION'
```

If it fails, run `gem install xcodeproj` and retry.

### 2. Collect application identification keys

If the user's message contains a `dynatrace-ios-setup-config` block (see
[Pre-filled values](#pre-filled-values)), extract `DTXApplicationID` and
`DTXBeaconURL` from there and skip to step 3.

Otherwise, ask the user for the two required values:

- **DTXApplicationID** — the application's unique identifier
- **DTXBeaconURL** — the beacon endpoint URL (e.g., `https://{environment}.dynatrace.com/mbeacon`)

If the user already provided these values in their message, skip asking.

If the user doesn't have these values or doesn't know how to get them, refer them to the official setup documentation: https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/mobile-frontends/ios/id-01-initial-setup

### 3. Add OneAgent to the project (SPM dependency)

Add the Dynatrace Swift Mobile SDK via Swift Package Manager.

If the user's message contains a `dynatrace-ios-setup-config` block with a
`Product` value, use that directly. Otherwise, ask the user which product they
want:

- **Dynatrace** — OneAgent for automatic mobile app instrumentation
- **DynatraceSessionReplay** — OneAgent + Session Replay module (replay on crash)

**SPM package URL:** `https://github.com/Dynatrace/swift-mobile-sdk.git`

Run the bundled Ruby script [scripts/add_spm_dependency.rb](./scripts/add_spm_dependency.rb). It uses the `xcodeproj` gem to add the package reference, product dependency, and frameworks build-file entry correctly — no string manipulation of `.pbxproj`.

```bash
ruby ./scripts/add_spm_dependency.rb \
  <ProjectPath> \
  https://github.com/Dynatrace/swift-mobile-sdk.git \
  8.0.0 \
  <Product> \
  [TargetName]
```

- `ProjectPath` — e.g. `./MyApp.xcodeproj`
- `<Product>` — `Dynatrace` or `DynatraceSessionReplay` (from step 3 choice)
- `TargetName` — optional; defaults to the first application target in the project

The script is idempotent — running it twice is a no-op. Prints `OK: project saved` on success.

**If the script fails for any reason** (unusual project layout, Ruby unavailable), fall back to guiding the user through Xcode manually:

1. Open the project in Xcode
1. **File > Add Package Dependencies...**
1. Enter URL: `https://github.com/Dynatrace/swift-mobile-sdk.git`
1. **Up to Next Major Version** from `8.0.0`
1. Add the chosen library to the app target
1. Click **Add Package**

After the script succeeds (or the user confirms manual addition), proceed to step 4.

### 4. Create Dynatrace.plist configuration

Use `mcp_xcode_XcodeWrite` to create a new `Dynatrace.plist` file in the app's main source directory. This ensures the file is automatically registered in the Xcode project.

Content:

```text
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>DTXApplicationID</key>
    <string>{USER_PROVIDED_APP_ID}</string>
    <key>DTXBeaconURL</key>
    <string>{USER_PROVIDED_BEACON_URL}</string>
    <key>DTXUserOptIn</key>
    {USER_OPT_IN_VALUE}
    <key>DTXStartupLoadBalancing</key>
    <true/>
    <key>DTXStartupWithGrailEnabled</key>
    <true/>
</dict>
</plist>
```

Replace `{USER_PROVIDED_APP_ID}` and `{USER_PROVIDED_BEACON_URL}` with the actual values from step 2.
Replace `{USER_OPT_IN_VALUE}` with `<true/>` or `<false/>` based on the `DTXUserOptIn` value from the config block. If no config block is provided, default to `<true/>`.

- `DTXUserOptIn` — when `true`, starts the agent with data collection OFF, requiring explicit opt-in via the privacy API (configured in step 5). When `false`, data collection starts immediately without requiring opt-in, and step 5 is skipped.
- `DTXStartupLoadBalancing` — enables load balancing across cluster nodes on startup.
- `DTXStartupWithGrailEnabled` — enables RUM on the latest Dynatrace on the first app start before the cluster configuration is received. Once the cluster config is cached, this flag is permanently overridden.

### 5. Add user opt-in privacy configuration

Use `mcp_xcode_XcodeRead` to read the app's entry point file, then use `mcp_xcode_XcodeUpdate` to add the privacy configuration code with a TODO comment so the user knows to move it to the appropriate place (e.g., a privacy settings screen):

**For SwiftUI apps (`@main` App struct file):**
Add the following inside the `App` struct's `init()` method (create one if it doesn't exist):

```text
init() {
    // TODO: Move this privacy configuration to your app's privacy settings screen.
    // These settings are provided here for a quick start with capturing monitoring data.
    // In production, this should be driven by user consent (e.g., a privacy settings screen).
    let privacyConfig = Dynatrace.userPrivacyOptions()
    privacyConfig.dataCollectionLevel = .userBehavior
    privacyConfig.crashReportingOptedIn = true
    Dynatrace.applyUserPrivacyOptions(privacyConfig) { (successful) in
        // callback after privacy changed
    }
}
```

**For UIKit apps (AppDelegate):**
Add the same code inside `application(_:didFinishLaunchingWithOptions:)`.

### 6. Add the Dynatrace import

Use `mcp_xcode_XcodeUpdate` to add `import Dynatrace` to the app's entry point file.

**For SwiftUI apps:** Add to the file containing the `@main` App struct.

**For UIKit apps:** Add to `AppDelegate.swift`.

### 7. Build and run

Use the Xcode MCP server to build the project:

- Build the project using `mcp_xcode_BuildProject`
- If the build succeeds, report success to the user
- If the build fails, show the build errors and help the user resolve them

### 8. Verify installation

Run the bundled verification script [scripts/verify-setup.sh](./scripts/verify-setup.sh). It asserts build output, plist values, simulator launch, and agent startup — all serially with `set -e`, hard-failing with distinct exit codes.

**Invocation:**

```bash
./scripts/verify-setup.sh <ProjectPath> <SchemeName> \
  <ExpectedAppID> <ExpectedBeaconURL> [ExpectedOptIn]
```

Arguments (discover from the Xcode project and the values used in step 2/4):

- `ProjectPath` — e.g. `./MyApp.xcodeproj`
- `SchemeName` — run `xcodebuild -list -project <ProjectPath>` to see available schemes, then pick the correct app scheme (not test or irrelevant schemes)
- `ExpectedAppID` — the `DTXApplicationID` value written to `Dynatrace.plist`
- `ExpectedBeaconURL` — the `DTXBeaconURL` value written to `Dynatrace.plist`
- `ExpectedOptIn` — optional; `true` or `false`. Pass the `DTXUserOptIn` value used in step 4 to assert it. Omit to skip.

**Exit codes:**

| Code | Meaning                                                                             | Action                                                                                                    |
| ---- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `0`  | All checks passed; plist values correct; agent startup log seen                     | Report success                                                                                            |
| `2`  | Build output missing framework, missing plist, or plist values don't match expected | SPM link / plist target membership / wrong values — stderr says which                                     |
| `3`  | Simulator boot / install / launch failed                                            | Inspect stderr; re-run step 7 if app bundle is stale                                                      |
| `4`  | `Dynatrace Core` log not found after launch                                         | Verify `import Dynatrace` is in entry point; suggest manual launch and checking the Dynatrace environment |
| `5`  | `log show` itself failed                                                            | Simulator state issue; retry after restarting the simulator                                               |

The script prints `=== Phase N: ... ===` headers so partial failures are debuggable from stdout.

#### Post-verification guidance

Leave the simulator running with the app open so the user can interact with it and generate events that will appear in their Dynatrace environment. Do NOT shut down the simulator.

After successful verification, inform the user:

- The simulator is running with the app — to verify data reaches their Dynatrace environment, they should:
  1. Interact with the app: tap buttons, navigate between screens to generate user actions and events
  1. Send the app to the background (press the Home button in the simulator) and bring it back to the foreground — this triggers an immediate session flush to the Dynatrace cluster
  1. Within a few minutes, the generated events will appear in their Dynatrace environment
- To view data: Experience Vitals > Overview > Mobile > select frontend
- Data can also be queried directly in Grail using DQL
- For advanced configuration options, see: https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/mobile-frontends/ios/id-03-configuration

## Important notes

- This skill covers **SPM integration only**. CocoaPods and manual framework integration are not supported.
- Do NOT add extra DTX configuration keys unless the user explicitly asks for them — the defaults are optimized for a good first experience.
- The public documentation for this setup is at: https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/mobile-frontends/ios/id-01-initial-setup
