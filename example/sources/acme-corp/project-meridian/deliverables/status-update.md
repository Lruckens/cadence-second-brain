# Weekly status — Project Meridian

**Date:** 2026-09-01
**Author:** Delivery lead

The forecasting model integration slipped by one sprint because the client's data
export only arrives in CSV, not the JSON the pipeline expects. We decided to add a
CSV adapter in the ingestion layer rather than ask the client to change their export
— changing the client's system would have taken longer and risked the relationship.

Consultant capacity: one data engineer rolled off this week to backfill on Project
Atlas, which is at risk of understaffing. We have not yet decided who replaces them
on Meridian — this needs a decision before next sprint planning.

Open question: does the CSV adapter need to handle multiple client regions, or just
the one we've seen so far? Nobody has confirmed this with the client yet.
