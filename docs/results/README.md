# Results log

Dated findings, one doc per analysis milestone, immutable once written (caveats reflect
what was known at the time). Newest last:

- [2026-07-04-smoke-test.md](2026-07-04-smoke-test.md) — backfill pipeline verified;
  temp MAE 0.70 → 1.63 °C over leads 0–5 d vs ERA5.
- [2026-07-05-first-real-metrics.md](2026-07-05-first-real-metrics.md) — full metrics
  engine: MAE by nation/season, rain ETS decay, skill vs baselines; UKMO 10 m wind loses
  to climatology beyond day 3.
- [2026-07-05-calibration.md](2026-07-05-calibration.md) — conformal intervals hold 90 %
  coverage out-of-sample; binary rain calls have negative Brier skill from day 2;
  bootstrap CIs make every lead-to-lead difference significant.

All current results are **vs ERA5 truth** (see the standing caveats in
[../methodology.md](../methodology.md)).
