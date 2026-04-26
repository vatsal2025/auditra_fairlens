"""
Delete empty Vertex AI endpoints created by failed deploy_remaining_outcome.py.
These endpoints have no deployed models but consume quota.

Run:
  python cleanup_empty_endpoints.py
"""
PROJECT_ID = "project-6bf0badc-9510-4a48-9e6"
REGION     = "us-central1"

# Endpoints created but with no model deployed (from failed run)
EMPTY_ENDPOINT_IDS = [
    "4131050453263712256",   # auditra-outcome-scorer-adult-test (empty)
    "2081349672856715264",   # auditra-outcome-scorer-german (empty)
]

from google.cloud import aiplatform
aiplatform.init(project=PROJECT_ID, location=REGION)

for eid in EMPTY_ENDPOINT_IDS:
    try:
        ep = aiplatform.Endpoint(endpoint_name=eid)
        print(f"[delete] Deleting empty endpoint {eid}...")
        ep.delete(force=True)
        print(f"[delete] Done: {eid}")
    except Exception as e:
        print(f"[delete] Error {eid}: {e}")

print("\nEmpty endpoints cleaned. Quota freed.")
print("Now run: python deploy_german_outcome.py")
