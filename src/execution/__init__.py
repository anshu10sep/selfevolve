"""Deterministic execution layer for the SelfEvolve trading system.

This layer handles all mathematical, regulatory, and risk management logic
that MUST NOT be delegated to LLMs. Every function here is deterministic
and operates on strict numerical/logical rules.
"""
