---
name: bench-ec2
metadata:
  version: "1.0.0"
description: Manage the i8g.8xlarge AWS EC2 instance used to benchmark diskgraph (launch, status, stop, start, terminate, ssh-config, ssm, bootstrap). Use when the user wants to spin up, tear down, or SSH into the diskgraph benchmark VM.
allowed-tools: Bash Read Write
---

# bench-ec2

Lifecycle of the diskgraph benchmark EC2 instance (i8g.8xlarge, ARM64 Ubuntu 24.04, us-west-2, SSM-access only).

Single source of truth: the EC2 `Name=lei-diskgraph-bench` tag. No state files.

Scripts are bundled with this skill under `scripts/`. Invoke them from the skill directory (e.g. `.agents/skills/bench-ec2/scripts/bench-ec2.sh`).

## Subcommands

Invoke via `scripts/bench-ec2.sh <sub>`:

- `launch` — create the instance (fails if one with the tag already exists). Waits for `status-ok`.
- `status` — show id / state / AZ / private IP / launch time.
- `stop` — halt compute billing (EBS keeps billing ~$8/mo for 100GB gp3).
- `start` — start a stopped instance; waits for `status-ok`.
- `terminate` (alias: `cleanup`) — **destructive**; confirms, then deletes instance and root EBS.
- `ssh-config` — print the `~/.ssh/config` stanza for `ssh aws-bench` (SSM ProxyCommand, no public IP).
- `ssm` — open an interactive SSM shell session.
- `bootstrap` — run `scripts/bench-ec2-bootstrap.sh` on the instance via SSM (apt packages, `gh` CLI, NVMe mount at `/mnt/data`, rustup, pyarrow venv, git identity, env defaults, daily auto-shutdown timer). Idempotent.

## Manual steps left to the user after bootstrap

1. `gh auth login -s "repo,read:org,admin:public_key" -w` on the instance (interactive browser flow) — also uploads an SSH key so git over SSH works.
2. `cd /mnt/data && git clone git@github.com:kumo-ai/kumo-diskgraph.git` (keep source off the 100GB root EBS).
3. `cargo build --release ...` per the benchmark issue comment.

## What bootstrap sets

- `/etc/profile.d/diskgraph-bench.sh` exports `DISKGRAPH_DATA_ROOT=/mnt/data` and `DISKGRAPH_STATS_DEST=s3://kumo-unit-test/diskgraph-profiles` (takes effect on new login shells).
- `~/.bashrc` auto-sources `~/.cargo/env` and activates `~/.venv-bench` (has `pyarrow`).
- S3 creds come from the IAM instance profile `kumo_user_admin_access` — no `aws configure` needed.
- Daily auto-shutdown safety net via `bench-auto-shutdown.timer` — defaults to 03:00 America/Los_Angeles, runs `shutdown -h now` (EC2 stop). Override at bootstrap time with `BENCH_SHUTDOWN_HOUR` (0-23, or `off` to skip) and `BENCH_SHUTDOWN_TZ` (IANA). Reconfigure later by re-running `bootstrap` with new env vars, or edit `/etc/systemd/system/bench-auto-shutdown.timer`. **Wall-clock, not idle** — if you're mid-run at the trigger hour, it stops the box.

## Cost reminder

- Running: ~$2.50/hr on-demand.
- Stopped: ~$8/mo (root EBS only).
- Terminated: $0.

## Config (edit the script to change)

- AMI: resolved at launch from SSM param `/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id`
- Subnet / SG / IAM profile: mirrors the existing `lei-eng-devtest` m5.xlarge so SSM access works identically.
- Instance store: 2× 3.75TB NVMe. Bootstrap mounts only the first at `/mnt/data` (XFS). Edit the script to RAID0 across both if you need the full 7.5TB.
