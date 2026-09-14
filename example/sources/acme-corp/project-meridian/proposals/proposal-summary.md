# Proposal — Project Meridian forecasting integration

**Date:** 2026-06-15

Acme Corp asked for a forecasting model that predicts weekly demand per region,
integrated into their existing planning tool. We proposed a phased delivery:
phase 1 (8 weeks) builds the core model and a JSON-based ingestion pipeline against
Acme's data warehouse export; phase 2 (4 weeks) adds the planning-tool integration.

We decided to scope out real-time updates for phase 1 — Acme's planning tool only
refreshes daily, so a nightly batch job is sufficient and meaningfully cheaper to
build than a streaming pipeline. Acme's stakeholder (procurement lead) agreed to
this trade-off in the kickoff call.
