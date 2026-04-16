"""
Builds a feature correlation graph from a DataFrame and detects multi-hop
discrimination chains leading to protected attributes.
"""
import itertools
import uuid
from typing import List, Tuple, Dict

import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from sklearn.preprocessing import LabelEncoder

from app.core.config import settings
from app.models.schemas import Chain, ChainHop, GraphEdge, GraphNode


# ---------------------------------------------------------------------------
# Correlation helpers
# ---------------------------------------------------------------------------

def _cramers_v(x: pd.Series, y: pd.Series) -> float:
    """Cramér's V for two categorical columns."""
    confusion = pd.crosstab(x, y)
    chi2, _, _, _ = chi2_contingency(confusion)
    n = confusion.values.sum()
    r, k = confusion.shape
    phi2 = chi2 / n
    phi2_corr = max(0, phi2 - ((k - 1) * (r - 1)) / (n - 1))
    r_corr = r - ((r - 1) ** 2) / (n - 1)
    k_corr = k - ((k - 1) ** 2) / (n - 1)
    denom = min(r_corr - 1, k_corr - 1)
    if denom <= 0:
        return 0.0
    return float(np.sqrt(phi2_corr / denom))


def _eta_squared(numeric: pd.Series, categorical: pd.Series) -> float:
    """Eta-squared: correlation ratio for numeric vs categorical."""
    groups = [numeric[categorical == cat].dropna() for cat in categorical.unique()]
    grand_mean = numeric.mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in groups if len(g) > 0)
    ss_total = ((numeric - grand_mean) ** 2).sum()
    if ss_total == 0:
        return 0.0
    return float(ss_between / ss_total)


def _pearson(x: pd.Series, y: pd.Series) -> float:
    corr = x.corr(y)
    return float(abs(corr)) if not np.isnan(corr) else 0.0


def _pairwise_strength(df: pd.DataFrame, col_types: Dict[str, str]) -> Dict[Tuple[str, str], float]:
    """Returns a dict of (col_a, col_b) -> predictive strength [0, 1]."""
    cols = list(col_types.keys())
    strengths: Dict[Tuple[str, str], float] = {}
    for a, b in itertools.combinations(cols, 2):
        ta, tb = col_types[a], col_types[b]
        try:
            if ta == "numeric" and tb == "numeric":
                s = _pearson(df[a], df[b])
            elif ta == "categorical" and tb == "categorical":
                s = _cramers_v(df[a].astype(str), df[b].astype(str))
            elif ta == "numeric" and tb == "categorical":
                s = _eta_squared(df[a], df[b].astype(str))
            else:
                s = _eta_squared(df[b], df[a].astype(str))
        except Exception:
            s = 0.0
        strengths[(a, b)] = s
        strengths[(b, a)] = s
    return strengths


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def detect_column_types(df: pd.DataFrame) -> Dict[str, str]:
    types: Dict[str, str] = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) and df[col].nunique() > 10:
            types[col] = "numeric"
        else:
            types[col] = "categorical"
    return types


def build_graph(
    df: pd.DataFrame,
    col_types: Dict[str, str],
    threshold: float,
) -> Tuple[nx.DiGraph, Dict[Tuple[str, str], float]]:
    strengths = _pairwise_strength(df, col_types)
    G = nx.DiGraph()
    G.add_nodes_from(df.columns)

    for (a, b), w in strengths.items():
        if a != b and w >= threshold:
            G.add_edge(a, b, weight=w)

    return G, strengths


# ---------------------------------------------------------------------------
# Chain detection (DFS)
# ---------------------------------------------------------------------------

def _dfs_chains(
    G: nx.DiGraph,
    start: str,
    target: str,
    max_depth: int,
    current_path: List[str],
    all_chains: List[List[str]],
) -> None:
    if len(current_path) > max_depth + 1:
        return
    if len(current_path) > 1 and current_path[-1] == target:
        all_chains.append(list(current_path))
        return
    for neighbor in G.successors(current_path[-1]):
        if neighbor not in current_path:
            _dfs_chains(G, start, target, max_depth, current_path + [neighbor], all_chains)


def find_chains(
    G: nx.DiGraph,
    strengths: Dict[Tuple[str, str], float],
    protected_attributes: List[str],
    max_depth: int,
    col_types: Dict[str, str],
) -> List[Chain]:
    chains: List[Chain] = []
    non_protected = [n for n in G.nodes if n not in protected_attributes]

    for protected in protected_attributes:
        for start in non_protected:
            raw_paths: List[List[str]] = []
            _dfs_chains(G, start, protected, max_depth, [start], raw_paths)

            for path in raw_paths:
                if len(path) < 2:
                    continue
                hops = [
                    ChainHop(
                        source=path[i],
                        target=path[i + 1],
                        weight=round(strengths.get((path[i], path[i + 1]), 0.0), 4),
                    )
                    for i in range(len(path) - 1)
                ]
                # Simple reconstructive accuracy proxy: geometric mean of hop weights
                weights = [h.weight for h in hops]
                risk_score = float(np.prod(weights) ** (1.0 / max(len(weights), 1)))
                risk_label = _risk_label(risk_score)
                weakest = min(hops, key=lambda h: h.weight)

                chains.append(
                    Chain(
                        id=str(uuid.uuid4()),
                        path=path,
                        hops=hops,
                        risk_score=round(risk_score, 4),
                        risk_label=risk_label,
                        protected_attribute=protected,
                        weakest_link=weakest.source,
                    )
                )

    # Sort by risk descending, deduplicate identical paths
    seen = set()
    unique: List[Chain] = []
    for c in sorted(chains, key=lambda x: x.risk_score, reverse=True):
        key = tuple(c.path)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def _risk_label(score: float) -> str:
    if score >= 0.75:
        return "CRITICAL"
    if score >= 0.50:
        return "HIGH"
    if score >= 0.25:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Graph schema helpers
# ---------------------------------------------------------------------------

def build_graph_schema(
    G: nx.DiGraph,
    chains: List[Chain],
    protected_attributes: List[str],
    col_types: Dict[str, str],
) -> Tuple[List[GraphNode], List[GraphEdge]]:
    # Determine worst risk per node
    node_risk: Dict[str, str] = {n: "none" for n in G.nodes}
    for chain in chains:
        for node in chain.path:
            current = _risk_level_value(node_risk[node])
            new = _risk_level_value(chain.risk_label.lower())
            if new > current:
                node_risk[node] = chain.risk_label.lower()

    nodes = [
        GraphNode(
            id=n,
            label=n,
            dtype=col_types.get(n, "categorical"),
            is_protected=n in protected_attributes,
            risk_level=node_risk[n],
        )
        for n in G.nodes
    ]

    edges = [
        GraphEdge(source=u, target=v, weight=round(d["weight"], 4))
        for u, v, d in G.edges(data=True)
    ]

    return nodes, edges


def _risk_level_value(label: str) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(label.lower(), 0)
