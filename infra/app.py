#!/usr/bin/env python3
"""CDK entry point.

  cdk deploy ClaimsTriageFoundation            # bucket + SageMaker role
  python ../scripts/train_in_sagemaker.py      # trains 3 models -> build/model_artifacts.json
  cdk deploy ClaimsTriageApp                   # endpoints, API, Lambda, DynamoDB, console

Context flags (cdk.json or -c):
  endpoint_mode=serverless|realtime   realtime_instance_type=ml.t2.medium   keep_warm=true|false
"""
import json
import os
import sys

import aws_cdk as cdk

sys.path.insert(0, os.path.dirname(__file__))
from stacks.app_stack import AppStack  # noqa: E402
from stacks.foundation import FoundationStack  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ARTIFACTS = os.path.join(ROOT, "build", "model_artifacts.json")

app = cdk.App()
env = cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
                      region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"))
cdk.Tags.of(app).add("project", "claims-triage-poc")

foundation = FoundationStack(app, "ClaimsTriageFoundation", env=env)

if os.path.exists(ARTIFACTS):
    AppStack(app, "ClaimsTriageApp", foundation=foundation, artifacts=json.load(open(ARTIFACTS)), env=env)
else:
    print("NOTE: build/model_artifacts.json not found - only the Foundation stack is defined. "
          "Run scripts/train_in_sagemaker.py after deploying it.", file=sys.stderr)

app.synth()
