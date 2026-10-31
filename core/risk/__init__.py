# core/risk/__init__.py
"""Deterministic six-factor project risk model.

The package is intentionally thin: rules are pure functions over
``RiskFactorScores``; no storage, LLM, or gate imports occur here.
"""
