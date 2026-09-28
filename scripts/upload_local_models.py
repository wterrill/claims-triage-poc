"""Fallback for accounts whose SageMaker *training* quota is 0 (common on new accounts).

Trains the 3 models locally with the same entry points and hyperparameters as
train_in_sagemaker.py, packages each as a SageMaker model.tar.gz (model + code/), uploads
them to the Foundation artifact bucket and writes build/model_artifacts.json. Hosting is
unchanged: the endpoints still run on the AWS-managed scikit-learn 1.2-1 container.

Must run under scikit-learn 1.2.1 (the serving container's version) so the pickles load, e.g.
  uv venv -p 3.9 .venv-sk12 && VIRTUAL_ENV=.venv-sk12 uv pip install scikit-learn==1.2.1 \
      numpy==1.24.1 pandas==1.1.3 scipy==1.8.0 joblib boto3
  .venv-sk12/bin/python scripts/upload_local_models.py --region us-east-2
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time

import boto3
import sklearn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_in_sagemaker import FOUNDATION_STACK, MODELS, sklearn_image, stack_outputs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default=os.environ.get("AWS_REGION", "us-east-1"))
    a = ap.parse_args()
    if not sklearn.__version__.startswith("1.2."):
        raise SystemExit(f"scikit-learn {sklearn.__version__} found; the 1.2-1 serving container needs "
                         "1.2.x pickles. See this file's docstring.")

    sess = boto3.Session(region_name=a.region)
    outs = stack_outputs(sess.client("cloudformation"), FOUNDATION_STACK)
    bucket = outs["ArtifactBucketName"]
    run_id = "local-" + time.strftime("%Y%m%d-%H%M%S")
    image = sklearn_image(a.region)
    s3 = sess.client("s3")
    work = os.path.join(ROOT, "build", "sm_model")
    shutil.rmtree(work, ignore_errors=True)

    results = {}
    for name, (entry, hps) in MODELS.items():
        mdir = os.path.join(work, name)
        os.makedirs(mdir)
        args = [sys.executable, os.path.join(ROOT, "ml", "src", entry), "--model-dir", mdir,
                "--train", os.path.join(ROOT, "data")]
        for k, v in hps.items():
            args += [f"--{k}", str(v)]
        out = subprocess.run(args, check=True, capture_output=True, text=True).stdout
        metrics = json.load(open(os.path.join(mdir, "metrics.json")))
        tgz = os.path.join(work, f"{name}.tar.gz")
        with tarfile.open(tgz, "w:gz") as tar:
            for f in os.listdir(mdir):
                tar.add(os.path.join(mdir, f), arcname=f)
        key = f"models/{run_id}/{name}/model.tar.gz"
        s3.upload_file(tgz, bucket, key)
        print(f"  {name}: {out.strip().splitlines()[-1]} -> s3://{bucket}/{key}")
        results[name] = {"job": f"local:{run_id}", "model_data": f"s3://{bucket}/{key}",
                         "entry_point": entry, "image": image, "metrics": metrics}

    path = os.path.join(ROOT, "build", "model_artifacts.json")
    json.dump({"region": a.region, "run_id": run_id, "models": results}, open(path, "w"), indent=2)
    print(f"Wrote {path}. Next: cdk deploy ClaimsTriageApp")


if __name__ == "__main__":
    main()
