#!/usr/bin/env bash
# Runs ON the benchmark instance (via SSM send-command as root).
# Idempotent: re-running is safe.
set -euxo pipefail

TARGET_USER="ubuntu"
HOME_DIR="/home/$TARGET_USER"
DATA_MNT="/mnt/data"
# Extra public keys to authorize for TARGET_USER (one per line). The launch key
# (kumo_init) is already added by cloud-init; this is for operator keys that
# aren't tied to the EC2 KeyName.
EXTRA_AUTHORIZED_KEYS="${EXTRA_AUTHORIZED_KEYS:-}"

# --- apt packages ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  build-essential pkg-config libssl-dev git curl jq unzip clang \
  python3-pip python3-venv xfsprogs nvme-cli

# --- install AWS CLI v2 (not in Ubuntu apt; IAM role creds resolve automatically) ---
if ! command -v aws >/dev/null 2>&1; then
  cd /tmp
  curl -sSL https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip -o awscliv2.zip
  unzip -q -o awscliv2.zip
  ./aws/install --update
  rm -rf /tmp/aws /tmp/awscliv2.zip
fi

# --- install gh CLI (user will run `gh auth login` manually later) ---
if ! command -v gh >/dev/null 2>&1; then
  install -dm 755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
  chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update -y
  apt-get install -y gh
fi

# --- mount instance-store NVMe (single-disk XFS on the first ephemeral) ---
if ! mountpoint -q "$DATA_MNT"; then
  EPHEMERALS=( $(lsblk -d -n -o NAME,TYPE | awk '$2=="disk" && $1 ~ /^nvme[12]n1$/ {print "/dev/"$1}') )
  if [[ ${#EPHEMERALS[@]} -ge 1 ]]; then
    DEV="${EPHEMERALS[0]}"
    blkid "$DEV" >/dev/null 2>&1 || mkfs.xfs -f "$DEV"
    mkdir -p "$DATA_MNT"
    UUID=$(blkid -s UUID -o value "$DEV")
    grep -q "$UUID" /etc/fstab || echo "UUID=$UUID $DATA_MNT xfs defaults,nofail 0 2" >> /etc/fstab
    mount -a
  fi
fi
# Reconcile ownership every run — the original mount may have been performed
# before this step existed, leaving /mnt/data owned by root.
[[ -d "$DATA_MNT" ]] && chown "$TARGET_USER:$TARGET_USER" "$DATA_MNT"

# --- authorize extra SSH keys for $TARGET_USER ---
if [[ -n "$EXTRA_AUTHORIZED_KEYS" ]]; then
  install -d -m 700 -o "$TARGET_USER" -g "$TARGET_USER" "$HOME_DIR/.ssh"
  AK="$HOME_DIR/.ssh/authorized_keys"
  touch "$AK"
  while IFS= read -r key; do
    [[ -z "$key" ]] && continue
    grep -qxF "$key" "$AK" || echo "$key" >> "$AK"
  done <<< "$EXTRA_AUTHORIZED_KEYS"
  chown "$TARGET_USER:$TARGET_USER" "$AK"
  chmod 600 "$AK"
fi

# --- write the per-user bootstrap to a tempfile and run as $TARGET_USER ---
# (avoid `sudo -iu ubuntu bash -c '<multiline>'` which flattens newlines via -i)
USER_SCRIPT=$(mktemp /tmp/bench-user-bootstrap.XXXXXX.sh)
cat > "$USER_SCRIPT" <<'EOF'
#!/usr/bin/env bash
set -euxo pipefail

# Rust toolchain
if [ ! -x "$HOME/.cargo/bin/rustc" ]; then
  curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
fi
grep -q "cargo/env" "$HOME/.bashrc" || echo 'source "$HOME/.cargo/env"' >> "$HOME/.bashrc"

# Python venv + pyarrow (Ubuntu 24.04 blocks system pip per PEP 668)
if [ ! -d "$HOME/.venv-bench" ]; then
  python3 -m venv "$HOME/.venv-bench"
fi
"$HOME/.venv-bench/bin/pip" install --upgrade pip
"$HOME/.venv-bench/bin/pip" install pyarrow
grep -q "venv-bench/bin/activate" "$HOME/.bashrc" || echo 'source "$HOME/.venv-bench/bin/activate"' >> "$HOME/.bashrc"
EOF
chmod +x "$USER_SCRIPT"
chown "$TARGET_USER:$TARGET_USER" "$USER_SCRIPT"
sudo -u "$TARGET_USER" -H bash "$USER_SCRIPT"
rm -f "$USER_SCRIPT"

# --- environment defaults for the benchmark ---
PROFILE_D="/etc/profile.d/diskgraph-bench.sh"
cat > "$PROFILE_D" <<EOF
export DISKGRAPH_DATA_ROOT=$DATA_MNT
export DISKGRAPH_STATS_DEST=s3://kumo-unit-test/diskgraph-profiles
EOF
chmod 644 "$PROFILE_D"

# --- daily auto-shutdown safety net (systemd timer, wall-clock not idle) ---
# Override via BENCH_SHUTDOWN_HOUR (0-23) / BENCH_SHUTDOWN_TZ (IANA name).
# Set BENCH_SHUTDOWN_HOUR=off to skip installing the timer.
BENCH_SHUTDOWN_HOUR="${BENCH_SHUTDOWN_HOUR:-3}"
BENCH_SHUTDOWN_TZ="${BENCH_SHUTDOWN_TZ:-America/Los_Angeles}"
if [[ "$BENCH_SHUTDOWN_HOUR" != "off" ]]; then
  cat > /etc/systemd/system/bench-auto-shutdown.service <<EOF
[Unit]
Description=Shut down benchmark VM

[Service]
Type=oneshot
ExecStart=/sbin/shutdown -h now
EOF
  printf -v SHUTDOWN_HH '%02d' "$BENCH_SHUTDOWN_HOUR"
  cat > /etc/systemd/system/bench-auto-shutdown.timer <<EOF
[Unit]
Description=Daily benchmark VM auto-shutdown

[Timer]
OnCalendar=*-*-* ${SHUTDOWN_HH}:00:00 ${BENCH_SHUTDOWN_TZ}
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now bench-auto-shutdown.timer >/dev/null
fi

# --- git identity placeholder (user to override after gh auth) ---
sudo -u "$TARGET_USER" -H git config --global --get user.email >/dev/null 2>&1 || \
  sudo -u "$TARGET_USER" -H git config --global user.email "lei.sun@kumo.ai"
sudo -u "$TARGET_USER" -H git config --global --get user.name >/dev/null 2>&1 || \
  sudo -u "$TARGET_USER" -H git config --global user.name "Lei Sun"

echo "Bootstrap complete."
