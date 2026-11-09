"""Rate per mile doctor for truck dispatching.

Reads a JSON list of loads offered on a load board and compares each
one against DAT national spot benchmarks by equipment type, using
deadhead-adjusted rates. A load that looks fine per loaded mile can
still pay below the national average once the empty miles to the
pickup are counted, and this tool makes that gap explicit.

The math, per load:

* total miles = loaded miles + deadhead miles
* rate per loaded mile = gross pay / loaded miles
* rate per total mile = gross pay / total miles
* benchmark = DAT national spot average for the equipment type
* difference per mile = rate per total mile - benchmark
* shortfall = (benchmark - rate per total mile) x total miles,
  when the load is below benchmark

A load is ABOVE when its rate per total mile meets or beats the
benchmark, and BELOW otherwise. The verdict uses the total-mile
rate, because deadhead is real cost: the per-loaded-mile rate is
shown alongside it so the dispatcher can see how much deadhead is
eating.

Default benchmarks (DAT national spot averages, linehaul plus fuel
surcharge, week of Oct 24-30, 2026, reported by The Trucker on
2026-11-04):

* dry van: $3.07 per mile
* reefer: $3.63 per mile
* flatbed: $3.62 per mile

Override them with a --benchmarks JSON file or repeatable
--benchmark flags, for example when you want to compare against
contract rates or a newer DAT release instead. The prior month
(September 2026) averaged $3.01 dry van, $3.62 reefer, and $3.61
flatbed, so the market moved up a little for dry van between the
two snapshots.

Zero dependencies, Python 3.10 or newer, standard library only.

Usage:
    python3 rate_per_mile_doctor.py examples/loads.json
    python3 rate_per_mile_doctor.py loads.json --json --check
    python3 rate_per_mile_doctor.py loads.json --equipment reefer
    python3 rate_per_mile_doctor.py loads.json --benchmarks benchmarks.json
"""

import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

__version__ = "1.0.0"

CENT = Decimal("0.01")
RATE_PLACES = Decimal("0.01")

DEFAULT_BENCHMARKS = {
    "dry van": Decimal("3.07"),
    "reefer": Decimal("3.63"),
    "flatbed": Decimal("3.62"),
}

EQUIPMENT_ALIASES = {
    "dry van": "dry van",
    "dry-van": "dry van",
    "dryvan": "dry van",
    "van": "dry van",
    "reefer": "reefer",
    "refrigerated": "reefer",
    "refrigerated van": "reefer",
    "flatbed": "flatbed",
    "flat bed": "flatbed",
    "flat-bed": "flatbed",
}

BENCHMARK_SOURCE = (
    "DAT national spot averages, linehaul plus fuel surcharge, "
    "week of Oct 24-30, 2026 (reported by The Trucker, 2026-11-04)"
)


class LoadError(Exception):
    """A load entry that cannot be evaluated."""


def money(value):
    """Round a Decimal to cents, half up."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def rate(value):
    """Round a per-mile rate to cents, half up."""
    return value.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def to_decimal(value, field, load_id):
    """Convert a JSON number or numeric string to Decimal."""
    if isinstance(value, bool):
        raise LoadError("load %s: %s must be a number, got %r"
                        % (load_id, field, value))
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            raise LoadError("load %s: %s is not a number: %r"
                            % (load_id, field, value))
    if isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
        if not text:
            raise LoadError("load %s: %s is empty" % (load_id, field))
        try:
            return Decimal(text)
        except InvalidOperation:
            raise LoadError("load %s: %s is not a number: %r"
                            % (load_id, field, value))
    raise LoadError("load %s: %s must be a number, got %r"
                    % (load_id, field, value))


def normalize_equipment(value, load_id):
    """Map a free-text equipment value to a canonical benchmark key."""
    if not isinstance(value, str) or not value.strip():
        raise LoadError("load %s: equipment is missing" % load_id)
    key = " ".join(value.strip().lower().split())
    canonical = EQUIPMENT_ALIASES.get(key)
    if canonical is None:
        raise LoadError(
            "load %s: unknown equipment %r (expected dry van, reefer, "
            "or flatbed)" % (load_id, value))
    return canonical


def parse_loads(data):
    """Validate a parsed JSON document into a list of load dicts.

    Accepts a bare list or an object with a "loads" list. Returns a
    list of normalized load dicts, raising LoadError on structural
    problems.
    """
    if isinstance(data, dict):
        if "loads" not in data:
            raise LoadError("input object must have a \"loads\" list")
        data = data["loads"]
    if not isinstance(data, list):
        raise LoadError("input must be a JSON list of loads, or an "
                        "object with a \"loads\" list")
    if not data:
        raise LoadError("input contains no loads")
    seen_ids = set()
    loads = []
    for index, raw in enumerate(data):
        label = "at index %d" % index
        if not isinstance(raw, dict):
            raise LoadError("load %s: each load must be an object"
                            % label)
        load_id = (raw.get("id") or raw.get("load_id")
                   or raw.get("load_number"))
        if load_id is None or (isinstance(load_id, str)
                               and not load_id.strip()):
            raise LoadError("load %s: missing id (id, load_id, or "
                            "load_number)" % label)
        load_id = str(load_id).strip()
        if load_id in seen_ids:
            raise LoadError("load %s: duplicate id" % load_id)
        seen_ids.add(load_id)
        if "loaded_miles" not in raw:
            raise LoadError("load %s: missing loaded_miles" % load_id)
        if "gross_pay" not in raw:
            raise LoadError("load %s: missing gross_pay" % load_id)
        if "equipment" not in raw:
            raise LoadError("load %s: missing equipment" % load_id)
        loaded = to_decimal(raw["loaded_miles"], "loaded_miles", load_id)
        if loaded <= 0:
            raise LoadError("load %s: loaded_miles must be above 0, "
                            "got %s" % (load_id, loaded))
        deadhead = Decimal("0")
        if raw.get("deadhead_miles") is not None:
            deadhead = to_decimal(raw["deadhead_miles"],
                                  "deadhead_miles", load_id)
        if deadhead < 0:
            raise LoadError("load %s: deadhead_miles cannot be "
                            "negative, got %s" % (load_id, deadhead))
        gross = to_decimal(raw["gross_pay"], "gross_pay", load_id)
        if gross < 0:
            raise LoadError("load %s: gross_pay cannot be negative, "
                            "got %s" % (load_id, gross))
        equipment = normalize_equipment(raw["equipment"], load_id)
        lane = raw.get("lane")
        if lane is None:
            origin = raw.get("origin", "")
            destination = raw.get("destination", "")
            if origin or destination:
                lane = "%s to %s" % (origin, destination)
        loads.append({
            "id": load_id,
            "lane": lane if isinstance(lane, str) else None,
            "equipment": equipment,
            "loaded_miles": loaded,
            "deadhead_miles": deadhead,
            "gross_pay": money(gross),
        })
    return loads


def evaluate_load(load, benchmarks):
    """Score one load against its equipment benchmark."""
    loaded = load["loaded_miles"]
    total = loaded + load["deadhead_miles"]
    gross = load["gross_pay"]
    benchmark = benchmarks[load["equipment"]]
    per_loaded = rate(gross / loaded)
    per_total = rate(gross / total)
    diff = rate(per_total - benchmark)
    below = per_total < benchmark
    shortfall = Decimal("0.00")
    if below:
        # Use the unrounded rate so the shortfall is exact:
        # benchmark x total miles - gross pay.
        shortfall = money(benchmark * total - gross)
    return {
        "id": load["id"],
        "lane": load["lane"],
        "equipment": load["equipment"],
        "loaded_miles": str(loaded),
        "deadhead_miles": str(load["deadhead_miles"]),
        "total_miles": str(total),
        "gross_pay": str(money(gross)),
        "rate_per_loaded_mile": str(per_loaded),
        "rate_per_total_mile": str(per_total),
        "benchmark": str(benchmark),
        "difference_per_mile": str(diff),
        "shortfall": str(shortfall),
        "verdict": "BELOW" if below else "ABOVE",
    }


def summarize(results):
    """Build summary counts and averages from evaluated loads."""
    total = len(results)
    above = sum(1 for r in results if r["verdict"] == "ABOVE")
    below = total - above
    below_rows = [r for r in results if r["verdict"] == "BELOW"]
    total_shortfall = sum((Decimal(r["shortfall"]) for r in below_rows),
                          Decimal("0.00"))
    average_shortfall = Decimal("0.00")
    if below_rows:
        average_shortfall = money(total_shortfall / len(below_rows))
    average_per_total = Decimal("0.00")
    average_per_loaded = Decimal("0.00")
    if results:
        average_per_total = rate(sum(
            (Decimal(r["rate_per_total_mile"]) for r in results),
            Decimal("0")) / total)
        average_per_loaded = rate(sum(
            (Decimal(r["rate_per_loaded_mile"]) for r in results),
            Decimal("0")) / total)
    best = None
    worst = None
    if results:
        best = max(results,
                   key=lambda r: Decimal(r["rate_per_total_mile"]))
        worst = min(results,
                    key=lambda r: Decimal(r["rate_per_total_mile"]))
    return {
        "total_loads": total,
        "above_benchmark": above,
        "below_benchmark": below,
        "average_rate_per_total_mile": str(average_per_total),
        "average_rate_per_loaded_mile": str(average_per_loaded),
        "total_shortfall": str(money(total_shortfall)),
        "average_shortfall_per_below_load": str(average_shortfall),
        "best_load": best["id"] if best else None,
        "best_rate_per_total_mile": (
            best["rate_per_total_mile"] if best else None),
        "worst_load": worst["id"] if worst else None,
        "worst_rate_per_total_mile": (
            worst["rate_per_total_mile"] if worst else None),
    }


def load_benchmarks(path, overrides):
    """Build the benchmark table from defaults, a file, and flags.

    The file is a JSON object mapping equipment names (or aliases)
    to per-mile rates. Flags are EQUIPMENT=RATE pairs and win over
    the file. Every value must be a positive number.
    """
    benchmarks = dict(DEFAULT_BENCHMARKS)
    if path:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except OSError as exc:
            raise LoadError("cannot read benchmarks file %s: %s"
                            % (path, exc))
        except json.JSONDecodeError as exc:
            raise LoadError("benchmarks file %s is not valid JSON: %s"
                            % (path, exc))
        if not isinstance(data, dict):
            raise LoadError("benchmarks file must be a JSON object "
                            "mapping equipment to rates")
        for key, value in data.items():
            canonical = EQUIPMENT_ALIASES.get(
                " ".join(str(key).strip().lower().split()))
            if canonical is None:
                raise LoadError("benchmarks file: unknown equipment "
                                "%r" % (key,))
            benchmarks[canonical] = to_decimal(value, "benchmark",
                                               str(key))
    for override in overrides or []:
        if "=" not in override:
            raise LoadError("--benchmark must be EQUIPMENT=RATE, got "
                            "%r" % (override,))
        name, value = override.split("=", 1)
        canonical = EQUIPMENT_ALIASES.get(
            " ".join(name.strip().lower().split()))
        if canonical is None:
            raise LoadError("--benchmark: unknown equipment %r"
                            % (name,))
        benchmarks[canonical] = to_decimal(value, "benchmark", name)
    for equipment, value in benchmarks.items():
        if value <= 0:
            raise LoadError("benchmark for %s must be above 0, got %s"
                            % (equipment, value))
    return benchmarks


def format_text(results, summary, benchmarks):
    """Render the human-readable report."""
    lines = []
    lines.append("Rate per mile vs DAT national spot benchmarks")
    bench_text = ", ".join(
        "%s $%s" % (name, benchmarks[name])
        for name in ("dry van", "reefer", "flatbed"))
    lines.append("Benchmarks: %s per mile" % bench_text)
    lines.append("Source: %s" % BENCHMARK_SOURCE)
    lines.append("")
    header = ("%-8s %-9s %7s %9s %7s %11s %9s %9s %10s %9s  %s"
              % ("ID", "Equipment", "Loaded", "Deadhead", "Total",
                 "Gross pay", "$/loaded", "$/total", "Benchmark",
                 "Diff/mi", "Verdict"))
    lines.append(header)
    lines.append("-" * len(header))
    for row in results:
        diff = Decimal(row["difference_per_mile"])
        diff_text = ("+$%s" % diff) if diff >= 0 else ("-$%s" % abs(diff))
        lines.append(
            "%-8s %-9s %7s %9s %7s %11s %9s %9s %10s %9s  %s"
            % (row["id"], row["equipment"], row["loaded_miles"],
               row["deadhead_miles"], row["total_miles"],
               "$%s" % row["gross_pay"],
               "$%s" % row["rate_per_loaded_mile"],
               "$%s" % row["rate_per_total_mile"],
               "$%s" % row["benchmark"], diff_text, row["verdict"]))
    lines.append("")
    lines.append("Summary: %d loads, %d ABOVE benchmark, %d BELOW "
                 "benchmark" % (summary["total_loads"],
                                summary["above_benchmark"],
                                summary["below_benchmark"]))
    lines.append("Average rate per total mile: $%s"
                 % summary["average_rate_per_total_mile"])
    lines.append("Average rate per loaded mile: $%s"
                 % summary["average_rate_per_loaded_mile"])
    if summary["below_benchmark"]:
        lines.append("Average shortfall per below-benchmark load: $%s "
                     "(total $%s)"
                     % (summary["average_shortfall_per_below_load"],
                        summary["total_shortfall"]))
    else:
        lines.append("No load is below benchmark. Total shortfall: $0.00")
    lines.append("Best rate per total mile: %s at $%s"
                 % (summary["best_load"],
                    summary["best_rate_per_total_mile"]))
    lines.append("Worst rate per total mile: %s at $%s"
                 % (summary["worst_load"],
                    summary["worst_rate_per_total_mile"]))
    return "\n".join(lines) + "\n"


def build_report(loads, benchmarks):
    """Evaluate loads and return (results, summary)."""
    results = [evaluate_load(load, benchmarks) for load in loads]
    return results, summarize(results)


def run(argv=None):
    """Entry point used by the CLI and the tests. Returns exit code."""
    parser = argparse.ArgumentParser(
        prog="rate-per-mile-doctor",
        description="Compare truck loads against DAT national spot "
                    "benchmarks by equipment type, with deadhead-"
                    "adjusted rates.")
    parser.add_argument("input", help="JSON file with a list of loads")
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when any load is below benchmark")
    parser.add_argument("--equipment",
                        choices=["dry van", "reefer", "flatbed"],
                        help="only evaluate loads of this equipment type")
    parser.add_argument("--benchmarks", metavar="FILE",
                        help="JSON file overriding benchmark rates")
    parser.add_argument("--benchmark", action="append", default=[],
                        metavar="EQUIPMENT=RATE",
                        help="override one benchmark rate, repeatable")
    parser.add_argument("--out", metavar="FILE",
                        help="also write the report to this file")
    parser.add_argument("--version", action="version",
                        version="rate-per-mile-doctor " + __version__)
    args = parser.parse_args(argv)

    try:
        benchmarks = load_benchmarks(args.benchmarks, args.benchmark)
        try:
            with open(args.input, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except OSError as exc:
            raise LoadError("cannot read input file %s: %s"
                            % (args.input, exc))
        except json.JSONDecodeError as exc:
            raise LoadError("input file %s is not valid JSON: %s"
                            % (args.input, exc))
        loads = parse_loads(data)
    except LoadError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    if args.equipment:
        loads = [load for load in loads
                 if load["equipment"] == args.equipment]
        if not loads:
            print("error: no %s loads in %s"
                  % (args.equipment, args.input), file=sys.stderr)
            return 2

    results, summary = build_report(loads, benchmarks)
    report = {
        "benchmarks": {name: str(benchmarks[name])
                       for name in ("dry van", "reefer", "flatbed")},
        "benchmark_source": BENCHMARK_SOURCE,
        "loads": results,
        "summary": summary,
    }
    if args.json:
        text = json.dumps(report, indent=2) + "\n"
    else:
        text = format_text(results, summary, benchmarks)
    print(text, end="")
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as exc:
            print("error: cannot write %s: %s" % (args.out, exc),
                  file=sys.stderr)
            return 2
    if args.check and summary["below_benchmark"]:
        return 1
    return 0


def main_entry():
    """Console script entry point."""
    sys.exit(run())


if __name__ == "__main__":
    main_entry()
