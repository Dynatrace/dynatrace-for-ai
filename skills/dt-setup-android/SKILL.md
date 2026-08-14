---
name: dt-setup-android
description: 'Instruments an existing Android project (Kotlin or Java) with the Dynatrace Mobile Agent for basic monitoring. Covers zero-to-first-event setup only: Gradle plugin, agent config, and user privacy opt-in. Do not use for advanced Dynatrace configuration beyond initial instrumentation.'
license: Apache-2.0
---

# Android Dynatrace Instrumentation

> **Scope:** Basic setup only — from zero to first event. For anything beyond initial instrumentation (custom actions, crash grouping, data privacy policies, etc.) refer to the Dynatrace documentation directly.

## Phase 1: Preflight

Before doing anything else, check that the current directory is an Android project root by looking for `settings.gradle.kts` or `settings.gradle`. If neither exists, **stop and tell the user this is not an Android project root**, and ask them to navigate to the correct directory.

Then verify the following minimum requirements. If any are not met, **stop and inform the user** of what needs to be upgraded before proceeding:

| Requirement                 | Minimum |
| --------------------------- | ------- |
| Gradle                      | 7.0.2   |
| Android Gradle Plugin (AGP) | 7.0     |
| JVM                         | Java 11 |

Run `./gradlew --version` (or `gradlew.bat --version` on Windows). The output covers both Gradle and the actual JVM Gradle is using (the `Daemon JVM` line), which may differ from the system Java when the project is opened in Android Studio or IntelliJ. Do not use `java -version` — it may report a different JDK than what the build actually runs on. The AGP version is declared in the root build file.

## Phase 2: Detect existing setup

If a `dynatrace { }` block or a `configure<com.dynatrace.tools.android.dsl.DynatraceExtension> { }` block (also written as `configure<DynatraceExtension> { }` when the class is imported) is found anywhere in the build files, read it and extract if present:

- `applicationId` (the value passed to `applicationId(...)` or `applicationId '...'`)
- `beaconUrl` (the value passed to `beaconUrl(...)` or `beaconUrl '...'`)

Save these as pre-filled values to carry into Phase 3. If either value is absent or uses a placeholder (e.g. `YOUR_APPLICATION_ID`), treat it as not found. Proceed to Phase 3.

## Phase 3: Collect inputs

**First**, ask only for:

1. `applicationId` — Dynatrace application ID. Tell the user this can be found in their Dynatrace tenant, inside the mobile application they have already created. If a value was extracted in Phase 2, show it as the current value and ask the user to confirm or replace it.
1. `beaconUrl` — Dynatrace beacon URL. Tell the user this can also be found in their Dynatrace tenant, inside the same mobile application configuration. Same: show the extracted value if available and ask to confirm or replace.

Once the user confirms or provides both, **then** ask — unless the user already stated their session replay preference in their initial request, in which case skip this question and use what they said:

1. Session replay — should session replay be enabled? (yes/no)

## Phase 4: Locate files

### Finding the app module

The application module is not always named `app`. Read `settings.gradle.kts` or `settings.gradle` to find all included modules, then check each module's build file for the `com.android.application` plugin. Use the directory of the first module that applies it as `APP_MODULE` for all paths below.

macOS / Linux:

```bash
grep -r -l --include="*.gradle" --include="*.gradle.kts" --exclude-dir=buildSrc "com.android.application" .
```

Windows (cmd):

```text
findstr /s /m "com.android.application" *.gradle *.gradle.kts
```

Windows (PowerShell):

```text
Get-ChildItem -Recurse -Include "*.gradle","*.gradle.kts" | Select-String "com.android.application" | Select-Object -ExpandProperty Path
```

Discard any result where the matching line contains `apply false` — those are version-catalog declarations in the root build file, not actual plugin applications. Also discard any result under `buildSrc/`.

If no module applying `com.android.application` is found after filtering, **stop and report the failure** — no files have been modified at this point.

### Files to read before editing

- **Root** `build.gradle.kts` / `build.gradle` (sibling of the settings file)
- **App** `APP_MODULE/build.gradle.kts` / `APP_MODULE/build.gradle`
- **Entry-point source file** — see below

### Finding the entry-point file

**Preferred: Application class.** Search the source tree for a class that extends `Application` using the appropriate command for the OS:

macOS / Linux:

```bash
grep -r -l --include="*.java" "extends Application" APP_MODULE/src
grep -r -l --include="*.kt" ": Application()" APP_MODULE/src
```

Windows (cmd):

```text
findstr /s /m "extends Application" APP_MODULE\src\*.java
findstr /s /m ": Application()" APP_MODULE\src\*.kt
```

Windows (PowerShell):

```text
Get-ChildItem -Recurse -Path APP_MODULE/src -Include "*.java" | Select-String "extends Application" | Select-Object -ExpandProperty Path
Get-ChildItem -Recurse -Path APP_MODULE/src -Include "*.kt" | Select-String ": Application()" | Select-Object -ExpandProperty Path
```

If found, use that file. Add the privacy opt-in call inside its `onCreate()`, after `super.onCreate()`.

**Fallback: Launcher activity.** If no Application class exists, find the launcher activity in `AndroidManifest.xml` — it is the `<activity>` that contains:

```text
<action android:name="android.intent.action.MAIN" />
<category android:name="android.intent.category.LAUNCHER" />
```

Read the `android:name` attribute of that activity, locate its source file, and add the privacy opt-in call inside `onCreate()`, after `setContentView(...)`.

Once the file is found, detect the language from its extension: `.kt` = Kotlin, `.java` = Java.

> Do not assume the file is named `MainActivity`.

## Phase 5: Instrument

For each step below, check whether the element is already present before writing. If it is present and correct, skip it. If it is present but incorrect or incomplete, update only the affected values. If it is absent, add it in full.

Before editing any file, record its original content. If any step fails for any reason (build error, missing file, unresolvable conflict, unexpected file structure, etc.):

1. **Stop immediately** — do not attempt further changes.
1. **Report the failure** — state clearly which step failed and why.
1. **Rollback all edits** — restore every file modified in this phase to its original content. If a file was created from scratch, delete it.
1. **Confirm rollback** — tell the user which files were restored and that the project is back to its original state.

Do not leave the project in a partially instrumented state.

### Root build file

First check whether the root build file is `build.gradle.kts` (Kotlin DSL) or `build.gradle` (Groovy DSL) and apply the matching syntax.

> `com.dynatrace.instrumentation` **must** be applied in the root build file, not the app module.

### Kotlin DSL (`build.gradle.kts`)

**Classpath dependency** — check whether `com.dynatrace.tools.android:gradle-plugin` already appears in a `buildscript { dependencies { } }` block. If yes and the version spec is `8.+`, skip. If yes with a different version, update the version to `8.+`. If absent, add the classpath into an existing `buildscript { dependencies { } }` block if one exists; otherwise add the full `buildscript` block **before** the `plugins {}` block:

```text
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath("com.dynatrace.tools.android:gradle-plugin:8.+")
    }
}
```

**Plugin apply** — check whether `apply(plugin = "com.dynatrace.instrumentation")` is already present. If yes, skip. If absent, add it after the `plugins {}` block.

**DynatraceExtension block** — check whether a `configure<com.dynatrace.tools.android.dsl.DynatraceExtension>` block already exists.

- If it exists, check each field and update only those that differ from the target values: `applicationId`, `beaconUrl`, `userOptIn(true)`, `agentBehavior.startupLoadBalancing(true)`, `agentBehavior.startupWithGrailEnabled(true)`, and `sessionReplay.enabled(true)` (if session replay was requested). Add any missing fields.
- If absent, add the full block after the plugin apply line. In both cases, substitute `applicationId` and `beaconUrl` with the values confirmed in Phase 3 — do not leave the placeholders below in place:

```text
configure<com.dynatrace.tools.android.dsl.DynatraceExtension> {
    configurations {
        create("sampleConfig") {
            autoStart {
                applicationId("YOUR_APPLICATION_ID")
                beaconUrl("https://your-tenant.live.dynatrace.com/mbeacon")
            }
            userOptIn(true)
            agentBehavior.startupLoadBalancing(true)
            agentBehavior.startupWithGrailEnabled(true)
            // only if session replay was requested:
            sessionReplay.enabled(true)
        }
    }
}
```

### Groovy DSL (`build.gradle`)

**Classpath dependency** — check whether `com.dynatrace.tools.android:gradle-plugin` already appears in a `buildscript { dependencies { } }` block. If yes and the version spec is `8.+`, skip. If yes with a different version, update the version to `8.+`. If absent, add the classpath inside the existing `buildscript { dependencies { } }` block, or create the full `buildscript` block before any `apply` lines if none exists:

```text
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'com.dynatrace.tools.android:gradle-plugin:8.+'
    }
}
```

**Plugin apply** — check whether `apply plugin: 'com.dynatrace.instrumentation'` is already present. If yes, skip. If absent, add it after the existing `apply` lines or at the end of the file.

**dynatrace block** — check whether a `dynatrace { }` block already exists.

- If it exists, check each field and update only those that differ from the target values: `applicationId`, `beaconUrl`, `userOptIn true`, `agentBehavior.startupLoadBalancing true`, `agentBehavior.startupWithGrailEnabled true`, and `sessionReplay.enabled true` (if session replay was requested). Add any missing fields.
- If absent, add the full block after the plugin apply line. In both cases, substitute `applicationId` and `beaconUrl` with the values confirmed in Phase 3 — do not leave the placeholders below in place:

```text
dynatrace {
    configurations {
        sampleConfig {
            autoStart {
                applicationId 'YOUR_APPLICATION_ID'
                beaconUrl 'https://your-tenant.live.dynatrace.com/mbeacon'
            }
            userOptIn true
            agentBehavior.startupLoadBalancing true
            agentBehavior.startupWithGrailEnabled true
            // only if session replay was requested:
            sessionReplay.enabled true
        }
    }
}
```

### Entry-point file (Application class or launcher activity)

Add only the imports not already present. For the privacy opt-in call, check whether `Dynatrace.applyUserPrivacyOptions(...)` already exists inside `onCreate`. If yes, verify each option (`DataCollectionLevel.USER_BEHAVIOR`, `withCrashReportingOptedIn(true)`, `withScreenRecordOptedIn(true)` if session replay is enabled) and update any that differ. If absent, insert it at the position matching the entry-point type:

- **Application subclass** — after `super.onCreate()`
- **Launcher activity** — after `setContentView(...)`

### Kotlin

**Imports** — add only those not already present:

```text
import com.dynatrace.android.agent.Dynatrace
import com.dynatrace.android.agent.conf.DataCollectionLevel
import com.dynatrace.android.agent.conf.UserPrivacyOptions
```

**Privacy opt-in call** — insert after `super.onCreate()` (Application subclass) or after `setContentView(...)` (launcher activity). Include `.withScreenRecordOptedIn(true)` only if session replay was enabled in Phase 3:

```text
Dynatrace.applyUserPrivacyOptions(
    UserPrivacyOptions.builder()
        .withDataCollectionLevel(DataCollectionLevel.USER_BEHAVIOR)
        .withCrashReportingOptedIn(true)
        // .withScreenRecordOptedIn(true) — add only if session replay is enabled
        .build()
)
```

### Java

**Imports** — add only those not already present:

```text
import com.dynatrace.android.agent.Dynatrace;
import com.dynatrace.android.agent.conf.DataCollectionLevel;
import com.dynatrace.android.agent.conf.UserPrivacyOptions;
```

**Privacy opt-in call** — insert after `super.onCreate()` (Application subclass) or after `setContentView(...)` (launcher activity). Include `.withScreenRecordOptedIn(true)` only if session replay was enabled in Phase 3:

```text
Dynatrace.applyUserPrivacyOptions(UserPrivacyOptions.builder()
    .withDataCollectionLevel(DataCollectionLevel.USER_BEHAVIOR)
    .withCrashReportingOptedIn(true)
    // .withScreenRecordOptedIn(true) — add only if session replay is enabled
    .build()
);
```

## Phase 6: Build and verify

First, discover available assemble tasks to handle projects with custom build types or product flavors:

macOS / Linux:

```bash
./gradlew tasks --group=build | grep -i "^assemble"
```

Windows (cmd):

```text
gradlew.bat tasks --group=build | findstr /i "assemble"
```

Windows (PowerShell):

```text
.\gradlew.bat tasks --group=build | Select-String -Pattern "^assemble" -CaseSensitive:$false
```

If only one assemble task is listed, use it. If multiple tasks are listed, present them to the user and ask which one to run.

Then run it:

- macOS / Linux: `./gradlew CHOSEN_TASK`
- Windows (cmd): `gradlew.bat CHOSEN_TASK`
- Windows (PowerShell): `.\gradlew.bat CHOSEN_TASK`

A successful build confirms the Dynatrace plugin is wired up correctly.
