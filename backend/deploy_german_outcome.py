"""
Deploy only the german outcome-scorer endpoint.
adult-test is routed to adult-train endpoint in code (same features).
Run after cleanup_empty_endpoints.py frees quota.

  python deploy_german_outcome.py
"""
import os

PROJECT_ID = "project-6bf0badc-9510-4a48-9e6"
REGION     = "us-central1"
MACHINE    = "n1-standard-2"
ENV_FILE   = os.path.join(os.path.dirname(__file__), ".env")

from google.cloud import aiplatform
aiplatform.init(project=PROJECT_ID, location=REGION)

display_name = "auditra-outcome-scorer-german"

models = aiplatform.Model.list(
    filter=f'display_name="{display_name}"',
    project=PROJECT_ID,
    location=REGION,
    order_by="create_time desc",
)
if not models:
    print(f"ERROR: No trained model '{display_name}'")
    exit(1)

model = models[0]
print(f"[deploy] Found: {display_name} ({model.resource_name})")

endpoints = aiplatform.Endpoint.list(
    filter=f'display_name="{display_name}-endpoint"',
    project=PROJECT_ID,
    location=REGION,
)
if endpoints:
    eid = endpoints[0].resource_name.split("/")[-1]
    print(f"[deploy] Already exists: endpoint {eid}")
else:
    endpoint = model.deploy(
        deployed_model_display_name=display_name,
        machine_type=MACHINE,
        min_replica_count=1,
        max_replica_count=1,
        traffic_split={"0": 100},
    )
    eid = endpoint.resource_name.split("/")[-1]
    print(f"[deploy] Done: {display_name} → endpoint {eid}")

# Write to .env
lines = []
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        lines = f.readlines()

key = "VERTEX_AI_OUTCOME_GERMAN"
new_lines = []
updated = False
for line in lines:
    if line.startswith(f"{key}="):
        new_lines.append(f"{key}={eid}\n")
        updated = True
    else:
        new_lines.append(line)
if not updated:
    new_lines.append(f"{key}={eid}\n")

with open(ENV_FILE, "w") as f:
    f.writelines(new_lines)

print(f"\n[env] {key}={eid} written to .env")
print("\nRestart server:")
print("  pkill -f uvicorn")
print("  nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &")
