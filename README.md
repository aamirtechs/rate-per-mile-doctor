# rate-per-mile-doctor
**Live tool:** https://aamirtechs.github.io/rate-per-mile-doctor/ (runs in your browser, no install)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/rate-per-mile-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/rate-per-mile-doctor/issues)

A zero-dependency Python CLI that batch-compares a list of truck
loads against DAT national spot benchmarks by equipment type, using
deadhead-adjusted rates. Give it the loads on a load board and it
tells you, per load, whether the rate per total mile beats the
national average for that equipment, and how much money a
below-benchmark load leaves on the table.

The gross rate on a broker's load sheet is not the rate you actually
earn. A load paying $2.88 per loaded mile can still pay $2.30 per
total mile once 200 empty miles to the pickup are counted, which is
$0.77 under the dry van national average on every mile of the trip.
This tool makes that arithmetic explicit, per load, so the book it
or skip it decision is a number, not a gut feeling.

## Benchmarks

Default benchmarks are DAT national spot averages, linehaul plus
fuel surcharge, for the week of Oct 24-30, 2026, as reported by The
Trucker on 2026-11-04:

| Equipment | Benchmark per mile |
| --- | --- |
| Dry van | $3.07 |
| Reefer | $3.63 |
| Flatbed | $3.62 |

Spot rates move every week, so these defaults are a snapshot, not a
live feed. The prior month (September 2026) averaged $3.01 dry van,
$3.62 reefer, and $3.61 flatbed. Override the numbers with a
`--benchmarks` JSON file or repeatable `--benchmark` flags whenever
a newer DAT release comes out, or when you want to compare against
your own contract rates instead. See
[Overriding benchmarks](#overriding-benchmarks).

## Install

Requires Python 3.10 or newer. No dependencies beyond the standard
library.

```bash
pip install rate-per-mile-doctor
```

Or run it straight from the source checkout:

```bash
python3 rate_per_mile_doctor.py examples/loads.json
```

## Input format

A JSON list, or an object with a `loads` list. Each load needs an
`id` (or `load_id` / `load_number`), `loaded_miles`, `gross_pay`,
and `equipment`. Optional fields: `deadhead_miles` (default 0),
`lane` (or `origin` and `destination`, which are combined into a
lane). Numbers may be given as JSON numbers or as strings, and
gross pay may include a `$` sign and commas.

Equipment names are flexible: `van`, `dry-van`, and `dryvan` all
mean dry van; `refrigerated` means reefer; `flat bed` means flatbed.
Anything else is a data error.

```json
[
  {
    "id": "L-201",
    "lane": "Dallas, TX to Oklahoma City, OK",
    "equipment": "dry van",
    "loaded_miles": 500,
    "deadhead_miles": 60,
    "gross_pay": 2400
  },
  {
    "id": "L-202",
    "lane": "Houston, TX to Atlanta, GA",
    "equipment": "dry van",
    "loaded_miles": 800,
    "deadhead_miles": 200,
    "gross_pay": 2300
  }
]
```

## Example output

```bash
$ python3 rate_per_mile_doctor.py examples/loads.json
Rate per mile vs DAT national spot benchmarks
Benchmarks: dry van $3.07, reefer $3.63, flatbed $3.62 per mile
Source: DAT national spot averages, linehaul plus fuel surcharge, week of Oct 24-30, 2026 (reported by The Trucker, 2026-11-04)

ID       Equipment  Loaded  Deadhead   Total   Gross pay  $/loaded   $/total  Benchmark   Diff/mi  Verdict
----------------------------------------------------------------------------------------------------------
L-201    dry van       500        60     560    $2400.00     $4.80     $4.29      $3.07    +$1.22  ABOVE
L-202    dry van       800       200    1000    $2300.00     $2.88     $2.30      $3.07    -$0.77  BELOW
L-203    reefer        650       150     800    $2850.00     $4.38     $3.56      $3.63    -$0.07  BELOW
L-204    flatbed       300        20     320    $1250.00     $4.17     $3.91      $3.62    +$0.29  ABOVE
L-205    reefer        150        90     240     $500.00     $3.33     $2.08      $3.63    -$1.55  BELOW

Summary: 5 loads, 2 ABOVE benchmark, 3 BELOW benchmark
Average rate per total mile: $3.23
Average rate per loaded mile: $3.91
Average shortfall per below-benchmark load: $398.40 (total $1195.20)
Best rate per total mile: L-201 at $4.29
Worst rate per total mile: L-205 at $2.08
```

Read it load by load:

* L-201 pays $4.29 per total mile, $1.22 above the dry van
  benchmark. Book it.
* L-202 pays $2.88 per loaded mile, which looks close to the $3.07
  benchmark, but 200 deadhead miles drag it to $2.30 per total
  mile, $770.00 short of the benchmark over the whole trip.
* L-203 pays $4.38 per loaded mile, yet still falls $0.07 short
  per total mile, a $54.00 shortfall, because 150 deadhead miles
  dilute a strong loaded rate.
* L-205 is the worst offer in the batch: $2.08 per total mile on a
  reefer load, $1.55 under benchmark, $371.20 short.

The verdict always uses the rate per total mile, because deadhead
is real cost. The per-loaded-mile rate is shown alongside it so you
can see how much deadhead is eating.

## Flags

| Flag | What it does |
| --- | --- |
| `--json` | Print the report as JSON instead of text |
| `--check` | Exit 1 when any load is below benchmark (a CI gate) |
| `--equipment {dry van,reefer,flatbed}` | Only evaluate loads of that equipment type |
| `--benchmarks FILE` | JSON file overriding benchmark rates |
| `--benchmark EQUIPMENT=RATE` | Override one benchmark rate, repeatable |
| `--out FILE` | Also write the report to a file |
| `--version` | Print the version |

`--check` in action, on the same sample file:

```bash
$ python3 rate_per_mile_doctor.py examples/loads.json --check >/dev/null; echo $?
1
```

The exit code is 1 because three of the five loads are below
benchmark. A file where every load is above benchmark exits 0.

Filter to one equipment type:

```bash
$ python3 rate_per_mile_doctor.py examples/loads.json --equipment reefer
Rate per mile vs DAT national spot benchmarks
Benchmarks: dry van $3.07, reefer $3.63, flatbed $3.62 per mile
Source: DAT national spot averages, linehaul plus fuel surcharge, week of Oct 24-30, 2026 (reported by The Trucker, 2026-11-04)

ID       Equipment  Loaded  Deadhead   Total   Gross pay  $/loaded   $/total  Benchmark   Diff/mi  Verdict
----------------------------------------------------------------------------------------------------------
L-203    reefer        650       150     800    $2850.00     $4.38     $3.56      $3.63    -$0.07  BELOW
L-205    reefer        150        90     240     $500.00     $3.33     $2.08      $3.63    -$1.55  BELOW

Summary: 2 loads, 0 ABOVE benchmark, 2 BELOW benchmark
Average rate per total mile: $2.82
Average rate per loaded mile: $3.86
Average shortfall per below-benchmark load: $212.60 (total $425.20)
Best rate per total mile: L-203 at $3.56
Worst rate per total mile: L-205 at $2.08
```

## Overriding benchmarks

A benchmarks file is a JSON object mapping equipment names to
per-mile rates. `examples/benchmarks.json` ships with the repo:

```json
{"dry van": 2.9, "flatbed": 3.45, "reefer": 3.4}
```

```bash
$ python3 rate_per_mile_doctor.py examples/loads.json --benchmarks examples/benchmarks.json
```

Against those lower contract-style rates, the same five loads come
out 3 ABOVE and 2 BELOW, with a total shortfall of $916.00 and an
average shortfall of $458.00 per below-benchmark load. A single
rate can also be overridden on the command line, and flags win
over the file:

```bash
$ python3 rate_per_mile_doctor.py examples/loads.json --benchmark flatbed=3.80
```

## Bad input

Bad input is reported as a data error, not a crash. The exit code
is 2. `examples/bad-loads.json` has four broken loads; the first
one reported is the missing gross pay:

```bash
$ python3 rate_per_mile_doctor.py examples/bad-loads.json
error: load B-1: missing gross_pay
$ echo $?
2
```

The other three errors in that file are a negative deadhead
(B-2), an unknown equipment type (B-3, "step deck"), and zero
loaded miles (B-4). Missing fields, negative miles, negative pay,
duplicate load ids, unknown equipment, and non-numeric values are
all handled the same way.

## JSON output

`--json` prints the full report as JSON: benchmarks with their
source, one object per load (rates, benchmark, difference per
mile, shortfall, verdict), and the summary. The shortfall for a
below-benchmark load is exact: benchmark times total miles minus
gross pay, computed from the unrounded rate, so L-203 reports
$54.00, not the $56.00 you would get from the rounded $3.56 rate.

## How it differs from load-profit-doctor

load-profit-doctor scores loads against your own operating cost per
mile and answers "does this load make money for my truck".
rate-per-mile-doctor compares loads against the national market
and answers "does this load pay what the market pays". Use both:
a load can beat the market and still lose money if your costs are
high, or make a profit while paying well under the market rate.

## Running the tests

```bash
python3 -m unittest discover -s tests
```

53 tests, all passing. They cover rate math (including the exact
shortfall and the at-benchmark edge case), equipment aliases,
input validation, summary totals, benchmark overrides, and the CLI
flags and exit codes.

## License

MIT. See [LICENSE](LICENSE).
