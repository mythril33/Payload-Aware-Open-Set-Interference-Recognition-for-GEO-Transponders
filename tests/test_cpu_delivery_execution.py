"""Real subprocess checks for CPU restart/interrupt handling; standard library."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.cpu_delivery.execution import campaign_lock, run_step, termination_signals


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "campaign"
        self.out.mkdir()

    def step(self, code, **kwargs):
        return run_step(self.out, "test", [sys.executable, "-c", code],
                        cwd=ROOT, env=os.environ.copy(), timeout=5, **kwargs)

    def records(self):
        return [json.loads(line) for line in (self.out / "execution.jsonl").read_text().splitlines()]

    def test_success_and_resume_append_log_and_attempts(self):
        self.step("print('first')")
        self.step("print('second')", resume=True)
        rows = self.records()
        self.assertEqual([r["returncode"] for r in rows], [0, 0])
        self.assertEqual([r["resume"] for r in rows], [False, True])
        self.assertTrue(all(r["elapsed_s"] > 0 for r in rows))
        self.assertEqual((self.out / "test.log").read_text(), "first\nsecond\n")

    def test_nonzero_exit_is_recorded_and_refused(self):
        with self.assertRaisesRegex(RuntimeError, "campaign incomplete"):
            self.step("raise SystemExit(7)")
        row, = self.records()
        self.assertEqual(row["returncode"], 7)
        self.assertFalse(row["timed_out"])

    def test_spawn_failure_is_recorded_and_propagated(self):
        with self.assertRaises(FileNotFoundError):
            run_step(self.out, "test", [str(self.out / "no-such-executable")],
                     cwd=ROOT, env=os.environ.copy(), timeout=5)
        row, = self.records()
        self.assertEqual(row["error_type"], "FileNotFoundError")
        self.assertIsNone(row["returncode"])
        self.assertFalse(row["interrupted"])

    def test_interruption_is_recorded_before_propagating(self):
        with patch("research.cpu_delivery.execution.subprocess.Popen", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.step("pass")
        row, = self.records()
        self.assertTrue(row["interrupted"])
        self.assertEqual(row["error_type"], "KeyboardInterrupt")

    def contender(self, path):
        code = ("from research.cpu_delivery.execution import campaign_lock\n"
                f"with campaign_lock({str(path)!r}): print('acquired')\n")
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                              capture_output=True, text=True, timeout=5)

    def test_second_process_cannot_write_same_output_but_can_use_another(self):
        with campaign_lock(self.out):
            blocked = self.contender(self.out)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("already running", blocked.stderr)
            self.assertEqual(self.contender(self.out.with_name("another")).returncode, 0)
        self.assertEqual(self.contender(self.out).returncode, 0)

    def test_lock_released_after_exception_and_file_retained(self):
        with self.assertRaises(ValueError):
            with campaign_lock(self.out):
                raise ValueError("abort")
        self.assertTrue(self.out.with_name(".campaign.cpu-delivery.lock").exists())
        self.assertEqual(self.contender(self.out).returncode, 0)

    @unittest.skipUnless(os.name == "posix", "symlink output aliases on POSIX")
    def test_symlink_alias_cannot_bypass_lock(self):
        alias = self.out.with_name("alias")
        alias.symlink_to(self.out, target_is_directory=True)
        with campaign_lock(self.out):
            self.assertNotEqual(self.contender(alias).returncode, 0)

    def test_signal_handlers_restored_on_exception(self):
        before = signal.getsignal(signal.SIGTERM)
        with self.assertRaises(ValueError):
            with termination_signals():
                self.assertNotEqual(signal.getsignal(signal.SIGTERM), before)
                raise ValueError("abort")
        self.assertEqual(signal.getsignal(signal.SIGTERM), before)

    def child_code(self):
        # A genuine child + grandchild, both sleeping far beyond the deadline.
        return ("import os, subprocess, sys, time\nfrom pathlib import Path\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                f"Path({str(self.out / 'pids.json')!r}).write_text(__import__('json').dumps([os.getpid(), child.pid]))\n"
                "time.sleep(60)\n")

    def wait_ready(self, process):
        deadline = time.monotonic() + 5
        while not (self.out / "pids.json").exists():
            if process.poll() is not None or time.monotonic() > deadline:
                self.fail("child did not become ready")
            time.sleep(0.02)

    def assert_children_stopped(self):
        for pid in json.loads((self.out / "pids.json").read_text()):
            # An adopted zombie is stopped, awaiting the host's init reaper.
            stat = Path(f"/proc/{pid}/stat")
            deadline = time.monotonic() + 3
            while stat.exists():
                try:
                    if stat.read_text().rsplit(") ", 1)[1].split()[0] == "Z":
                        break
                except FileNotFoundError:
                    break
                if time.monotonic() > deadline:
                    self.fail(f"descendant {pid} still running")
                time.sleep(0.02)

    @unittest.skipUnless(sys.platform == "linux", "Linux process-state inspection")
    def test_timeout_kills_child_and_grandchild(self):
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            run_step(self.out, "test", [sys.executable, "-c", self.child_code()],
                     cwd=ROOT, env=os.environ.copy(), timeout=1)
        self.assert_children_stopped()
        row, = self.records()
        self.assertTrue(row["timed_out"])
        self.assertEqual(row["returncode"], -signal.SIGKILL)

    @unittest.skipUnless(sys.platform == "linux", "Linux process-state inspection")
    def test_ctrl_c_term_hup_clean_children_record_attempt_and_release_lock(self):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=sig):
                (self.out / "pids.json").unlink(missing_ok=True)
                command = [sys.executable, "-c", self.child_code()]
                code = ("import os\nfrom research.cpu_delivery.execution import *\n"
                        f"with termination_signals(), campaign_lock({str(self.out)!r}):\n"
                        f"    run_step({str(self.out)!r}, 'test', {command!r}, cwd={str(ROOT)!r}, env=os.environ.copy(), timeout=20)\n")
                process = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    self.wait_ready(process)
                    process.send_signal(sig)
                    self.assertNotEqual(process.wait(timeout=5), 0)
                    self.assert_children_stopped()
                    self.assertTrue(self.records()[-1]["interrupted"])
                    self.assertEqual(self.contender(self.out).returncode, 0)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()

    def test_runner_stops_after_failed_step_without_aggregating(self):
        from research.cpu_delivery import run
        cfg = {"groups_per_source_split": 40, "unknown_groups": 40,
               "unknown_first_seed": 900000, "training_seeds": [0, 1, 2]}
        with patch.object(run, "prepare", return_value=(cfg, self.out)), \
                patch.object(run, "run_step", side_effect=RuntimeError("failed")) as step, \
                patch("research.cpu_delivery.summarize.summarize") as aggregate:
            with self.assertRaisesRegex(RuntimeError, "failed"):
                run.run(self.out, resume=True)
            self.assertEqual(step.call_count, 1)
            aggregate.assert_not_called()

    def test_runner_refuses_in_repository_output_before_taking_lock(self):
        from research.cpu_delivery import run
        with patch.object(run, "campaign_lock") as lock:
            with self.assertRaisesRegex(ValueError, "outside"):
                run.run(ROOT / "bad-output")
            lock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
