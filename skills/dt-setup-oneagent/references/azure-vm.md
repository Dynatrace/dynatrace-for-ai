# Azure VM / VM Scale Set (OneAgent VM extension)

Installing OneAgent on an Azure VM or Virtual Machine Scale Set through the Dynatrace VM extension, driven remotely with `az` — you do not need to be on the machine.

Part of the `dt-setup-oneagent` skill — see [../SKILL.md](../SKILL.md) for the hard rules, URL normalization and token guidance that apply to every target.

List what your subscription actually offers before you start — this resolves both the publisher and the extension type for your region:

```bash
az vm extension image list --publisher dynatrace.ruxit --location <region> -o table
```

---

### A note on the identifiers

`dynatrace.ruxit` is the publisher — it is what docs.dynatrace.com documents and what appears in Microsoft's `azure-resource-manager-schemas` publisher enum. If you find a write-up using `dynatrace.ruxitagents`, it is wrong; that string exists nowhere in Azure's own metadata.

Extension **type** is less settled. Current Dynatrace documentation gives `oneAgentLinux` / `oneAgentWindows`, which is what this page uses. Microsoft's ARM schema for the older `2015-08-01` API version lists `ruxitAgentLinux` / `ruxitAgentWindows`, which appears to be the legacy naming. The `extension image list` command above resolves which your subscription actually offers.

OneAgent on Azure VMs is shipped as a Marketplace **VM extension**. The extension wraps the same Linux/Windows installer used elsewhere, but the install is driven remotely via `az ... extension set` — you do **not** need to be on the VM. AKS clusters are covered by the Kubernetes flow above, not this one.

### Extension identity

| Field | Value |
|---|---|
| Publisher | `dynatrace.ruxit` |
| Type (Linux) | `oneAgentLinux` |
| Type (Windows) | `oneAgentWindows` |
| Version | use `1.*` (or the explicit latest published version) |

**Marketplace prerequisite:** the first use in a subscription requires accepting the offer once via Azure Marketplace. If `az ... extension set` returns `MarketplacePurchaseEligibilityFailed`, that's the cause.

### Settings payload

Split between `--settings` (public, returned by `az ... extension show`) and `--protected-settings` (encrypted at rest; not returned on read):

```json
// --settings (public)
{
  "tenantId": "<env-id>",                                    // e.g. "abc12345"
  "server":   "https://<env-id>.live.dynatrace.com",         // normalized env URL
  "hostGroup": "<optional>",                                  // optional
  "monitoringMode": "fullStack|infraOnly|discoveryMode",     // optional, camelCase
  "enableLogAnalytics": "yes"                                 // optional, documented by Dynatrace
}

// --protected-settings (encrypted)
{
  "token": "dt0c01.…"                                         // PaaS token, InstallerDownload scope
}
```

**Always put the token in `protectedSettings`.** Dynatrace recommends this from extension version 2.200.0.0 onward, though some example snippets still show it inside the public `settings` block. The distinction matters: `settings` is returned verbatim by `az ... extension show`, so anyone with Reader on the resource can retrieve the token — a far wider audience than the people you deliberately gave it to. `protectedSettings` is encrypted at rest and never returned on read.

`monitoringMode` uses camelCase (`fullStack`, `infraOnly`, `discoveryMode`) — different from the kebab-case (`fullstack`, `infra-only`, `discovery`) accepted by the Linux installer one-liner.

### Detect kind + OS

The same name can be a VM or a VMSS, and the right extension type depends on the OS. Cheap pair of API calls:

```bash
# Is it a VM?
az vm show -g "$RG" -n "$NAME" --query storageProfile.osDisk.osType -o tsv
# Or a VMSS?
az vmss show -g "$RG" -n "$NAME" --query virtualMachineProfile.storageProfile.osDisk.osType -o tsv
```

Either returns `Linux` or `Windows`; lowercase it and pick the matching extension type.

### Install — Azure VM

Azure encrypts protected settings at rest and never returns them from `az … extension show`, but an inline `--protected-settings '{"token":"…"}'` still puts the token in your shell history and in `ps` output for the duration of the call. Pass it via a `0600` file instead — `az` accepts `@filename` for both settings arguments:

```bash
umask 077
PROT="$(mktemp)"
trap 'rm -f "$PROT"' EXIT
printf '{"token":"%s"}\n' "$DT_API_TOKEN" > "$PROT"

az vm extension set \
  --resource-group "$RG" --vm-name "$VM" \
  --publisher dynatrace.ruxit --name "$EXT" \
  --settings '{"tenantId":"<env-id>","server":"https://<env-id>.live.dynatrace.com"}' \
  --protected-settings "@$PROT"
```

Where `$EXT` is `oneAgentLinux` or `oneAgentWindows`. Provisioning typically takes 1–3 minutes; Azure runs the agent installer behind the scenes.

### Install — Azure VM Scale Set (VMSS)

Same shape, different verb. The extension attaches to the VMSS **model**, not to live instances:

```bash
umask 077
PROT="$(mktemp)"
trap 'rm -f "$PROT"' EXIT
printf '{"token":"%s"}\n' "$DT_API_TOKEN" > "$PROT"

az vmss extension set \
  --resource-group "$RG" --vmss-name "$VMSS" \
  --publisher dynatrace.ruxit --name "$EXT" \
  --settings '{"tenantId":"<env-id>","server":"https://<env-id>.live.dynatrace.com"}' \
  --protected-settings "@$PROT"

# New instances pick it up on next boot. Existing instances need an explicit
# update (or rely on the VMSS's upgrade policy):
az vmss update-instances -g "$RG" -n "$VMSS" --instance-ids '*'
```

### Uninstall

Removing the extension triggers the agent's uninstall handler on the live machine(s):

```bash
# VM
az vm extension delete   -g "$RG" --vm-name   "$VM"   --name "$EXT"

# VMSS (also remove from the model; existing instances keep the agent
# until reimage/reboot or an explicit update-instances).
az vmss extension delete -g "$RG" --vmss-name "$VMSS" --name "$EXT"
az vmss update-instances -g "$RG" -n "$VMSS" --instance-ids '*'
```

Find any Dynatrace-published extensions on a resource (regardless of whether it's `oneAgentLinux` or `oneAgentWindows`):

```bash
az vm   extension list -g "$RG" --vm-name   "$VM"   --query "[?publisher=='dynatrace.ruxit'].name" -o tsv
az vmss extension list -g "$RG" --vmss-name "$VMSS" --query "[?publisher=='dynatrace.ruxit'].name" -o tsv
```

### Verifying

The definitive signals that the extension is attached and healthy:

1. `publisher == 'dynatrace.ruxit'` shows up in `az ... extension list`, **and**
2. `provisioningState == 'Succeeded'` on that entry.

```bash
az vm extension list -g "$RG" --vm-name "$VM" \
  --query "[?publisher=='dynatrace.ruxit'].{name:name,state:provisioningState}" -o tsv
```

A `provisioningState` of `Failed` typically means: missing RBAC (`Microsoft.Compute/.../extensions/write`), an invalid token, the wrong server URL (forgot the `https://` or used the unnormalized `apps.dynatrace.com` host), or the marketplace offer hasn't been accepted yet in the subscription.

### Gotchas

- **Server URL normalization applies here too.** Use `<env-id>.live.dynatrace.com` (or the regional `dynatracelabs.com` host), **not** the `apps.dynatrace.com` UI URL. See *URL normalization* at the top of this doc.
- **AKS is not Azure VM.** Even though AKS node pools are technically VMSSes, do not install the VM extension on them — use the Kubernetes Operator + DynaKube path. The OneAgent CSI driver and operator handle pod-level injection in a way the VM extension can't.
- **Azure Functions / App Service / Container Apps** use different mechanisms (site extension or app settings env vars) and are **not** covered by `dynatrace.ruxit`. They are explicitly out of scope for this skill.
- **VMSS model vs instances.** The extension is part of the model. New scale-out picks it up automatically; existing instances need `az vmss update-instances --instance-ids '*'` (or the VMSS's automatic upgrade policy). Same caveat on uninstall.
- **Protected-settings retrieval.** `az ... extension show` returns `--settings` but **not** `--protected-settings`. The token is encrypted at rest; you cannot recover it from Azure later. Plan for that — keep the token in your own secret store, not "I'll read it back from Azure."
