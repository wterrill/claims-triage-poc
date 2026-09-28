"""Generate the synthetic historical claims dataset used to train all three models.

Usage:  python data/generate_dataset.py --n 5000 --seed 42
Writes: data/claims_history.csv
"""
import argparse
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from claimgen import make_claim  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "claims_history.csv"))
    a = ap.parse_args()

    rng = random.Random(a.seed)
    rows = []
    for i in range(a.n):
        c = make_claim(i, rng)
        r = c.as_row()
        r["incurred_cost"] = round(c.extra["true_cost"], 2)  # severity target
        rows.append(r)

    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    fraud = sum(r["is_fraud"] for r in rows) / len(rows)
    print(f"wrote {len(rows)} claims to {a.out}  (fraud rate {fraud:.1%})")


if __name__ == "__main__":
    main()
