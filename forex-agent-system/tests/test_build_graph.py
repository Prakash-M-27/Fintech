"""Tests for graph/build_graph.py — the control-flow safety contract.

WHY these tests exist:
    The graph's conditional edge is the enforcement point that guarantees a
    signal is only executed when the Risk Agent approved it. We test the
    routing predicate directly (deterministically) AND the end-to-end graph
    behavior with the default mock-data pipeline, whose fixed seed inputs
    exercise the full node chain without external dependencies.
"""

from __future__ import annotations

from graph.build_graph import build_graph, _route_after_risk


class TestRouteAfterRisk:
    """Direct unit tests of the conditional-edge predicate."""

    def test_approved_routes_to_execution(self):
        assert _route_after_risk({"risk_check": {"approved": True}}) == "execution"

    def test_rejected_routes_to_audit(self):
        assert _route_after_risk({"risk_check": {"approved": False}}) == "audit_trail"

    def test_missing_risk_check_routes_to_audit(self):
        # THE critical safety property: absence of approval can never be
        # interpreted as approval. A missing risk_check must go to audit.
        assert _route_after_risk({}) == "audit_trail"

    def test_approved_must_be_exactly_true(self):
        # Truth-y but not literally True (e.g. 1, "yes") must NOT pass.
        for bad in (1, "yes", "True", None, [], {}):
            assert _route_after_risk({"risk_check": {"approved": bad}}) == "audit_trail"


class TestEndToEnd:
    """Full-pipeline routing tests using the mock-data graph."""

    def test_default_pipeline_produces_coherent_terminal_state(self):
        app = build_graph().compile()
        out = app.invoke({"instrument": "USDINR", "trace_id": "e2e-1"})
        # Guaranteed invariants regardless of random data:
        assert out["risk_check"] is not None
        assert out["execution_result"] is not None
        # If the signal was HOLD (typical for mock data), it must be REJECTED,
        # never executed. If it was a real signal, approval implies execution.
        if out.get("proposed_signal", {}).get("action") == "HOLD":
            assert out["execution_result"]["status"] == "REJECTED"

    def test_no_path_leaves_execution_without_risk_check(self):
        app = build_graph().compile()
        out = app.invoke({"instrument": "USDINR", "trace_id": "e2e-2"})
        # Explicitly assert the invariant: no execution without risk approval.
        if out["execution_result"]["status"] not in ("REJECTED",):
            assert out["risk_check"]["approved"] is True
