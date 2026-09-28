"""Model 3 - Claim narrative / adjuster-notes classifier (TF-IDF + logistic regression).

Reads free text (FNOL loss description, adjuster notes, or text Textract pulled from a
PDF) and returns:
  * loss_category          - what kind of loss this really is
  * flags                  - injury / litigation / total_loss probabilities
  * key_phrases            - the words that drove the category (for adjuster trust)

Request:  {"instances": [{"text": "IV was rear-ended at light..."}]}
"""
import argparse
import json
import os
import re
import shutil

import joblib
import numpy as np
import pandas as pd

MODEL_FILE = "notes_model.joblib"
FLAGS = {"injury": "injury_reported", "litigation": "attorney_involved",
         "total_loss": "total_loss_indicated"}

# Expand legacy shorthand so the vectorizer sees real words too
ABBREV = {r"\biv\b": "insured vehicle", r"\bcv\b": "claimant vehicle", r"\binsd\b": "insured",
          r"\bclmt\b": "claimant", r"\bee\b": "employee", r"\batty\b": "attorney",
          r"\blor\b": "letter of representation", r"\bfd\b": "fire department",
          r"\btl\b": "total loss", r"\bacv\b": "actual cash value", r"\bveh\b": "vehicle",
          r"\bf/u\b": "follow up", r"\bw/\b": "with", r"\bems\b": "ambulance"}


def normalize(text: str) -> str:
    t = (text or "").lower()
    for pat, rep in ABBREV.items():
        t = re.sub(pat, rep, t)
    return t


def train(args):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
    from sklearn.model_selection import train_test_split

    df = pd.read_csv(os.path.join(args.train, "claims_history.csv"))
    text = df["narrative"].fillna("").map(normalize)
    tr, te = train_test_split(df.index, test_size=0.2, random_state=3, stratify=df["loss_category"])

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    Xtr, Xte = vec.fit_transform(text[tr]), vec.transform(text[te])

    cat = LogisticRegression(C=args.C, max_iter=2000).fit(Xtr, df.loc[tr, "loss_category"])
    metrics = {"category_accuracy": round(float(accuracy_score(df.loc[te, "loss_category"], cat.predict(Xte))), 4),
               "category_macro_f1": round(float(f1_score(df.loc[te, "loss_category"], cat.predict(Xte), average="macro")), 4)}
    flag_models = {}
    for name, col in FLAGS.items():
        m = LogisticRegression(C=args.C, max_iter=2000).fit(Xtr, df.loc[tr, col])  # unweighted -> calibrated probs
        metrics[f"{name}_auc"] = round(float(roc_auc_score(df.loc[te, col], m.predict_proba(Xte)[:, 1])), 4)
        flag_models[name] = m
    metrics.update({"n_train": int(len(tr)), "n_test": int(len(te))})
    for k, v in metrics.items():
        print(f"metric_{k}={v};")

    joblib.dump({"vec": vec, "cat": cat, "flags": flag_models}, os.path.join(args.model_dir, MODEL_FILE))
    json.dump(metrics, open(os.path.join(args.model_dir, "metrics.json"), "w"), indent=2)
    code = os.path.join(args.model_dir, "code")
    os.makedirs(code, exist_ok=True)
    shutil.copy(os.path.abspath(__file__), code)
    print("notes model saved")


def model_fn(model_dir):
    return joblib.load(os.path.join(model_dir, MODEL_FILE))


def input_fn(body, content_type="application/json"):
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8")
    if content_type and content_type.startswith("text/plain"):
        return [body]
    data = json.loads(body)
    if isinstance(data, dict) and "instances" in data:
        data = data["instances"]
    if isinstance(data, dict):
        data = [data]
    return [d.get("text", "") if isinstance(d, dict) else str(d) for d in data]


def predict_fn(texts, art):
    vec, cat = art["vec"], art["cat"]
    X = vec.transform([normalize(t) for t in texts])
    probs = cat.predict_proba(X)
    vocab = np.array(vec.get_feature_names_out())
    out = []
    for i in range(len(texts)):
        k = int(np.argmax(probs[i]))
        label = cat.classes_[k]
        # key phrases = present terms with the largest positive weight for the chosen class
        row = X[i].toarray().ravel()
        contrib = row * cat.coef_[k]
        idx = [j for j in np.argsort(-contrib)[:4] if contrib[j] > 0]
        flags = {name: round(float(m.predict_proba(X[i])[0, 1]), 4) for name, m in art["flags"].items()}
        out.append({
            "loss_category": label,
            "category_confidence": round(float(probs[i][k]), 4),
            "flags": flags,
            "flagged": sorted([n for n, p in flags.items() if p >= 0.5]),
            "key_phrases": vocab[idx].tolist(),
        })
    return out


def output_fn(prediction, accept="application/json"):
    return json.dumps({"predictions": prediction}), "application/json"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--C", type=float, default=4.0)
    ap.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model/notes"))
    ap.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "data"))
    a = ap.parse_args()
    os.makedirs(a.model_dir, exist_ok=True)
    train(a)
