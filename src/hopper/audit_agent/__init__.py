"""Audit agent v0 — Phase 4e.

Minimal, single-threaded service that:
  1. Applies tag-normalization auto-apply rules (cheap, rule-based).
  2. Produces a weekly idea synthesis digest as a proposal (Anthropic API).

Entry point: ``python -m hopper.audit_agent`` or ``hopper-audit-agent``.
"""
