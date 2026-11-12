"""Failure attribution — why did the pre-registered criteria reject this?

A failed experiment is only useful if the failure is *classified*, because
the class determines what next hypothesis is worth spending budget on (and
which are structurally hopeless). v0.3 taxonomy, evaluated mechanically from
the E card:

* ``insufficient_observations`` — not enough evaluation dates to judge
* ``instability``              — the effect flips sign in the parameter
                                  neighborhood (mined noise, not mechanism)
* ``threshold_miss``           — stable direction, insufficient magnitude
* ``deflation``                — the number was there, but the family has been
                                  mined N times and the Bonferroni floor ate it
* ``oos_miss``                 — held in-sample, failed out-of-sample
* ``unknown``                  — none of the above (the honest fallback)

``neutralization_residual`` and ``universe`` classes land with the data-plane
richness that can compute them (later versions); they are recognized in the
taxonomy but never fabricated here.
"""
from __future__ import annotations

from typing import Any

CLASSES = ("insufficient_observations", "instability", "threshold_miss",
           "deflation", "oos_miss", "review_veto", "neutralization_residual",
           "universe", "unknown")


def classify(e_card: dict[str, Any], h_card: dict[str, Any],
             reasons: list[str] | None = None) -> dict[str, Any]:
    reasons = reasons or []
    metrics = e_card.get("metrics", {})
    attribution = e_card.get("attribution", {})
    min_obs = (h_card.get("admission") or {}).get("min_observations")
    n = metrics.get("n_dates")

    evidence: list[str] = list(reasons)

    if min_obs is not None and isinstance(n, (int, float)) and n < min_obs:
        cls = "insufficient_observations"
        evidence.append(f"n_dates={n} < min_observations={min_obs}")
    elif any("deflation" in r for r in reasons):
        cls = "deflation"
    elif (e_card.get("review") or {}).get("admitted") is False:
        cls = "review_veto"
        upheld = (e_card.get("review") or {}).get("upheld_objections") or []
        evidence.append("bear objection verified mechanically: "
                        + (upheld[0].get("check") if upheld else "structure error"))
    elif (e_card.get("oos") or {}).get("verdict") != "pass" and e_card.get("oos"):
        cls = "oos_miss"
        evidence.append("held in-sample, missed the pre-registered OOS window: "
                        + "; ".join((e_card.get("oos") or {}).get("reasons") or [])[:160])
    elif attribution.get("neighborhood_stable") is False:
        cls = "instability"
        neighborhood = attribution.get("neighborhood_rankic", {})
        flips = [k for k, v in neighborhood.items()
                 if (v > 0) != (metrics.get("rankic_mean", 0) > 0)]
        evidence.append(f"sign flips at parameter neighbors {flips or neighborhood}")
    elif metrics.get("rankic_mean") is not None:
        cls = "threshold_miss"
        evidence.append(f"rankic_mean={metrics.get('rankic_mean')} — direction "
                        f"stable but magnitude below the pre-registered bar")
    else:
        cls = "unknown"
        evidence.append("no mechanical classification matched")

    return {"class": cls, "evidence": evidence}


def next_hypothesis_prompt(order_text: str, h_card: dict[str, Any],
                           attribution: dict[str, Any]) -> str:
    """The exact prompt that steers the next iteration of the mining loop."""
    return (
        "Research order:\n" + order_text + "\n\n"
        "Previous hypothesis (rejected):\n" + str({
            "hyp_id": h_card.get("hyp_id"),
            "mechanism": h_card.get("mechanism"),
            "admission": h_card.get("admission"),
        }) + "\n\n"
        "Attribution of the failure:\n" + str(attribution) + "\n\n"
        "Propose the next hypothesis as JSON (fields: mechanism, "
        "falsifiable_condition, admission{required_metrics, thresholds, "
        "min_observations}). The admission bar must stay equally strict — "
        "do not lower thresholds to rescue the previous direction. If the "
        "attribution says instability, change the mechanism family, not the "
        "parameters.")
