#!/usr/bin/env bash
# Lifecycle manager for the diskgraph benchmark EC2 instance.
# Single source of truth for instance identity is the Name tag.
set -euo pipefail

AWS_PROFILE_NAME="${AWS_PROFILE_NAME:-default}"
REGION="us-west-2"
NAME_TAG="lei-diskgraph-bench"
INSTANCE_TYPE="i8g.8xlarge"
AMI_PARAM="/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
KEY_NAME="kumo_init"
SUBNET_ID="subnet-06375692880ed05db"
SG_ID="sg-0605ffb9c352acfc8"
IAM_PROFILE="kumo_user_admin_access"
ROOT_VOL_GB=100

aws_() { aws --profile "$AWS_PROFILE_NAME" --region "$REGION" "$@"; }

find_instance_id() {
  aws_ ec2 describe-instances \
    --filters "Name=tag:Name,Values=$NAME_TAG" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text 2>/dev/null
}

cmd_launch() {
  local existing; existing=$(find_instance_id)
  if [[ -n "$existing" && "$existing" != "None" ]]; then
    echo "Instance already exists: $existing. Use 'terminate' first, or 'start' if stopped."
    cmd_status; exit 1
  fi
  local ami; ami=$(aws_ ssm get-parameter --name "$AMI_PARAM" --query 'Parameter.Value' --output text)
  echo "Launching $INSTANCE_TYPE with AMI $ami ..."
  local iid
  iid=$(aws_ ec2 run-instances \
    --image-id "$ami" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --subnet-id "$SUBNET_ID" \
    --security-group-ids "$SG_ID" \
    --iam-instance-profile "Name=$IAM_PROFILE" \
    --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$ROOT_VOL_GB,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME_TAG},{Key=Type,Value=Benchmark},{Key=Owner,Value=lei.sun@kumo.ai}]" \
    --metadata-options "HttpTokens=required,HttpEndpoint=enabled" \
    --query 'Instances[0].InstanceId' --output text)
  echo "Launched: $iid"
  echo "Waiting for running state ..."
  aws_ ec2 wait instance-running --instance-ids "$iid"
  echo "Waiting for status-ok (SSM agent ready) ..."
  aws_ ec2 wait instance-status-ok --instance-ids "$iid"
  echo "Ready. Add to ~/.ssh/config with: $0 ssh-config"
  cmd_status
}

cmd_status() {
  local iid; iid=$(find_instance_id)
  if [[ -z "$iid" || "$iid" == "None" ]]; then
    echo "No instance with Name=$NAME_TAG found."; return 0
  fi
  aws_ ec2 describe-instances --instance-ids "$iid" \
    --query 'Reservations[0].Instances[0].{Id:InstanceId,State:State.Name,Type:InstanceType,AZ:Placement.AvailabilityZone,PrivateIP:PrivateIpAddress,LaunchTime:LaunchTime}' \
    --output table
}

cmd_stop() {
  local iid; iid=$(find_instance_id); [[ -z "$iid" || "$iid" == "None" ]] && { echo "No instance found."; exit 1; }
  aws_ ec2 stop-instances --instance-ids "$iid" --query 'StoppingInstances[0].CurrentState.Name' --output text
  echo "Note: EBS root volume continues to bill while stopped (~\$8/mo for ${ROOT_VOL_GB}GB gp3)."
}

cmd_start() {
  local iid; iid=$(find_instance_id); [[ -z "$iid" || "$iid" == "None" ]] && { echo "No instance found."; exit 1; }
  aws_ ec2 start-instances --instance-ids "$iid" --query 'StartingInstances[0].CurrentState.Name' --output text
  aws_ ec2 wait instance-status-ok --instance-ids "$iid"
  cmd_status
}

cmd_terminate() {
  local iid; iid=$(find_instance_id); [[ -z "$iid" || "$iid" == "None" ]] && { echo "No instance found."; exit 0; }
  read -r -p "Terminate $iid and delete its root EBS? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Aborted."; exit 1; }
  aws_ ec2 terminate-instances --instance-ids "$iid" --query 'TerminatingInstances[0].CurrentState.Name' --output text
}

cmd_ssh_config() {
  local iid; iid=$(find_instance_id); [[ -z "$iid" || "$iid" == "None" ]] && { echo "No instance found."; exit 1; }
  cat <<EOF
# Add to ~/.ssh/config:
Host aws-bench
  HostName $iid
  User ubuntu
  IdentityFile ~/.ssh/id_ed25519
  ProxyCommand sh -c "PATH=/usr/local/sessionmanagerplugin/bin:/opt/homebrew/bin:\$PATH /opt/homebrew/bin/aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters 'portNumber=%p' --profile $AWS_PROFILE_NAME"
EOF
}

cmd_ssm() {
  local iid; iid=$(find_instance_id); [[ -z "$iid" || "$iid" == "None" ]] && { echo "No instance found."; exit 1; }
  aws_ ssm start-session --target "$iid"
}

cmd_bootstrap() {
  local iid; iid=$(find_instance_id); [[ -z "$iid" || "$iid" == "None" ]] && { echo "No instance found."; exit 1; }
  local script_dir; script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  local boot="$script_dir/bench-ec2-bootstrap.sh"
  [[ -f "$boot" ]] || { echo "Missing $boot"; exit 1; }
  echo "Sending bootstrap via SSM to $iid ..."
  # Inject the operator's local pubkey so `ssh aws-bench` works without relying
  # on the EC2 key pair's private half being installed locally.
  local extra_keys=""
  [[ -f "$HOME/.ssh/id_ed25519.pub" ]] && extra_keys="$(cat "$HOME/.ssh/id_ed25519.pub")"
  # SSM AWS-RunShellScript runs commands under /bin/sh (dash on Ubuntu),
  # which doesn't understand `set -o pipefail`. Base64-encode the bash
  # script and decode + execute under bash on the remote.
  local script_body; script_body="export EXTRA_AUTHORIZED_KEYS=$(printf %q "$extra_keys")"$'\n'"$(cat "$boot")"
  local b64; b64=$(printf '%s' "$script_body" | base64 | tr -d '\n')
  local wrapped_script="echo $b64 | base64 -d | bash"
  local payload; payload=$(mktemp)
  jq -n --arg script "$wrapped_script" \
    '{InstanceIds:[$iid], DocumentName:"AWS-RunShellScript", Comment:"diskgraph bench bootstrap", TimeoutSeconds:3600, Parameters:{commands:[$script], executionTimeout:["3600"]}}' \
    --arg iid "$iid" > "$payload"
  local cmd_id
  cmd_id=$(aws_ ssm send-command --cli-input-json "file://$payload" --query 'Command.CommandId' --output text)
  rm -f "$payload"
  echo "SSM command: $cmd_id"
  echo "Tail with: aws ssm list-command-invocations --command-id $cmd_id --details --profile $AWS_PROFILE_NAME --region $REGION"
}

usage() {
  cat <<EOF
Usage: $0 <subcommand>

  launch       Create the i8g.8xlarge benchmark instance (ARM64 Ubuntu 24.04)
  status       Show current instance info
  stop         Stop (halt billing for compute; EBS still billed)
  start        Start a stopped instance
  terminate    Terminate and delete root EBS (destructive)
  ssh-config   Print ~/.ssh/config block for 'ssh aws-bench'
  ssm          Open an SSM shell session on the instance
  bootstrap    Run bench-ec2-bootstrap.sh on the instance via SSM

Tag: Name=$NAME_TAG, Region: $REGION, Profile: $AWS_PROFILE_NAME
EOF
}

sub="${1:-}"; shift || true
case "$sub" in
  launch) cmd_launch "$@" ;;
  status) cmd_status "$@" ;;
  stop) cmd_stop "$@" ;;
  start) cmd_start "$@" ;;
  terminate|cleanup) cmd_terminate "$@" ;;
  ssh-config) cmd_ssh_config "$@" ;;
  ssm) cmd_ssm "$@" ;;
  bootstrap) cmd_bootstrap "$@" ;;
  ""|-h|--help|help) usage ;;
  *) echo "Unknown subcommand: $sub"; usage; exit 1 ;;
esac
