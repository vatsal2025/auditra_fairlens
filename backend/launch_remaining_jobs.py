"""
Launches the 3 remaining AutoML training jobs using already-created dataset IDs.
Run this on the VM since COMPAS job already launched but adult/german did not.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

PROJECT_ID = "project-6bf0badc-9510-4a48-9e6"
REGION     = "us-central1"
BUDGET_MILLI_NODE_HOURS = 1000

# Dataset resource names from setup_vertex.py output
DATASETS = {
    "auditra-chain-scorer-adult-train": {
        "resource": "projects/109675598322/locations/us-central1/datasets/2983343932307406848",
        "target":   "sex",
    },
    "auditra-chain-scorer-adult-test": {
        "resource": "projects/109675598322/locations/us-central1/datasets/1534310752200949760",
        "target":   "sex",
    },
    "auditra-chain-scorer-german": {
        "resource": "projects/109675598322/locations/us-central1/datasets/2025203111584333824",
        "target":   "sex",
    },
}

from google.cloud import aiplatform
aiplatform.init(project=PROJECT_ID, location=REGION)

for display_name, cfg in DATASETS.items():
    print(f"\n[train] Launching: {display_name}  target={cfg['target']}")
    dataset = aiplatform.TabularDataset(cfg["resource"])

    job = aiplatform.AutoMLTabularTrainingJob(
        display_name=display_name,
        optimization_prediction_type="classification",
        project=PROJECT_ID,
        location=REGION,
    )

    job.run(
        dataset=dataset,
        target_column=cfg["target"],
        budget_milli_node_hours=BUDGET_MILLI_NODE_HOURS,
        model_display_name=display_name,
        training_fraction_split=0.8,
        validation_fraction_split=0.1,
        test_fraction_split=0.1,
        sync=False,
    )

    try:
        print(f"        Resource: {job.resource_name}")
    except Exception:
        print(f"        Launched (resource name registers shortly)")

print("\nAll 3 jobs launched. Monitor at:")
print(f"https://console.cloud.google.com/vertex-ai/training?project={PROJECT_ID}")
