import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import perf_trace


class PerfTraceLifecycleTests(unittest.TestCase):
    def setUp(self):
        # Start from a clean module state each test — `perf_trace` is
        # a process-global singleton and tests run in the same process.
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()
        self.tmp = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmp, "perf.jsonl")
        self.summary_path = os.path.join(self.tmp, "summary.txt")

    def tearDown(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()

    def test_disabled_by_default(self):
        self.assertFalse(perf_trace.is_enabled())

    def test_enable_sets_paths(self):
        perf_trace.enable(self.log_path, session_label="unit", summary_path=self.summary_path)
        self.assertTrue(perf_trace.is_enabled())
        self.assertEqual(perf_trace.log_path(), self.log_path)
        self.assertEqual(perf_trace.summary_path(), self.summary_path)

    def test_span_no_op_when_disabled(self):
        with perf_trace.span("some.event", foo="bar"):
            pass
        perf_trace.stamp("other.event")
        self.assertEqual(perf_trace.recorded_events(), [])

    def test_span_records_duration(self):
        perf_trace.enable(self.log_path, session_label="unit", summary_path=self.summary_path)
        with perf_trace.span("parsers.parse_all_files", files=7):
            time.sleep(0.01)
        events = perf_trace.recorded_events()
        spans = [e for e in events if e.get("kind") == "span"]
        self.assertEqual(len(spans), 1)
        row = spans[0]
        self.assertEqual(row["event"], "parsers.parse_all_files")
        self.assertEqual(row["files"], 7)
        self.assertGreaterEqual(row["duration_ms"], 5)  # ~10ms, give slack

    def test_stamp_records_event_without_duration(self):
        perf_trace.enable(self.log_path, summary_path=self.summary_path)
        perf_trace.stamp("notebook.tab_switch", old="Load", new="Bulk")
        stamps = [e for e in perf_trace.recorded_events() if e.get("kind") == "stamp"]
        self.assertEqual(len(stamps), 1)
        self.assertEqual(stamps[0]["event"], "notebook.tab_switch")
        self.assertEqual(stamps[0]["old"], "Load")
        self.assertEqual(stamps[0]["new"], "Bulk")
        self.assertNotIn("duration_ms", stamps[0])

    def test_jsonl_file_appends_one_row_per_event(self):
        perf_trace.enable(self.log_path, summary_path=self.summary_path)
        with perf_trace.span("a"):
            pass
        perf_trace.stamp("b")
        with perf_trace.span("c"):
            pass
        with open(self.log_path, "r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        # enable marker + 2 span_start + 2 span + 1 stamp = 5 events.
        # The "perf_trace.disabled" marker only appears after disable().
        # Filter to user-visible events.
        event_rows = [r for r in lines if r.get("event") not in ("perf_trace.enabled", "perf_trace.disabled")]
        # Three user events (two spans completed + one stamp); spans
        # also emit a span_start breadcrumb so we can diagnose crashes.
        completed = [r for r in event_rows if r.get("kind") in ("span", "stamp")]
        self.assertEqual([r["event"] for r in completed], ["a", "b", "c"])
        started = [r for r in event_rows if r.get("kind") == "span_start"]
        self.assertEqual([r["event"] for r in started], ["a", "c"])

    def test_disable_writes_summary_report(self):
        perf_trace.enable(self.log_path, summary_path=self.summary_path)
        with perf_trace.span("parsers.parse"):
            time.sleep(0.005)
        with perf_trace.span("ui_bulk.filter"):
            time.sleep(0.005)
        returned = perf_trace.disable(write_summary=True)
        self.assertEqual(returned, self.summary_path)
        self.assertTrue(os.path.exists(self.summary_path))
        text = Path(self.summary_path).read_text(encoding="utf-8")
        self.assertIn("parsers.parse", text)
        self.assertIn("ui_bulk.filter", text)
        self.assertIn("Top 10 slowest individual events", text)


class CrashDiagnosisBreadcrumbTests(unittest.TestCase):
    """The span_start breadcrumb must land on disk even when the
    enclosed block raises — that's the whole point of the feature.
    """

    def setUp(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()
        self.tmp = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmp, "p.jsonl")
        perf_trace.enable(self.log_path, summary_path=os.path.join(self.tmp, "p.txt"))

    def tearDown(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()

    def test_span_start_written_before_exception_inside_block(self):
        with self.assertRaises(RuntimeError):
            with perf_trace.span("boom.event", phase="parse"):
                raise RuntimeError("simulated crash")
        with open(self.log_path, "r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        starts = [r for r in lines if r.get("kind") == "span_start" and r.get("event") == "boom.event"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]["phase"], "parse")
        # The completion `span` row should also appear — `span` uses
        # try/finally so the exception doesn't prevent the finally
        # block from writing the duration row.
        spans = [r for r in lines if r.get("kind") == "span" and r.get("event") == "boom.event"]
        self.assertEqual(len(spans), 1)

    def test_span_start_allows_crash_diagnosis_without_completion_row(self):
        """Simulate the scenario where the process is killed mid-span
        by writing only the start marker and asserting summarize_events
        ignores orphaned starts.
        """
        # Manually write a span_start to the ring as if the process
        # crashed before the finally block could run.
        orphan_start = {
            "event": "parsers.parse_detailed_pair_aggregates",
            "ts": "2026-04-08T20:15:10.000",
            "session_label": "crash",
            "kind": "span_start",
        }
        with open(self.log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(orphan_start) + "\n")
        # summarize_events should skip span_start rows entirely
        rows = [orphan_start]
        summary = perf_trace.summarize_events(rows)
        self.assertEqual(summary, [])


class SummarizeEventsTests(unittest.TestCase):
    def _span(self, event, duration_ms):
        return {"event": event, "kind": "span", "duration_ms": duration_ms, "ts": "2026-04-08"}

    def _aggregate(self, event, count, total_ms, max_ms):
        return {
            "event": event, "kind": "aggregate",
            "count": count, "total_ms": total_ms, "max_ms": max_ms,
            "ts": "2026-04-08",
        }

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(perf_trace.summarize_events([]), [])

    def test_single_span_has_count_1_and_percentiles_match_the_value(self):
        result = perf_trace.summarize_events([self._span("a", 42.0)])
        self.assertEqual(len(result), 1)
        row = result[0]
        self.assertEqual(row["event"], "a")
        self.assertEqual(row["count"], 1)
        self.assertEqual(row["total_ms"], 42.0)
        self.assertEqual(row["avg_ms"], 42.0)
        self.assertEqual(row["min_ms"], 42.0)
        self.assertEqual(row["max_ms"], 42.0)
        self.assertEqual(row["p50_ms"], 42.0)
        self.assertEqual(row["p95_ms"], 42.0)
        self.assertEqual(row["p99_ms"], 42.0)

    def test_groups_by_event_name(self):
        events = [
            self._span("a", 10.0),
            self._span("a", 20.0),
            self._span("a", 30.0),
            self._span("b", 5.0),
        ]
        result = {row["event"]: row for row in perf_trace.summarize_events(events)}
        self.assertEqual(result["a"]["count"], 3)
        self.assertEqual(result["a"]["total_ms"], 60.0)
        self.assertEqual(result["a"]["avg_ms"], 20.0)
        self.assertEqual(result["a"]["min_ms"], 10.0)
        self.assertEqual(result["a"]["max_ms"], 30.0)
        self.assertEqual(result["b"]["count"], 1)

    def test_sorted_by_total_ms_descending(self):
        events = [
            self._span("small", 1.0),
            self._span("big", 100.0),
            self._span("medium", 10.0),
        ]
        result = [row["event"] for row in perf_trace.summarize_events(events)]
        self.assertEqual(result, ["big", "medium", "small"])

    def test_aggregate_rows_roll_up_separately(self):
        events = [
            self._span("a", 100.0),
            self._aggregate("enrich", count=1000, total_ms=50.0, max_ms=0.5),
            self._aggregate("enrich", count=500,  total_ms=25.0, max_ms=0.6),
        ]
        rows = {row["event"]: row for row in perf_trace.summarize_events(events)}
        self.assertIn("a", rows)
        self.assertIn("enrich", rows)
        self.assertEqual(rows["enrich"]["kind"], "aggregate")
        self.assertEqual(rows["enrich"]["count"], 1500)
        self.assertEqual(rows["enrich"]["total_ms"], 75.0)
        self.assertEqual(rows["enrich"]["max_ms"], 0.6)

    def test_p95_picks_near_top(self):
        # 100 samples with one dominant outlier — p95 should land on
        # the upper tail, not the median.
        events = [self._span("e", float(i)) for i in range(100)]
        row = perf_trace.summarize_events(events)[0]
        self.assertGreaterEqual(row["p95_ms"], 94.0)
        self.assertLessEqual(row["p95_ms"], 95.0)
        self.assertAlmostEqual(row["p50_ms"], 50.0, delta=1.0)

    def test_ignores_malformed_rows(self):
        events = [
            "not a dict",
            {"event": "good", "kind": "span", "duration_ms": 5.0},
            {"kind": "span", "duration_ms": 5.0},  # no event name
            {"event": "x", "kind": "stamp"},  # stamps don't get timed
        ]
        result = perf_trace.summarize_events(events)
        names = [row["event"] for row in result]
        self.assertEqual(names, ["good"])


class TopSlowestTests(unittest.TestCase):
    def test_returns_spans_sorted_by_duration_descending(self):
        events = [
            {"event": "a", "kind": "span", "duration_ms": 10, "ts": "t"},
            {"event": "b", "kind": "span", "duration_ms": 500, "ts": "t"},
            {"event": "c", "kind": "span", "duration_ms": 50, "ts": "t"},
        ]
        result = perf_trace.top_slowest(events, limit=2)
        self.assertEqual([row["event"] for row in result], ["b", "c"])

    def test_skips_non_span_rows(self):
        events = [
            {"event": "a", "kind": "stamp"},
            {"event": "b", "kind": "span", "duration_ms": 1.0, "ts": "t"},
        ]
        result = perf_trace.top_slowest(events, limit=5)
        self.assertEqual([row["event"] for row in result], ["b"])


class AggregateSpanTests(unittest.TestCase):
    def setUp(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()
        self.tmp = tempfile.mkdtemp()
        perf_trace.enable(
            os.path.join(self.tmp, "p.jsonl"),
            summary_path=os.path.join(self.tmp, "p.txt"),
        )

    def tearDown(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()

    def test_aggregate_span_does_not_emit_per_call_rows(self):
        for _ in range(1000):
            with perf_trace.aggregate_span("rules.enrich_item"):
                pass
        before_flush = [e for e in perf_trace.recorded_events() if e.get("event") == "rules.enrich_item"]
        self.assertEqual(before_flush, [])

    def test_flush_aggregate_emits_single_summary_row(self):
        for _ in range(100):
            with perf_trace.aggregate_span("rules.enrich_item"):
                pass
        perf_trace.flush_aggregate("rules.enrich_item")
        rows = [e for e in perf_trace.recorded_events() if e.get("event") == "rules.enrich_item"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "aggregate")
        self.assertEqual(rows[0]["count"], 100)
        self.assertGreaterEqual(rows[0]["total_ms"], 0)

    def test_flush_aggregate_is_idempotent(self):
        with perf_trace.aggregate_span("a"):
            pass
        perf_trace.flush_aggregate("a")
        perf_trace.flush_aggregate("a")  # no-op
        rows = [e for e in perf_trace.recorded_events() if e.get("event") == "a"]
        self.assertEqual(len(rows), 1)


class FormatSummaryReportTests(unittest.TestCase):
    def test_summary_contains_headline_sections(self):
        events = [
            {"event": "parsers.parse_all_files", "kind": "span", "duration_ms": 18_000.0, "ts": "2026-04-08T10:00:00.000"},
            {"event": "ui_bulk.apply_bulk_filter", "kind": "span", "duration_ms": 300.0, "ts": "2026-04-08T10:01:00.000"},
            {"event": "ui_bulk.apply_bulk_filter", "kind": "span", "duration_ms": 50.0, "ts": "2026-04-08T10:01:05.000"},
        ]
        text = perf_trace.format_summary_report(events)
        self.assertIn("PO Builder Perf Summary", text)
        self.assertIn("parsers.parse_all_files", text)
        self.assertIn("ui_bulk.apply_bulk_filter", text)
        self.assertIn("Top 10 slowest", text)


class TimedDecoratorTests(unittest.TestCase):
    def setUp(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()
        self.tmp = tempfile.mkdtemp()
        perf_trace.enable(
            os.path.join(self.tmp, "p.jsonl"),
            summary_path=os.path.join(self.tmp, "p.txt"),
        )

    def tearDown(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()

    def test_timed_decorator_records_a_span(self):
        @perf_trace.timed("my.func")
        def do_work(x):
            return x * 2

        self.assertEqual(do_work(21), 42)
        spans = [e for e in perf_trace.recorded_events() if e.get("kind") == "span"]
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["event"], "my.func")


class MaybeAutoEnableTests(unittest.TestCase):
    def setUp(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()

    def tearDown(self):
        perf_trace.disable(write_summary=False)
        perf_trace.clear_ring_buffer()
        os.environ.pop("DEBUG_PERF", None)

    def test_maybe_auto_enable_respects_debug_perf_env(self):
        os.environ["DEBUG_PERF"] = "1"
        perf_trace.maybe_auto_enable()
        self.assertTrue(perf_trace.is_enabled())

    def test_maybe_auto_enable_no_op_when_env_unset(self):
        perf_trace.maybe_auto_enable()
        self.assertFalse(perf_trace.is_enabled())


if __name__ == "__main__":
    unittest.main()
