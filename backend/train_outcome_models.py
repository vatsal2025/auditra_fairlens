"""
Launch 4 AutoML outcome-prediction training jobs using existing Vertex AI datasets.
These models predict the OUTCOME column (recidivism / income / credit risk)
from all features - used for fairness metric computation via Vertex AI.

Run on VM after the chain-scorer models are deployed:
  source venv/bin/activate
  python train_outcome_models.py
"""
import os
import sys
import time

PROJECT_ID = "project-6bf0badc-9510-4a48-9e6"
REGION     = "us-central1"
BUDGET     = 1000  # milli-node-hours (1 node-hour minimum)

# Same dataset resource IDs used for chain-scorer models
JOBS = [
    {
        "name":    "auditra-outcome-scorer-compas",
        "dataset": "projects/109675598322/locations/us-central1/datasets/5049933211317043200",
        "target":  "two_year_recid",
    },
    {
        "name":    "auditra-outcome-scorer-adult-train",
        "dataset": "projects/109675598322/locations/us-central1/datasets/2983343932307406848",
        "target":  "income",
    },
    {
        "name":    "auditra-outcome-scorer-adult-test",
        "dataset": "projects/109675598322/locations/us-central1/datasets/1534310752200949760",
        "target":  "income",
    },
    {
        "name":    "auditra-outcome-scorer-german",
        "dataset": "projects/109675598322/locations/us-central1/datasets/2025203111584333824",
        "target":  "credit_risk_binary",
    },
]


def launch_job(cfg: dict) -> bool:
    from google.cloud import aiplatform

    name   = cfg["name"]
    target = cfg["target"]
    print(f"\n── Launching: {name}  (target={target})")

    try:
        dataset = aiplatform.TabularDataset(cfg["dataset"])

        job = aiplatform.AutoMLTabularTrainingJob(
            display_name=name,
            optimization_prediction_type="classification",
            project=PROJECT_ID,
            location=REGION,
        )

        job.run(
            dataset=dataset,
            target_column=target,
            budget_milli_node_hours=BUDGET,
            model_display_name=name,
            training_fraction_split=0.8,
            validation_fraction_split=0.1,
            test_fraction_split=0.1,
            sync=False,
        )

        time.sleep(5)
        try:
            print(f"   Resource : {job.resource_name}")
        except Exception:
            pass

        print(f"   Status   : LAUNCHED")
        return True

    except Exception as e:
        print(f"   ERROR: {e}")
        return False


def main():
    from google.cloud import aiplatform
    aiplatform.init(project=PROJECT_ID, location=REGION)

    print("=" * 60)
    print("Auditra - Launch 4 Outcome-Prediction AutoML Jobs")
    print(f"Project : {PROJECT_ID}")
    print(f"Budget  : {BUDGET} milli-node-hours per job")
    print("=" * 60)

    results = {}
    for cfg in JOBS:
        ok = launch_job(cfg)
        results[cfg["name"]] = ok

    print("\n" + "=" * 60)
    all_ok = True
    for name, ok in results.items():
        status = "LAUNCHED" if ok else "FAILED"
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False

    print()
    print("Monitor at:")
    print(f"  https://console.cloud.google.com/vertex-ai/training?project={PROJECT_ID}")
    print()
    if all_ok:
        print("Wait 1-3 hours for all to show 'Succeeded', then run:")
        print("  python deploy_outcome_models.py")
    else:
        print("Fix failed jobs above, then re-run for those only.")
    print("=" * 60)


if __name__ == "__main__":
    main()
