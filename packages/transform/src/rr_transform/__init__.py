"""Cleaning rules for the silver layer.

Pure Python with no third-party dependencies, so the same functions run in unit tests (CI)
and inside Spark UDFs on Databricks. Every rule comes from a measured fact in
``docs/data/profiles/sg-alerts-bronze-2026-11-14.md``.
"""
