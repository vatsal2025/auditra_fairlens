import asyncio
import multiprocessing
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request

from app.core import session_store
from app.models.schemas import AuditRequest, AuditResponse
from app.services import gemini_service
from app.services.chain_scorer import score_all_chains
from app.services.graph_engine import (
    build_graph,
    build_graph_schema,
    find_chains,
)

router = APIRouter()


def _infer_positive_outcome(df, outcome_col: str) -> str:
    vals = df[outcome_col].dropna()
    if vals.nunique() == 2:
        counts = vals.value_counts()
        return str(counts.index[-1])
    return str(vals.value_counts().index[0])


def _audit_worker(df, col_types, req_dict, result_queue):
    try:
        from app.models.schemas import AuditRequest, AuditResponse
        from app.services import gemini_service
        from app.services.chain_scorer import score_all_chains
        from app.services.graph_engine import build_graph, build_graph_schema, find_chains
        from app.services.gemini_service import _fallback_explanation

        req = AuditRequest(**req_dict)

        G, strengths = build_graph(df, col_types, req.threshold, req.protected_attributes)
        chains = find_chains(G, strengths, req.protected_attributes, req.max_depth, col_types)
        chains = score_all_chains(df, chains)

        explain_limit = 2 if req.fast_mode else 5
        for i, chain in enumerate(chains[:20]):
            if i < explain_limit and chain.risk_label in ("HIGH", "CRITICAL"):
                explanation = gemini_service.explain_chain(chain)
            else:
                explanation = _fallback_explanation(chain)
            chains[i] = chain.model_copy(update={"explanation": explanation})

        nodes, edges = build_graph_schema(G, chains, req.protected_attributes, col_types)

        fairness_metrics = []
        mitigated_fairness_metrics = []
        if req.outcome_column and req.outcome_column in df.columns:
            from app.services.fairness_metrics import compute_all_fairness_metrics, compute_mitigated_fairness_metrics
            privileged = req.privileged_groups or {}
            positive = req.positive_outcome or _infer_positive_outcome(df, req.outcome_column)
            fairness_metrics = compute_all_fairness_metrics(
                df, req.protected_attributes, req.outcome_column, privileged, positive,
            )
            for attr in req.protected_attributes:
                priv = (req.privileged_groups or {}).get(attr)
                if not priv and attr in df.columns:
                    priv = str(df[attr].value_counts().index[0])
                if priv:
                    m = compute_mitigated_fairness_metrics(df, attr, req.outcome_column, priv, positive)
                    if m is not None:
                        mitigated_fairness_metrics.append(m)

        conjunctive_proxies = []
        if not req.fast_mode and len(df.columns) <= 30:
            from app.services.interaction_scanner import find_conjunctive_proxies
            conjunctive_proxies = find_conjunctive_proxies(
                df, req.protected_attributes,
                min_individual_skill=0.05, min_interaction_gain=0.05, max_pairs=40,
            )

        calibration_audit = None
        if not req.fast_mode and req.outcome_column and req.outcome_column in df.columns:
            from app.services.calibration import compute_calibration_audit
            positive = req.positive_outcome or _infer_positive_outcome(df, req.outcome_column)
            for attr in req.protected_attributes:
                cal = compute_calibration_audit(df, attr, req.outcome_column, positive)
                if cal is not None:
                    calibration_audit = cal
                    break

        intersectional_audit = None
        if (not req.fast_mode and req.outcome_column and req.outcome_column in df.columns
                and len(req.protected_attributes) >= 2):
            from app.services.intersectional import compute_intersectional_audit
            positive = req.positive_outcome or _infer_positive_outcome(df, req.outcome_column)
            intersectional_audit = compute_intersectional_audit(
                df, req.protected_attributes, req.outcome_column, positive,
            )

        critical_count = sum(1 for c in chains if c.risk_label == "CRITICAL")
        high_count = sum(1 for c in chains if c.risk_label == "HIGH")
        conj_count = len(conjunctive_proxies)
        cal_str = f" Calibration gap: {calibration_audit.calibration_gap:.3f}." if calibration_audit else ""
        int_str = (
            f" Intersectional max SPD: {intersectional_audit.max_spd_gap:.3f}"
            f" ({len(intersectional_audit.flagged_groups)} flagged)."
            if intersectional_audit else ""
        )
        summary = (
            f"Found {len(chains)} relay chains across "
            f"{len(req.protected_attributes)} protected attribute(s). "
            f"{critical_count} CRITICAL, {high_count} HIGH risk. "
            f"{conj_count} conjunctive proxy pair(s) detected."
            f"{cal_str}{int_str} "
            f"Risk scores are skill above majority-class baseline."
        )

        result = AuditResponse(
            session_id=req.session_id,
            nodes=nodes,
            edges=edges,
            chains=chains,
            summary=summary,
            fairness_metrics=fairness_metrics,
            mitigated_fairness_metrics=mitigated_fairness_metrics,
            conjunctive_proxies=conjunctive_proxies,
            calibration_audit=calibration_audit,
            intersectional_audit=intersectional_audit,
        )

        result_queue.put({"ok": True, "result": result, "G": G, "strengths": strengths})

    except Exception as e:
        import traceback
        result_queue.put({"ok": False, "error": str(e), "traceback": traceback.format_exc()})


@router.post("/audit", response_model=AuditResponse)
async def run_audit(req: AuditRequest, request: Request):
    if not session_store.exists(req.session_id):
        raise HTTPException(status_code=404, detail="Session not found.")

    df = session_store.get(req.session_id, "df")
    col_types = session_store.get(req.session_id, "col_types")

    invalid = [a for a in req.protected_attributes if a not in df.columns]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown columns: {invalid}")

    # Kill any stuck audit process for this session before starting new one
    existing_proc = session_store.get(req.session_id, "audit_proc")
    if existing_proc and existing_proc.is_alive():
        existing_proc.terminate()
        existing_proc.join(timeout=3)

    result_queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=_audit_worker,
        args=(df, col_types, req.model_dump(), result_queue),
        daemon=True,
    )
    proc.start()
    session_store.set(req.session_id, "audit_proc", proc)

    try:
        while proc.is_alive():
            await asyncio.sleep(0.5)
            if await request.is_disconnected():
                raise HTTPException(status_code=499, detail="Client disconnected - audit cancelled.")

        if result_queue.empty():
            raise HTTPException(status_code=500, detail="Audit process exited without result.")

        payload = result_queue.get_nowait()
        if not payload["ok"]:
            raise HTTPException(status_code=500, detail=payload["error"])

        result = payload["result"]
        G = payload["G"]
        strengths = payload["strengths"]

    finally:
        # Always kill process on any exit path - disconnect, timeout, error, or success
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=3)
            if proc.is_alive():
                proc.kill()
        session_store.set(req.session_id, "audit_proc", None)
        result_queue.close()

    session_store.set(req.session_id, "audit", result)
    session_store.set(req.session_id, "G", G)
    session_store.set(req.session_id, "strengths", strengths)
    resolved_positive = None
    if req.outcome_column and req.outcome_column in df.columns:
        resolved_positive = req.positive_outcome or _infer_positive_outcome(df, req.outcome_column)
    session_store.set(req.session_id, "audit_config", {
        "outcome_column": req.outcome_column,
        "privileged_groups": req.privileged_groups,
        "positive_outcome": resolved_positive,
        "protected_attributes": req.protected_attributes,
    })

    return result


class CancelRequest(BaseModel):
    session_id: str


@router.post("/cancel")
async def cancel_audit(req: CancelRequest):
    proc = session_store.get(req.session_id, "audit_proc")
    if proc and proc.is_alive():
        proc.terminate()
        proc.join(timeout=3)
        if proc.is_alive():
            proc.kill()
        session_store.set(req.session_id, "audit_proc", None)
        return {"cancelled": True}
    return {"cancelled": False, "reason": "No active audit"}
