# Changelog

## 1.0.0 - 2026-11-09

Initial release.

* Batch comparison of truck loads against DAT national spot
  benchmarks by equipment type: dry van $3.07, reefer $3.63,
  flatbed $3.62 per mile (DAT national spot averages, linehaul plus
  fuel surcharge, week of Oct 24-30, 2026, reported by The Trucker
  on 2026-11-04).
* Deadhead-adjusted rates: rate per loaded mile and rate per total
  mile (loaded plus deadhead) for every load, with the ABOVE/BELOW
  verdict based on the total-mile rate.
* Per-load shortfall in dollars, computed exactly from the
  unrounded rate (benchmark times total miles minus gross pay).
* Summary counts, average rates per loaded and total mile, average
  and total shortfall, and best and worst load by rate per total
  mile.
* Benchmarks overridable with a --benchmarks JSON file or
  repeatable --benchmark EQUIPMENT=RATE flags, so the numbers are
  never hardcoded magic.
* Equipment name aliases (van, dry-van, refrigerated, flat bed)
  normalized to dry van, reefer, and flatbed.
* Decimal money math with cents rounding (half up).
* Text and --json output, --out file output, --equipment filter,
  and a --check CI gate that exits 1 when any load is below
  benchmark.
* Bad input (missing fields, negative miles, negative pay, unknown
  equipment, duplicate ids, non-numeric values) reported as data
  errors with exit code 2, not crashes.
* Zero dependencies, Python 3.10 or newer.
