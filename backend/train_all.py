"""
Launch all 4 AutoML training jobs using already-created Vertex AI datasets.
Datasets were created by setup_vertex.py - no need to re-upload data.

Run on VM:
  source venv/bin/activate
  python train_all.py
"""
import os
import sys
import time

PROJECT_ID = "project-6bf0badc-9510-4a48-9e6"
REGION     = "us-central1"
BUDGET     = 1000  # milli-node-hours (minimum = 1 node-hour)

# Dataset resource IDs created by setup_vertex.py
JOBS = [
    {
        "name":     "auditra-chain-scorer-compas",
        "dataset":  "projects/109675598322/locations/us-central1/datasets/5049933211317043200",
        "target":   "race",
    },
    {
        "name":     "auditra-chain-scorer-adult-train",
        "dataset":  "projects/109675598322/locations/us-central1/datasets/2983343932307406848",
        "target":   "sex",
    },
    {
        "name":     "auditra-chain-scorer-adult-test",
        "dataset":  "projects/109675598322/locations/us-central1/datasets/1534310752200949760",
        "target":   "sex",
    },
    {
        "name":     "auditra-chain-scorer-german",
        "dataset":  "projects/109675598322/locations/us-central1/datasets/2025203111584333824",
        "target":   "sex",
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

        # Give SDK 5 seconds to register the job before checking resource_name
        time.sleep(5)
        try:
            print(f"   Resource : {job.resource_name}")
        except Exception:
            pass  # resource_name sometimes unavailable immediately with sync=False

        print(f"   Status   : LAUNCHED ✓")
        return True

    except Exception as e:
        print(f"   ERROR: {e}")
        return False


def main():
    from google.cloud import aiplatform
    aiplatform.init(project=PROJECT_ID, location=REGION)

    print("=" * 60)
    print("Auditra - Launch All 4 AutoML Training Jobs")
    print(f"Project : {PROJECT_ID}")
    print(f"Budget  : {BUDGET} milli-node-hours per job")
    print("=" * 60)

    results = {}
    for cfg in JOBS:
        ok = launch_job(cfg)
        results[cfg["name"]] = ok

    print("\n" + "=" * 60)
    print("Results:")
    all_ok = True
    for name, ok in results.items():
        status = "✓ LAUNCHED" if ok else "✗ FAILED"
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False

    print()
    print("Monitor all jobs at:")
    print(f"  https://console.cloud.google.com/vertex-ai/training?project={PROJECT_ID}")
    print()
    if all_ok:
        print("Wait 1-3 hours for all to show 'Succeeded', then run:")
        print("  python deploy_vertex.py")
    else:
        print("Fix failed jobs above, then re-run this script for those only.")
    print("=" * 60)


if __name__ == "__main__":
    main()
