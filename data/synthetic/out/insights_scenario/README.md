# Insights Scenario Dataset (Constructed Synthetic)

This dataset is a constructed scenario with planted bursts and temporal patterns designed specifically for demonstrating and testing the Timeline Insights feature in KAVACH. It is NOT evaluation or benchmark ground truth data.

## Planted Patterns Summary:
- 2 Call Volume Spikes: Day 10 (2026-01-10) and Day 20 (2026-01-20).
- 2 Transfer Volume Spikes: Day 12 (2026-01-12, count spike) and Day 21 (2026-01-21, amount spike).
- 2 Call-then-Transfer Correlations: 2026-01-10 -> 2026-01-12 and 2026-01-20 -> 2026-01-21.
- 3 New and Busy Identifiers:
  - Phone 9899112233: first seen 2026-01-10, carries ~21.5% of calls on Day 10 spike.
  - Account 998811223344: first seen 2026-01-12, carries ~21.6% of transfers on Day 12 spike.
  - IMEI 358811223344556: first seen 2026-01-20, carries ~21.6% of calls on Day 20 spike.
- 1 Additional FIR (FIR_101.txt): links new phone 9899112233 to suspect Rajendra Singh.
