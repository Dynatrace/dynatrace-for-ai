# dynatrace.config.yaml — Manual Configuration

Use this reference when the user cannot download `dynatrace.config.yaml` from the Dynatrace console and needs to create it manually.

## Required Information

Collect all of the following before writing the file:

1. `applicationId` — format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
2. `beaconUrl` — format: `https://<environment-id>.live.dynatrace.com/mbeacon` (or a cluster-specific URL)
3. Dynatrace generation: **2nd gen** or **3rd gen (Grail)**
4. User Opt-In mode: check Experience Vitals → Mobile → [Your App] → Settings → Data Privacy

## Base Config (always include)

```yaml
android:
  config:
    "dynatrace {
      configurations {
        defaultConfig {
          autoStart{
            applicationId '<APPLICATION_ID>'
            beaconUrl '<BEACON_URL>'
          }
          agentBehavior.startupLoadBalancing true
        }
      }
    }"

ios:
  config:
    "<key>DTXApplicationID</key>
    <string><APPLICATION_ID></string>
    <key>DTXBeaconURL</key>
    <string><BEACON_URL></string>
    <key>DTXStartupLoadBalancing</key>
    <true/>
    "
```

## Conditional Additions

### 3rd gen (Grail) only

Android — inside `defaultConfig`, after `agentBehavior.startupLoadBalancing true`:
```
agentBehavior.startupWithGrailEnabled true
```

iOS — after `DTXStartupLoadBalancing`:
```
<key>DTXStartupWithGrailEnabled</key>
<true/>
```

### User Opt-In — always add to both platforms

Android — inside `defaultConfig`, after the load balancing line (and Grail line if present):
```
userOptIn true
```
or
```
userOptIn false
```

iOS — after `DTXStartupLoadBalancing` (and `DTXStartupWithGrailEnabled` if present):
```
<key>DTXUserOptIn</key><true/>
```
or
```
<key>DTXUserOptIn</key><false/>
```

## After Writing the File

- If `userOptIn` is `true`: the privacy options call (Step 7a) is required — flag it.
- If `userOptIn` is `false`: Step 7a can be skipped.
