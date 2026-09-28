#!/usr/bin/env bash
# One-command deploy of the Claims Triage POC into the AWS account/region of your current credentials.
#
#   ./deploy.sh                      # us-east-1, serverless endpoints
#   AWS_REGION=us-east-2 ./deploy.sh
#   TRAINING=local ./deploy.sh       # train locally if the account's SageMaker training quota is 0
#   ENDPOINT_MODE=realtime ./deploy.sh   # always-on ml.t2.medium endpoints (no cold starts, ~$0.17/hr for all 3)
#
# Needs: AWS CLI v2 with credentials, Node 18+ (for the CDK CLI), Python 3.10+.
set -euo pipefail
cd "$(dirname "$0")"

export AWS_REGION="${AWS_REGION:-us-east-1}"
export CDK_DEFAULT_REGION="$AWS_REGION"
export CDK_DEFAULT_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
MODE="${ENDPOINT_MODE:-serverless}"
# Preflight: credentials from `sts get-session-token` without MFA are rejected by IAM, which makes
# CDK bootstrap (and the SageMaker role) fail half-way. Catch that before creating anything.
IAM_CHECK="$(aws iam list-account-aliases --output text 2>&1 || true)"
if [[ "$IAM_CHECK" == *InvalidClientTokenId* ]]; then
  echo "ERROR: these credentials can't call IAM (typically GetSessionToken credentials without MFA)." >&2
  echo "       Use assume-role / SSO credentials, get-session-token with --serial-number/--token-code, or access keys." >&2
  exit 1
fi
echo "==> Deploying to account $CDK_DEFAULT_ACCOUNT / $AWS_REGION (endpoint mode: $MODE)"

echo "==> Python dependencies"
python3 -m venv .venv >/dev/null 2>&1 || true
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r infra/requirements.txt -r requirements-dev.txt
command -v cdk >/dev/null || npm install -g aws-cdk

echo "==> Sample data (skipped if already present)"
[ -f data/claims_history.csv ] || python data/generate_dataset.py
[ -f sample_docs/samples.json ] || python data/generate_documents.py

cd infra
echo "==> CDK bootstrap (safe to re-run)"
cdk bootstrap "aws://$CDK_DEFAULT_ACCOUNT/$AWS_REGION" >/dev/null

echo "==> Stack 1/2: foundation (S3 + SageMaker role)"
cdk deploy ClaimsTriageFoundation --require-approval never
cd ..

if [ "${TRAINING:-sagemaker}" = "local" ]; then
  # For accounts whose SageMaker training-instance quota is still 0 (typical for new accounts):
  # train here under the serving container's exact versions, upload to S3, host on SageMaker as usual.
  echo "==> Training 3 models locally (scikit-learn 1.2.1, matching the SageMaker serving container)"
  command -v uv >/dev/null || pip install -q uv
  [ -x .venv-sk12/bin/python ] || uv venv -q -p 3.9 .venv-sk12
  VIRTUAL_ENV=.venv-sk12 uv pip install -q scikit-learn==1.2.1 numpy==1.24.1 pandas==1.1.3 scipy==1.8.0 joblib boto3
  .venv-sk12/bin/python scripts/upload_local_models.py --region "$AWS_REGION"
else
  echo "==> Training 3 models as SageMaker training jobs (~5-8 min)"
  python scripts/train_in_sagemaker.py --region "$AWS_REGION" || {
    echo "Training failed. If the error is ResourceLimitExceeded (training quota 0), request an increase for" >&2
    echo "'ml.m5.large for training job usage' in Service Quotas, or re-run with TRAINING=local ./deploy.sh" >&2
    exit 1; }
fi

cd infra
echo "==> Stack 2/2: endpoints, API, Lambda, DynamoDB, console (~8-12 min, endpoints are the slow part)"
cdk deploy ClaimsTriageApp --require-approval never -c endpoint_mode="$MODE" \
    --outputs-file ../build/outputs.json
cd ..

KEY_CMD=$(python3 -c "import json;print(json.load(open('build/outputs.json'))['ClaimsTriageApp']['GetApiKeyCommand'])")
API_KEY=$($KEY_CMD)
CONSOLE=$(python3 -c "import json;print(json.load(open('build/outputs.json'))['ClaimsTriageApp']['ConsoleUrl'])")
API_URL=$(python3 -c "import json;print(json.load(open('build/outputs.json'))['ClaimsTriageApp']['ApiUrl'])")

cat <<EOF

=====================================================================
 Claims Triage POC deployed
   Console : $CONSOLE
   API     : $API_URL
   API key : $API_KEY
 Next:  python scripts/smoke_test.py      (runs every sample end to end)
 Remove: ./destroy.sh
=====================================================================
EOF
