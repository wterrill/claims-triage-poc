#!/usr/bin/env bash
# Remove everything the POC created (endpoints, API, Lambda, tables, buckets and their contents).
set -euo pipefail
cd "$(dirname "$0")"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export CDK_DEFAULT_REGION="$AWS_REGION"
export CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
# shellcheck disable=SC1091
[ -d .venv ] && source .venv/bin/activate
cd infra
cdk destroy ClaimsTriageApp ClaimsTriageFoundation --force
echo "Done. SageMaker training-job history and CloudWatch logs remain (no ongoing cost)."
