"""
Gemini integration — two backends, automatic fallback:

1. Google AI Studio (GEMINI_API_KEY in .env) — simplest, free tier available
2. Vertex AI (GCP_PROJECT_ID + ADC) — uses GCP credits, may require model enablement
3. Rule-based fallback — always works, no AI needed
"""
from typing import List, Optional

from app.core.config import settings
from app.models.schemas import Chain

# Cache keyed on (path_tuple, protected_attribute)
_explanation_cache: dict[tuple, str] = {}

_VERTEX_INIT = False


def _init_vertex():
    global _VERTEX_INIT
    if not _VERTEX_INIT:
        import vertexai
        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
        _VERTEX_INIT = True


# ---------------------------------------------------------------------------
# Chain explanation
# ---------------------------------------------------------------------------

CHAIN_EXPLANATION_PROMPT = """You are a fairness auditor explaining a discrimination risk to a non-technical stakeholder.

A multi-hop proxy discrimination chain was found in a dataset:

Chain path: {path}
Protected attribute: {protected}
Skill score: {risk_score} ({risk_label}) — skill above random-chance baseline
Hop details:
{hop_details}

Write a 3-4 sentence plain English explanation that:
1. Describes how this chain allows indirect discrimination against people with attribute "{protected}"
2. Mentions the historical or social reason this chain is problematic (e.g., redlining, systemic bias)
3. States which regulation this likely violates (EU AI Act Article 10, US ECOA, etc.)
4. Is direct and professional - no jargon, no hedging

Do NOT use bullet points. Write in paragraph form."""


def _generate(prompt: str) -> str:
    """Try AI Studio first, then Vertex AI."""
    if settings.gemini_api_key:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        return model.generate_content(prompt).text.strip()

    if settings.gcp_project_id:
        _init_vertex()
        from vertexai.generative_models import GenerativeModel
        return GenerativeModel("gemini-2.0-flash-001").generate_content(prompt).text.strip()

    raise RuntimeError("No Gemini credentials configured")


def explain_chain(chain: Chain) -> str:
    cache_key = (tuple(chain.path), chain.protected_attribute)
    if cache_key in _explanation_cache:
        return _explanation_cache[cache_key]

    hop_details = "\n".join(
        f"  {h.source} → {h.target} (predictive strength: {h.weight:.2%})"
        for h in chain.hops
    )
    prompt = CHAIN_EXPLANATION_PROMPT.format(
        path=" → ".join(chain.path),
        protected=chain.protected_attribute,
        risk_score=f"{chain.risk_score:.0%}",
        risk_label=chain.risk_label,
        hop_details=hop_details,
    )
    try:
        result = _generate(prompt)
        _explanation_cache[cache_key] = result
        return result
    except Exception:
        return _fallback_explanation(chain)


def _fallback_explanation(chain: Chain) -> str:
    path_str = " → ".join(chain.path)
    return (
        f"This {len(chain.hops)}-hop chain ({path_str}) allows your model to "
        f"indirectly reconstruct '{chain.protected_attribute}' with {chain.risk_score:.0%} "
        f"skill above the majority-class baseline. Each hop individually appears neutral, "
        f"but together they form a discrimination pathway. "
        f"This chain likely violates EU AI Act Article 10 data governance requirements. "
        f"Removing '{chain.weakest_link}' will break the chain."
    )


# ---------------------------------------------------------------------------
# Audit chat assistant
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are FairLens, an AI fairness auditing assistant. You help users understand bias risks in their ML training datasets.

Audit context:
{audit_context}

RESPONSE FORMAT RULES — follow strictly:
- Lead with a 2-3 sentence plain-English summary.
- Then use bullet points (- item) for key findings, actions, or explanations.
- Use a markdown table when comparing metrics, chains, or groups (| Col | Col |).
- Never write long prose paragraphs. Max 4 lines of prose total.
- Be direct and specific — name exact features, exact metrics, exact regulations.
- Regulations to cite when relevant: EU AI Act Article 10, US ECOA, GDPR Article 22."""


def chat(
    user_message: str,
    chains: List[Chain],
    history: List[dict],
    dataset_name: Optional[str] = None,
) -> str:
    audit_context = _build_audit_context(chains, dataset_name)
    system_content = SYSTEM_PROMPT.format(audit_context=audit_context)
    full_prompt = f"{system_content}\n\n---\nUser: {user_message}"

    if settings.gemini_api_key:
        try:
            import google.generativeai as genai
            from google.generativeai.types import HarmCategory, HarmBlockThreshold
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            hist = [{"role": t["role"], "parts": [t["content"]]} for t in history]
            session = model.start_chat(history=hist)
            return session.send_message(full_prompt).text.strip()
        except Exception as e:
            return _rule_based_chat(user_message, chains)

    if settings.gcp_project_id:
        try:
            _init_vertex()
            from vertexai.generative_models import Content, GenerativeModel, Part
            model = GenerativeModel("gemini-2.0-flash-001")
            vertex_history = [
                Content(role=t["role"], parts=[Part.from_text(t["content"])])
                for t in history
            ]
            session = model.start_chat(history=vertex_history)
            return session.send_message(full_prompt).text.strip()
        except Exception:
            return _rule_based_chat(user_message, chains)

    return _rule_based_chat(user_message, chains)


def _rule_based_chat(message: str, chains: List[Chain]) -> str:
    msg = message.lower()
    high = [c for c in chains if c.risk_label in ("HIGH", "CRITICAL")]
    top = chains[0] if chains else None

    if any(w in msg for w in ["fix", "remove", "cut", "break", "mitigat"]):
        if top:
            rows = "\n".join(
                f"| {' → '.join(c.path)} | {c.risk_label} ({c.risk_score:.0%}) | `{c.weakest_link}` |"
                for c in chains[:5]
            )
            return (
                f"**Recommended fix:** Remove `{top.weakest_link}` — weakest link in the highest-risk chain.\n\n"
                f"| Chain | Risk | Weakest Link |\n|---|---|---|\n{rows}"
            )

    if any(w in msg for w in ["chain", "logic", "how", "explain", "what", "work"]):
        if top:
            rows = "\n".join(
                f"| {i+1} | {' → '.join(c.path)} | {c.risk_label} | {c.risk_score:.0%} |"
                for i, c in enumerate(chains[:5])
            )
            return (
                f"**Chain logic:** Each feature hop is a statistical proxy. Individually neutral features "
                f"chain together to reconstruct a protected attribute.\n\n"
                f"Top chain: `{' → '.join(top.path)}` → `{top.protected_attribute}` "
                f"({top.risk_score:.0%} skill above random baseline)\n\n"
                f"| # | Path | Risk | Skill |\n|---|---|---|---|\n{rows}"
            )

    if any(w in msg for w in ["complian", "regulat", "law", "eu", "act", "legal", "gdpr", "ecoa"]):
        return (
            "**Compliance implications:**\n"
            "- **EU AI Act Article 10** — data governance must prevent proxy discrimination in training data\n"
            "- **GDPR Article 22** — prohibits automated decisions producing legal effects from protected proxies\n"
            "- **US ECOA** — adverse action cannot stem from protected-class proxy features\n\n"
            f"{'Chains with skill >30% are high-priority compliance risks.' if high else 'No HIGH/CRITICAL chains — lower compliance risk.'}"
        )

    if any(w in msg for w in ["fairness", "metric", "spd", "disparate", "impact", "parity", "tpr", "fpr"]):
        return (
            "**Fairness metrics in this audit:**\n"
            "- **SPD** — Statistical Parity Diff: P(ŷ=1|unprivileged) − P(ŷ=1|privileged). Fair if |SPD| < 0.1\n"
            "- **DI** — Disparate Impact ratio: should be ≥ 0.8 (80% rule, EEOC standard)\n"
            "- **EOD** — Equal Opportunity Diff: TPR gap. Fair if |EOD| < 0.1\n"
            "- **AOD** — Average Odds Diff: mean of TPR + FPR gaps\n\n"
            "Check the Fairness Metrics panel for your dataset's exact values."
        )

    n_high = len(high)
    return (
        f"**Audit summary:** {len(chains)} relay chains found, {n_high} HIGH/CRITICAL risk.\n\n"
        + (f"Top risk: `{' → '.join(top.path)}` predicts `{top.protected_attribute}` "
           f"with **{top.risk_score:.0%} skill** above random baseline. "
           f"Cut `{top.weakest_link}` to break it.\n\n" if top else "")
        + "Ask about: chain logic · compliance · how to fix · fairness metrics"
    )


def _build_audit_context(chains: List[Chain], dataset_name: Optional[str]) -> str:
    lines = []
    if dataset_name:
        lines.append(f"Dataset: {dataset_name}")
    lines.append(f"Total chains found: {len(chains)}")
    for i, c in enumerate(chains[:10], 1):
        lines.append(
            f"Chain {i}: {' → '.join(c.path)} | "
            f"Protected: {c.protected_attribute} | "
            f"Risk: {c.risk_label} ({c.risk_score:.0%} skill) | "
            f"Weakest link: {c.weakest_link}"
        )
    return "\n".join(lines)
