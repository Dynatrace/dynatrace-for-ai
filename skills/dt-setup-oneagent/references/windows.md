# Windows host (from WSL or native)

Installer endpoint, elevated install, and the MSI product-code lookup needed to uninstall.

Part of the `dt-setup-oneagent` skill — see [../SKILL.md](../SKILL.md) for the hard rules, URL normalization and token guidance that apply to every target.

---

**Endpoint:**

```
GET ${DT_ENV_URL_NORMALIZED}/api/v1/deployment/installer/agent/windows/default/latest?flavor=default
Header: Authorization: Api-Token ${DT_API_TOKEN}   # dt0c01.… access token
        Authorization: Bearer ${DT_API_TOKEN}      # dt0s16.… platform token
```

The downloaded `.exe` is an MSI wrapper. **Sanity check** before invoking: the first two bytes must be `MZ` (PE magic). If not, the API returned an error body, not the installer.

**Install** (UAC required — silent MSI mode):

```text
Start-Process -FilePath 'C:\path\to\Dynatrace-OneAgent-Windows.exe' `
  -ArgumentList '--set-monitoring-mode=fullstack','--set-app-log-content-access=true','/quiet' `
  -Verb RunAs -Wait
```

**Uninstall (no standalone uninstaller — must go through MSI):**

```text
$pc = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
                        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' |
       Where-Object DisplayName -EQ 'Dynatrace OneAgent' | Select -First 1).PSChildName
Start-Process msiexec.exe -ArgumentList '/x',$pc,'/quiet','/norestart' -Verb RunAs -Wait
```

---
