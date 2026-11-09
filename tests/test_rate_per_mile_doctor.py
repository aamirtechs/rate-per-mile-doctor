"""Tests for rate_per_mile_doctor."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rate_per_mile_doctor as rpm


def make_load(**overrides):
    load = {
        "id": "L-1",
        "lane": "Dallas, TX to Oklahoma City, OK",
        "equipment": "dry van",
        "loaded_miles": 500,
        "deadhead_miles": 60,
        "gross_pay": 2400,
    }
    load.update(overrides)
    return load


class TestRateMath(unittest.TestCase):
    def test_rate_per_loaded_and_total_mile(self):
        load = rpm.parse_loads([make_load()])[0]
        result = rpm.evaluate_load(load, rpm.DEFAULT_BENCHMARKS)
        self.assertEqual(result["rate_per_loaded_mile"], "4.80")
        self.assertEqual(result["rate_per_total_mile"], "4.29")
        self.assertEqual(result["total_miles"], "560")
        self.assertEqual(result["verdict"], "ABOVE")
        self.assertEqual(result["difference_per_mile"], "1.22")
        self.assertEqual(result["shortfall"], "0.00")

    def test_deadhead_turns_an_above_load_below(self):
        # $2.88 per loaded mile looks close to the $3.07 benchmark,
        # but 200 deadhead miles drag the total-mile rate to $2.30.
        load = rpm.parse_loads([make_load(
            id="L-2", loaded_miles=800, deadhead_miles=200,
            gross_pay=2300)])[0]
        result = rpm.evaluate_load(load, rpm.DEFAULT_BENCHMARKS)
        self.assertEqual(result["rate_per_loaded_mile"], "2.88")
        self.assertEqual(result["rate_per_total_mile"], "2.30")
        self.assertEqual(result["verdict"], "BELOW")
        self.assertEqual(result["difference_per_mile"], "-0.77")
        self.assertEqual(result["shortfall"], "770.00")

    def test_shortfall_is_exact_not_rounded_rate_based(self):
        # 2850 / 800 = 3.5625, rounded to 3.56. The exact shortfall
        # is 3.63 x 800 - 2850 = 54.00, not (3.63 - 3.56) x 800.
        load = rpm.parse_loads([make_load(
            id="L-3", equipment="reefer", loaded_miles=650,
            deadhead_miles=150, gross_pay=2850)])[0]
        result = rpm.evaluate_load(load, rpm.DEFAULT_BENCHMARKS)
        self.assertEqual(result["rate_per_total_mile"], "3.56")
        self.assertEqual(result["shortfall"], "54.00")

    def test_rate_exactly_at_benchmark_is_above(self):
        # 3.07 x 500 = 1535, so the total-mile rate is exactly the
        # dry van benchmark.
        load = rpm.parse_loads([make_load(
            loaded_miles=500, deadhead_miles=0,
            gross_pay=1535)])[0]
        result = rpm.evaluate_load(load, rpm.DEFAULT_BENCHMARKS)
        self.assertEqual(result["rate_per_total_mile"], "3.07")
        self.assertEqual(result["verdict"], "ABOVE")
        self.assertEqual(result["shortfall"], "0.00")

    def test_zero_deadhead_defaults(self):
        load = rpm.parse_loads([make_load(deadhead_miles=None)])[0]
        self.assertEqual(load["deadhead_miles"], Decimal("0"))
        load = rpm.parse_loads([{k: v for k, v in make_load().items()
                                 if k != "deadhead_miles"}])[0]
        self.assertEqual(load["deadhead_miles"], Decimal("0"))

    def test_cents_rounding_half_up(self):
        # 1000 / 333 = 3.003..., rounds to 3.00; 1001 / 333 = 3.006,
        # rounds to 3.01.
        load = rpm.parse_loads([make_load(
            loaded_miles=333, deadhead_miles=0, gross_pay=1001)])[0]
        result = rpm.evaluate_load(load, rpm.DEFAULT_BENCHMARKS)
        self.assertEqual(result["rate_per_loaded_mile"], "3.01")

    def test_each_equipment_uses_its_own_benchmark(self):
        for equipment, benchmark in (("dry van", "3.07"),
                                     ("reefer", "3.63"),
                                     ("flatbed", "3.62")):
            load = rpm.parse_loads([make_load(
                equipment=equipment, loaded_miles=100,
                deadhead_miles=0, gross_pay=300)])[0]
            result = rpm.evaluate_load(load, rpm.DEFAULT_BENCHMARKS)
            self.assertEqual(result["benchmark"], benchmark)
            self.assertEqual(result["rate_per_total_mile"], "3.00")
            self.assertEqual(result["verdict"], "BELOW")


class TestEquipmentNormalization(unittest.TestCase):
    def test_aliases_map_to_canonical_names(self):
        cases = {
            "Van": "dry van",
            "DRY-VAN": "dry van",
            "dryvan": "dry van",
            "Refrigerated": "reefer",
            "REFRIGERATED VAN": "reefer",
            "Flat Bed": "flatbed",
            "FLAT-BED": "flatbed",
        }
        for raw, expected in cases.items():
            load = rpm.parse_loads([make_load(equipment=raw)])[0]
            self.assertEqual(load["equipment"], expected)

    def test_unknown_equipment_is_a_data_error(self):
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([make_load(equipment="step deck")])
        self.assertIn("unknown equipment", str(ctx.exception))

    def test_missing_equipment_is_a_data_error(self):
        raw = make_load()
        del raw["equipment"]
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([raw])
        self.assertIn("missing equipment", str(ctx.exception))


class TestInputValidation(unittest.TestCase):
    def test_missing_loaded_miles(self):
        raw = make_load()
        del raw["loaded_miles"]
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([raw])
        self.assertIn("missing loaded_miles", str(ctx.exception))

    def test_missing_gross_pay(self):
        raw = make_load()
        del raw["gross_pay"]
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([raw])
        self.assertIn("missing gross_pay", str(ctx.exception))

    def test_missing_id(self):
        raw = make_load()
        del raw["id"]
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([raw])
        self.assertIn("missing id", str(ctx.exception))

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([make_load(), make_load(lane="Other")])
        self.assertIn("duplicate id", str(ctx.exception))

    def test_negative_deadhead_rejected(self):
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([make_load(deadhead_miles=-10)])
        self.assertIn("cannot be negative", str(ctx.exception))

    def test_negative_gross_pay_rejected(self):
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([make_load(gross_pay=-100)])
        self.assertIn("cannot be negative", str(ctx.exception))

    def test_zero_loaded_miles_rejected(self):
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([make_load(loaded_miles=0)])
        self.assertIn("above 0", str(ctx.exception))

    def test_negative_loaded_miles_rejected(self):
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([make_load(loaded_miles=-50)])
        self.assertIn("above 0", str(ctx.exception))

    def test_non_numeric_miles_rejected(self):
        with self.assertRaises(rpm.LoadError) as ctx:
            rpm.parse_loads([make_load(loaded_miles="five hundred")])
        self.assertIn("not a number", str(ctx.exception))

    def test_boolean_is_not_a_number(self):
        with self.assertRaises(rpm.LoadError):
            rpm.parse_loads([make_load(loaded_miles=True)])

    def test_string_numbers_and_dollar_signs_accepted(self):
        load = rpm.parse_loads([make_load(
            loaded_miles="500", gross_pay="$2,400.00")])[0]
        self.assertEqual(load["loaded_miles"], Decimal("500"))
        self.assertEqual(load["gross_pay"], Decimal("2400.00"))

    def test_object_with_loads_key_accepted(self):
        loads = rpm.parse_loads({"loads": [make_load()]})
        self.assertEqual(len(loads), 1)

    def test_object_without_loads_key_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.parse_loads({"trucks": [make_load()]})

    def test_non_list_input_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.parse_loads("not a list")

    def test_empty_list_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.parse_loads([])

    def test_non_object_load_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.parse_loads(["L-1"])

    def test_alternate_id_fields_accepted(self):
        load = rpm.parse_loads([make_load(load_id="X-9")])[0]
        self.assertEqual(load["id"], "L-1")
        raw = make_load()
        del raw["id"]
        raw["load_number"] = "N-77"
        load = rpm.parse_loads([raw])[0]
        self.assertEqual(load["id"], "N-77")

    def test_origin_and_destination_become_lane(self):
        raw = make_load()
        del raw["lane"]
        raw["origin"] = "Dallas, TX"
        raw["destination"] = "Austin, TX"
        load = rpm.parse_loads([raw])[0]
        self.assertEqual(load["lane"], "Dallas, TX to Austin, TX")


class TestSummary(unittest.TestCase):
    def _sample_results(self):
        loads = rpm.parse_loads([
            make_load(id="L-201", loaded_miles=500, deadhead_miles=60,
                      gross_pay=2400),
            make_load(id="L-202", equipment="dry van",
                      loaded_miles=800, deadhead_miles=200,
                      gross_pay=2300),
            make_load(id="L-203", equipment="reefer",
                      loaded_miles=650, deadhead_miles=150,
                      gross_pay=2850),
            make_load(id="L-204", equipment="flatbed",
                      loaded_miles=300, deadhead_miles=20,
                      gross_pay=1250),
            make_load(id="L-205", equipment="reefer",
                      loaded_miles=150, deadhead_miles=90,
                      gross_pay=500),
        ])
        return rpm.build_report(loads, rpm.DEFAULT_BENCHMARKS)

    def test_sample_summary_counts(self):
        _, summary = self._sample_results()
        self.assertEqual(summary["total_loads"], 5)
        self.assertEqual(summary["above_benchmark"], 2)
        self.assertEqual(summary["below_benchmark"], 3)

    def test_sample_summary_shortfall(self):
        _, summary = self._sample_results()
        self.assertEqual(summary["total_shortfall"], "1195.20")
        self.assertEqual(summary["average_shortfall_per_below_load"],
                         "398.40")

    def test_sample_summary_averages(self):
        _, summary = self._sample_results()
        self.assertEqual(summary["average_rate_per_total_mile"], "3.23")
        self.assertEqual(summary["average_rate_per_loaded_mile"], "3.91")

    def test_sample_summary_best_and_worst(self):
        _, summary = self._sample_results()
        self.assertEqual(summary["best_load"], "L-201")
        self.assertEqual(summary["best_rate_per_total_mile"], "4.29")
        self.assertEqual(summary["worst_load"], "L-205")
        self.assertEqual(summary["worst_rate_per_total_mile"], "2.08")

    def test_all_above_summary_has_zero_shortfall(self):
        loads = rpm.parse_loads([make_load()])
        _, summary = rpm.build_report(loads, rpm.DEFAULT_BENCHMARKS)
        self.assertEqual(summary["below_benchmark"], 0)
        self.assertEqual(summary["total_shortfall"], "0.00")
        self.assertEqual(summary["average_shortfall_per_below_load"],
                         "0.00")


class TestBenchmarkOverrides(unittest.TestCase):
    def test_flag_override_changes_verdict(self):
        loads = rpm.parse_loads([make_load(
            loaded_miles=800, deadhead_miles=200, gross_pay=2300)])
        benchmarks = rpm.load_benchmarks(None, ["dry van=2.20"])
        results, _ = rpm.build_report(loads, benchmarks)
        self.assertEqual(results[0]["benchmark"], "2.20")
        self.assertEqual(results[0]["verdict"], "ABOVE")

    def test_flag_override_alias_accepted(self):
        benchmarks = rpm.load_benchmarks(None, ["van=2.90"])
        self.assertEqual(benchmarks["dry van"], Decimal("2.90"))

    def test_flag_without_equals_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.load_benchmarks(None, ["dry van 2.90"])

    def test_flag_unknown_equipment_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.load_benchmarks(None, ["step deck=3.00"])

    def test_flag_zero_rate_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.load_benchmarks(None, ["reefer=0"])

    def test_file_override(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as handle:
            json.dump({"reefer": 3.40, "flatbed": 3.45,
                       "dry van": 2.90}, handle)
            path = handle.name
        try:
            benchmarks = rpm.load_benchmarks(path, [])
            self.assertEqual(benchmarks["reefer"], Decimal("3.4"))
            self.assertEqual(benchmarks["flatbed"], Decimal("3.45"))
            self.assertEqual(benchmarks["dry van"], Decimal("2.9"))
        finally:
            os.unlink(path)

    def test_file_unknown_equipment_rejected(self):
        with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False) as handle:
            json.dump({"tanker": 4.00}, handle)
            path = handle.name
        try:
            with self.assertRaises(rpm.LoadError):
                rpm.load_benchmarks(path, [])
        finally:
            os.unlink(path)

    def test_missing_benchmarks_file_rejected(self):
        with self.assertRaises(rpm.LoadError):
            rpm.load_benchmarks("/nonexistent/benchmarks.json", [])

    def test_defaults_unchanged_without_overrides(self):
        benchmarks = rpm.load_benchmarks(None, [])
        self.assertEqual(benchmarks, rpm.DEFAULT_BENCHMARKS)


class TestCli(unittest.TestCase):
    def _write_input(self, data):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False)
        json.dump(data, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def _run(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = rpm.run(argv)
        return code, buffer.getvalue()

    def test_text_output_contains_verdicts_and_summary(self):
        path = self._write_input([make_load()])
        code, text = self._run([path])
        self.assertEqual(code, 0)
        self.assertIn("L-1", text)
        self.assertIn("ABOVE", text)
        self.assertIn("Summary: 1 loads, 1 ABOVE benchmark, 0 BELOW",
                      text)

    def test_json_output_parses_and_matches(self):
        path = self._write_input([make_load()])
        code, text = self._run([path, "--json"])
        self.assertEqual(code, 0)
        report = json.loads(text)
        self.assertEqual(report["loads"][0]["verdict"], "ABOVE")
        self.assertEqual(report["summary"]["total_loads"], 1)
        self.assertEqual(report["benchmarks"]["dry van"], "3.07")

    def test_check_fails_when_any_load_below(self):
        path = self._write_input([make_load(
            loaded_miles=800, deadhead_miles=200, gross_pay=2300)])
        code, _ = self._run([path, "--check"])
        self.assertEqual(code, 1)

    def test_check_passes_when_all_above(self):
        path = self._write_input([make_load()])
        code, _ = self._run([path, "--check"])
        self.assertEqual(code, 0)

    def test_equipment_filter_keeps_only_matching_loads(self):
        path = self._write_input([
            make_load(id="L-1"),
            make_load(id="L-2", equipment="reefer", loaded_miles=650,
                      deadhead_miles=150, gross_pay=2850),
        ])
        code, text = self._run([path, "--equipment", "reefer"])
        self.assertEqual(code, 0)
        self.assertIn("L-2", text)
        self.assertNotIn("L-1", text)
        self.assertIn("Summary: 1 loads", text)

    def test_equipment_filter_with_no_match_is_an_error(self):
        path = self._write_input([make_load()])
        code, _ = self._run([path, "--equipment", "flatbed"])
        self.assertEqual(code, 2)

    def test_bad_input_exits_2_not_a_crash(self):
        path = self._write_input([make_load(deadhead_miles=-5)])
        code, _ = self._run([path])
        self.assertEqual(code, 2)

    def test_invalid_json_file_exits_2(self):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False)
        handle.write("{not json")
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        code, _ = self._run([handle.name])
        self.assertEqual(code, 2)

    def test_missing_input_file_exits_2(self):
        code, _ = self._run(["/nonexistent/loads.json"])
        self.assertEqual(code, 2)

    def test_out_file_writes_report(self):
        path = self._write_input([make_load()])
        out = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False)
        out.close()
        self.addCleanup(os.unlink, out.name)
        code, text = self._run([path, "--out", out.name])
        self.assertEqual(code, 0)
        with open(out.name, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), text)

    def test_text_output_mentions_benchmark_source(self):
        path = self._write_input([make_load()])
        _, text = self._run([path])
        self.assertIn("Oct 24-30, 2026", text)
        self.assertIn("dry van $3.07", text)


if __name__ == "__main__":
    unittest.main()
