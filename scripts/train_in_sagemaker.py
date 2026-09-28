"""Train all three models as SageMaker training jobs (in parallel) using the AWS-managed
scikit-learn container, then record the resulting model artifacts for the CDK app stack.

Prereqs:  `cdk deploy ClaimsTriageFoundation` has run (creates the bucket + SageMaker role).
Usage:    python scripts/train_in_sagemaker.py [--region us-east-1] [--instance ml.m5.large]
Output:   build/model_artifacts.json   -> read by `cdk deploy ClaimsTriageApp`

Uses plain boto3 (no SageMaker Python SDK) so the moving parts are visible to the customer.
"""
import argparse
import io
import json
import os
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor

import boto3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOUNDATION_STACK = "ClaimsTriageFoundation"

# AWS-managed SageMaker scikit-learn container registry accounts
SKLEARN_ACCOUNTS = {
    "us-east-1": "683313688378", "us-east-2": "257758044811", "us-west-1": "746614075791",
    "us-west-2": "246618743249", "ca-central-1": "341280168497", "eu-west-1": "141502667606",
    "eu-west-2": "764974769150", "eu-central-1": "492215442770",
}
SKLEARN_VERSION = os.environ.get("SKLEARN_IMAGE_TAG", "1.2-1-cpu-py3")

MODELS = {
    # name: (entry point, hyperparameters)
    "fraud": ("fraud_model.py", {"n-estimators": 300, "max-depth": 3, "learning-rate": 0.05}),
    "severity": ("severity_model.py", {"n-estimators": 300, "max-depth": 3, "learning-rate": 0.05}),
    "notes": ("notes_model.py", {"C": 4.0}),
}


def sklearn_image(region):
    acct = SKLEARN_ACCOUNTS.get(region)
    if not acct:
        raise SystemExit(f"Add the SageMaker scikit-learn account for {region} to SKLEARN_ACCOUNTS")
    return f"{acct}.dkr.ecr.{region}.amazonaws.com/sagemaker-scikit-learn:{SKLEARN_VERSION}"


def stack_outputs(cfn, name):
    outs = cfn.describe_stacks(StackName=name)["Stacks"][0].get("Outputs", [])
    return {o["OutputKey"]: o["OutputValue"] for o in outs}


def upload_sources(s3, bucket, run_id):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        src = os.path.join(ROOT, "ml", "src")
        for f in os.listdir(src):
            if f.endswith(".py"):
                tar.add(os.path.join(src, f), arcname=f)
    buf.seek(0)
    key = f"training/{run_id}/sourcedir.tar.gz"
    s3.upload_fileobj(buf, bucket, key)
    s3.upload_file(os.path.join(ROOT, "data", "claims_history.csv"), bucket,
                   f"training/{run_id}/data/claims_history.csv")
    return f"s3://{bucket}/{key}", f"s3://{bucket}/training/{run_id}/data/"


def run_job(sm, name, entry, hps, image, role, src_uri, data_uri, out_uri, region, instance):
    job = f"claims-{name}-{int(time.time())}"
    hyper = {k: json.dumps(v) for k, v in hps.items()}
    hyper.update({
        "sagemaker_program": json.dumps(entry),
        "sagemaker_submit_directory": json.dumps(src_uri),
        "sagemaker_region": json.dumps(region),
        "sagemaker_container_log_level": "20",
    })
    sm.create_training_job(
        TrainingJobName=job,
        AlgorithmSpecification={
            "TrainingImage": image, "TrainingInputMode": "File",
            "MetricDefinitions": [{"Name": "auc", "Regex": r"metric_auc=([0-9\.]+);"},
                                  {"Name": "r2_log", "Regex": r"metric_r2_log=([0-9\.]+);"},
                                  {"Name": "category_accuracy", "Regex": r"metric_category_accuracy=([0-9\.]+);"}],
        },
        RoleArn=role,
        HyperParameters=hyper,
        InputDataConfig=[{"ChannelName": "train", "DataSource": {"S3DataSource": {
            "S3DataType": "S3Prefix", "S3Uri": data_uri, "S3DataDistributionType": "FullyReplicated"}}}],
        OutputDataConfig={"S3OutputPath": out_uri},
        ResourceConfig={"InstanceType": instance, "InstanceCount": 1, "VolumeSizeInGB": 10},
        StoppingCondition={"MaxRuntimeInSeconds": 1800},
        Tags=[{"Key": "project", "Value": "claims-triage-poc"}],
    )
    print(f"  started {job}")
    while True:
        d = sm.describe_training_job(TrainingJobName=job)
        st = d["TrainingJobStatus"]
        if st in ("Completed", "Failed", "Stopped"):
            break
        time.sleep(20)
    if st != "Completed":
        raise RuntimeError(f"{job} {st}: {d.get('FailureReason')}")
    metrics = {m["MetricName"]: m["Value"] for m in d.get("FinalMetricDataList", [])}
    print(f"  {job} completed {metrics}")
    return name, {"job": job, "model_data": d["ModelArtifacts"]["S3ModelArtifacts"],
                  "entry_point": entry, "image": image, "metrics": metrics}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default=os.environ.get("AWS_REGION") or boto3.Session().region_name or "us-east-1")
    ap.add_argument("--instance", default="ml.m5.large")
    a = ap.parse_args()

    sess = boto3.Session(region_name=a.region)
    outs = stack_outputs(sess.client("cloudformation"), FOUNDATION_STACK)
    bucket, role = outs["ArtifactBucketName"], outs["SageMakerRoleArn"]
    run_id = time.strftime("%Y%m%d-%H%M%S")
    image = sklearn_image(a.region)

    print(f"Uploading data + code to s3://{bucket}/training/{run_id}/")
    src_uri, data_uri = upload_sources(sess.client("s3"), bucket, run_id)
    out_uri = f"s3://{bucket}/models/{run_id}/"

    print(f"Launching 3 SageMaker training jobs ({a.instance}, image {image})")
    sm = sess.client("sagemaker")
    with ThreadPoolExecutor(3) as ex:
        futs = [ex.submit(run_job, sm, n, e, h, image, role, src_uri, data_uri, out_uri, a.region, a.instance)
                for n, (e, h) in MODELS.items()]
        results = dict(f.result() for f in futs)

    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    path = os.path.join(ROOT, "build", "model_artifacts.json")
    json.dump({"region": a.region, "run_id": run_id, "models": results}, open(path, "w"), indent=2)
    print(f"\nWrote {path}. Next: cdk deploy ClaimsTriageApp")


if __name__ == "__main__":
    main()
