"""
Gemini via aicredits.in (cheap OpenAI-compatible proxy) → AI Studio key → Vertex AI fallback.
"""
import json
from typing import List, Optional

import httpx

from app.core.config import settings
from app.models.schemas import Chain

_explanation_cache: dict[tuple, str] = {}

AICREDITS_ENDPOINT = "https://api.aicredits.in/v1/chat/completions"
AICREDITS_MODEL = "gemini-2.0-flash"


def _call_aicredits(system: str, user: str) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.aicredits_api_key}",
    }
    payload = {
        "model": AICREDITS_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": 4096,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(AICREDITS_ENDPOINT, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


def _call_aicredits_with_history(system: str, messages: list) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.aicredits_api_key}",
    }
    payload = {
        "model": AICREDITS_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "max_tokens": 4096,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(AICREDITS_ENDPOINT, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


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

CHAIN_EXPLANATION_SYSTEM = "You are a fairness auditor. Explain ML discrimination risks clearly to non-technical stakeholders."


def explain_chain(chain: Chain) -> str:
    cache_key = (tuple(chain.path), chain.protected_attribute)
    if cache_key in _explanation_cache:
        return _explanation_cache[cache_key]

    hop_details = "\n".join(
        f"  {h.source} → {h.target} (predictive strength: {h.weight:.2%})"
        for h in chain.hops
    )
    user_prompt = CHAIN_EXPLANATION_PROMPT.format(
        path=" → ".join(chain.path),
        protected=chain.protected_attribute,
        risk_score=f"{chain.risk_score:.0%}",
        risk_label=chain.risk_label,
        hop_details=hop_details,
    )

    try:
        result = _call_aicredits(CHAIN_EXPLANATION_SYSTEM, user_prompt)
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

    # Build OpenAI-style message list from history
    messages = []
    for turn in history:
        role = "user" if turn["role"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        return _call_aicredits_with_history(system_content, messages)
    except Exception:
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
                f"**Chain logic:** Features chain together as statistical proxies to reconstruct a protected attribute.\n\n"
                f"Top: `{' → '.join(top.path)}` → `{top.protected_attribute}` ({top.risk_score:.0%} skill)\n\n"
                f"| # | Path | Risk | Skill |\n|---|---|---|---|\n{rows}"
            )
    if any(w in msg for w in ["complian", "regulat", "law", "eu", "act", "legal", "gdpr", "ecoa"]):
        return (
            "**Compliance implications:**\n"
            "- **EU AI Act Article 10** — data governance must prevent proxy discrimination\n"
            "- **GDPR Article 22** — no automated decisions based on protected proxies\n"
            "- **US ECOA** — adverse action cannot stem from protected-class proxy features\n\n"
            f"{'HIGH/CRITICAL chains found — immediate remediation required.' if high else 'No HIGH/CRITICAL chains — lower compliance risk.'}"
        )
    if any(w in msg for w in ["fairness", "metric", "spd", "disparate", "impact", "parity", "tpr", "fpr"]):
        return (
            "**Fairness metrics:**\n"
            "- **SPD** — Statistical Parity Diff: P(ŷ=1|unprivileged) − P(ŷ=1|privileged). Fair: |SPD| < 0.1\n"
            "- **DI** — Disparate Impact ratio: ≥ 0.8 required (80% rule)\n"
            "- **EOD** — Equal Opportunity Diff: TPR gap across groups\n"
            "- **AOD** — Average Odds Diff: mean of TPR + FPR gaps\n\n"
            "See the Fairness Metrics panel for exact values."
        )
    n_high = len(high)
    return (
        f"**Audit summary:** {len(chains)} relay chains, {n_high} HIGH/CRITICAL risk.\n\n"
        + (f"Top: `{' → '.join(top.path)}` → `{top.protected_attribute}` "
           f"({top.risk_score:.0%} skill). Cut `{top.weakest_link}` to break it.\n\n" if top else "")
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
