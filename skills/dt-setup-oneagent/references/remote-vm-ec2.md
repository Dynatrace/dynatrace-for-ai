# Remote VM / EC2 over SSH

Installing OneAgent on a host reached over the network — an EC2 instance, a bare-metal server, anything with SSH.

Part of the `dt-setup-oneagent` skill — see [../SKILL.md](../SKILL.md) for the hard rules, URL normalization and token guidance that apply to every target.

---

The VM / server commands in [../SKILL.md](../SKILL.md) install OneAgent on **the machine running them**. To instrument a different host — an EC2 instance, a bare-metal server, any reachable Linux box — run the same installer *on that host* over SSH.

Nothing here creates the instance. Provision it with your own tooling (Terraform, CloudFormation, `aws ec2 run-instances`), then attach OneAgent to the host that already exists.

**Login user by AMI:** Amazon Linux / AL2023 → `ec2-user`, Ubuntu → `ubuntu`, Debian → `admin`, RHEL → `ec2-user`. The user needs `sudo`; stock EC2 AMIs are passwordless.

**Keep the token off the command line.** Write it into a `0600` file on the target through stdin — never as an `ssh` argument, or it lands in the process list on both machines and in your shell history:

```bash
SSH_HOST="ec2-user@ec2-1-2-3-4.compute-1.amazonaws.com"
SSH_KEY="$HOME/.ssh/my-key.pem"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -i "$SSH_KEY")
REMOTE_DIR="/tmp/dt-install-$(date +%s)"
AUTH_SCHEME="Api-Token"   # platform token (dt0s16.…): Bearer
ARCH="x86"                # Graviton / arm64 instances: arm

# 1. verify connectivity first — BatchMode fails fast instead of prompting
ssh "${SSH_OPTS[@]}" "$SSH_HOST" 'echo connectivity-ok'

# 2. ensure wget is present (installer dependency)
ssh "${SSH_OPTS[@]}" "$SSH_HOST" '
  command -v wget >/dev/null 2>&1 || {
    command -v apt-get >/dev/null 2>&1 && sudo apt-get update -qq && sudo apt-get install -y -qq wget ||
    command -v dnf     >/dev/null 2>&1 && sudo dnf install -y -q wget ||
    sudo yum install -y -q wget
  }'

# 3. ship the credentials into a 0600 file via stdin
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "mkdir -p '$REMOTE_DIR' && chmod 700 '$REMOTE_DIR'"
printf 'export DT_ENV_URL=%q\nexport DT_API_TOKEN=%q\nexport AUTH_SCHEME=%q\nexport ARCH=%q\n' \
       "$DT_ENV_URL_NORMALIZED" "$DT_API_TOKEN" "$AUTH_SCHEME" "$ARCH" \
  | ssh "${SSH_OPTS[@]}" "$SSH_HOST" "umask 077 && cat > '$REMOTE_DIR/dt.env'"

# 4. download and run the installer on the remote host
ssh "${SSH_OPTS[@]}" -t "$SSH_HOST" "
  set -e
  . '$REMOTE_DIR/dt.env'
  cd '$REMOTE_DIR'
  wget -q -O oneagent.sh \
    --header=\"Authorization: \$AUTH_SCHEME \$DT_API_TOKEN\" \
    \"\$DT_ENV_URL/api/v1/deployment/installer/agent/unix/default/latest?arch=\$ARCH&flavor=default\"
  sudo /bin/sh oneagent.sh --set-monitoring-mode=fullstack --set-app-log-content-access=true
"

# 5. ALWAYS clean up — dt.env holds the token
ssh "${SSH_OPTS[@]}" "$SSH_HOST" "rm -rf '$REMOTE_DIR'" || {
  echo "WARNING: $REMOTE_DIR/dt.env still holds a live token on $SSH_HOST" >&2
  echo "  remove it:  ssh $SSH_HOST 'rm -rf $REMOTE_DIR'" >&2
}
```

**If the cleanup fails, do not treat the run as clean.** A network blip after a successful install is enough, and the credentials file then stays on the host indefinitely — `0600`, but readable by root and by anything later running as root. Retry the removal; if it still fails, treat the token as exposed and rotate it. Scripting this? Exit with a distinct status for "installed but the token file could not be removed", so a pipeline can tell it apart from success.

**On `StrictHostKeyChecking=accept-new`.** This accepts an unrecognised host key on first connect. It is what makes a fresh instance usable without manual steps, but it also means the very run that ships a live token to that host is the one with no way to tell the real machine from an interposed one. On a private subnet with a known-good route that is a reasonable trade. Over the public internet, or when the token matters more than convenience, pin the key first — for EC2, the instance prints its host keys to the console on first boot:

```bash
aws ec2 get-console-output --instance-id i-xxxxxxxx --region <region> \
  --output text | sed -n '/BEGIN SSH HOST KEY KEYS/,/END SSH HOST KEY KEYS/p'
```

Compare that against `ssh-keyscan <host>`, add the verified key to `known_hosts`, and switch to `StrictHostKeyChecking=yes`. Console output can lag a minute or two after boot.

**Private instances** with no public IP: add a jump host — `-J user@bastion.example.com` in `SSH_OPTS`. AWS SSM Session Manager is the alternative when SSH is closed entirely.

**Verify** (no token needed):

```bash
ssh "${SSH_OPTS[@]}" "$SSH_HOST" \
  'systemctl is-active oneagent || ls -d /opt/dynatrace/oneagent'
```

**Uninstall** (no token needed):

```bash
ssh "${SSH_OPTS[@]}" -t "$SSH_HOST" \
  'sudo /bin/sh /opt/dynatrace/oneagent/agent/uninstall.sh'
```

**Restart caveat applies remotely too:** OneAgent cannot inject into already-running processes, so restart the workloads on the target after installing.

---
