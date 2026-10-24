"""
Executor module for parallel simulation execution.
"""

import logging
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from .config import RegressionConfig
from .case_parser import TestCase
from .compiler import Compiler
from .result_checker import ResultChecker, CheckResult
from .status_tracker import StatusTracker
from .utils import format_duration


def case_identity(case: TestCase) -> str:
    """Build a unique, human-readable key for a test case.

    Entries may share the same UVM test name (tc) and differ only by mode or
    by extra make arguments (e.g. sc=<C case> for SoC regressions). Using tc
    alone as the results-dictionary key silently collapses those entries, so
    the summary/HTML report undercounts. Include mode and extra args here.
    """
    extra = " ".join(
        f"{k}={v}" for k, v in sorted(case.extra_args.items()) if str(v).strip()
    )
    return f"{case.tc} [{case.mode}]" + (f" {extra}" if extra else "")


@dataclass
class RunResult:
    """Result of a single simulation run.

    Attributes:
        tc: Test case name
        mode: Simulation mode
        run_id: Run number (1-indexed within times)
        seed: Random seed used
        passed: Whether the run passed
        exit_code: Process exit code
        log_path: Path to simulation log
        duration: Run duration in seconds
        error_message: Error message if failed
        retry_count: Number of retries attempted
        uvm_summary: UVM report summary if available
    """
    tc: str
    mode: str
    run_id: int
    seed: int
    passed: bool = False
    exit_code: int = -1
    log_path: str = ""
    duration: float = 0.0
    error_message: str = ""
    retry_count: int = 0
    uvm_summary: Optional[dict] = None


@dataclass
class CaseResult:
    """Result of all runs for a test case.

    Attributes:
        tc: Test case name
        mode: Simulation mode
        times: Number of runs
        runs: List of RunResult objects
        passed: Whether the case passed (all runs passed)
        pass_count: Number of passed runs
        fail_count: Number of failed runs
    """
    tc: str
    mode: str
    times: int
    runs: List[RunResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Check if all runs passed."""
        return all(run.passed for run in self.runs)

    @property
    def pass_count(self) -> int:
        """Count of passed runs."""
        return sum(1 for run in self.runs if run.passed)

    @property
    def fail_count(self) -> int:
        """Count of failed runs."""
        return sum(1 for run in self.runs if not run.passed)


class Executor:
    """Executor for parallel simulation runs.

    Handles:
    - Parallel execution of test cases
    - Seed generation
    - Timeout management
    - Retry mechanism
    """

    def __init__(self, config: RegressionConfig, compiler: Compiler,
                 result_dir: str, timestamp: str,
                 status_tracker: Optional[StatusTracker] = None):
        """Initialize executor.

        Args:
            config: Regression configuration
            compiler: Compiler instance
            result_dir: Base result directory
            timestamp: Regression timestamp
            status_tracker: Optional status tracker instance
        """
        self.config = config
        self.compiler = compiler
        self.result_dir = result_dir
        self.timestamp = timestamp
        self.status_tracker = status_tracker

        # Initialize result checker
        self.checker = ResultChecker(
            fail_keywords=config.fail_keywords,
            pass_keywords=config.pass_keywords
        )

        # Progress tracking
        self._lock = threading.Lock()
        self._completed_count = 0
        self._total_count = 0
        self._start_time = None
        self._last_progress_time = None

        # Stop event for graceful shutdown
        self._stop_event = threading.Event()

        # Track running processes for cleanup
        self._running_processes: Set[subprocess.Popen] = set()
        self._process_lock = threading.Lock()

        self.logger = logging.getLogger("regr")
        self._running_futures: Dict[Future, TestCase] = {}

    def _generate_seed(self, case: TestCase, run_id: int) -> int:
        """Generate a unique seed for a run.

        Args:
            case: TestCase object
            run_id: Run number

        Returns:
            Seed value
        """
        if case.seed is not None:
            # Use specified seed
            return case.seed

        # Generate seed based on timestamp and run_id
        base = int(datetime.now().timestamp() * 1000)
        return (base + hash(case.tc) + run_id) % (2**31 - 1)

    def _get_run_result_dir(self, mode: str) -> str:
        """Get result directory for a mode.

        Simplified directory structure: result_dir/mode

        Args:
            mode: Simulation mode

        Returns:
            Result directory path
        """
        return os.path.join(self.result_dir, mode)

    def _get_log_path(self, tc: str, mode: str, seed: int, run_id: int) -> str:
        """Get log file path for a run.

        Args:
            tc: Test case name
            mode: Simulation mode
            seed: Random seed
            run_id: Run number

        Returns:
            Log file path
        """
        result_dir = self._get_run_result_dir(mode)
        # Log format matches Makefile: $(tc)_$(seed).log
        return os.path.join(result_dir, f"{tc}_{seed}.log")

    def build_sim_command(self, case: TestCase, seed: int, result_dir: str = "") -> List[str]:
        """Build simulation command for a test case.

        Public method for dry-run mode support.

        Args:
            case: TestCase object
            seed: Random seed
            result_dir: Result directory (optional, uses default if not provided)

        Returns:
            List of command arguments
        """
        if not result_dir:
            result_dir = self._get_run_result_dir(case.mode)

        # Use Makefile from current directory
        cmd = ['make', '-f', 'Makefile', self.config.target]

        # Add test case name
        cmd.append(f'tc={case.tc}')

        # Add mode
        cmd.append(f'mode={case.mode}')

        # Add seed
        cmd.append(f'seed={seed}')

        # Add UVM print level
        cmd.append(f'pl={self.config.pl}')

        # Add result directory
        cmd.append(f'RESULT_DIR={result_dir}')

        # Add coverage arguments if enabled
        if self.config.coverage:
            #cmd.append(f'COV_ARGS={self.config.coverage_args}')
            cmd.append('cov=1')
        else:
            cmd.append('cov=0')

        # Add extra arguments from case
        for key, value in case.extra_args.items():
            cmd.append(f'{key}={value}')

        # Add global arguments
        if self.config.global_args:
            cmd.extend(self.config.global_args.split())

        return cmd

    # Keep backward compatibility alias
    _build_sim_command = build_sim_command

    def _prepare_sim_dir(self, case: TestCase, result_dir: str) -> bool:
        """Prepare simulation directory with necessary config files.

        Note: simv and related files are already compiled into result_dir
        by the Compiler, so no symlink creation is needed.

        Args:
            case: TestCase object
            result_dir: Result directory

        Returns:
            True if preparation succeeded
        """
        try:
            # Create result directory
            os.makedirs(result_dir, exist_ok=True)

            # Verify simv exists (compiled by Compiler)
            simv_path = self.compiler.get_simv_path(case.mode)
            if not os.path.exists(simv_path):
                self.logger.error("simv not found: %s", simv_path)
                return False

            # Copy necessary files from current directory (Makefile directory)
            makefile_dir = os.getcwd()
            for fname in ['run.tcl', 'cm.cfg']:
                src = os.path.join(makefile_dir, fname)
                if os.path.exists(src):
                    dst = os.path.join(result_dir, fname)
                    if not os.path.exists(dst):
                        import shutil
                        shutil.copy2(src, dst)

            return True

        except Exception as e:
            self.logger.error("Failed to prepare simulation directory: %s", e)
            return False

    def _run_single(self, case: TestCase, run_id: int) -> RunResult:
        """Run a single simulation.

        Args:
            case: TestCase object
            run_id: Run number (1-indexed)

        Returns:
            RunResult object
        """
        # Check if stopped
        if self._stop_event.is_set():
            return RunResult(
                tc=case.tc,
                mode=case.mode,
                run_id=run_id,
                seed=0,
                passed=False,
                exit_code=-1,
                log_path="",
                duration=0.0,
                error_message="Regression stopped"
            )

        seed = self._generate_seed(case, run_id)
        result_dir = self._get_run_result_dir(case.mode)
        log_path = self._get_log_path(case.tc, case.mode, seed, run_id)

        # Prepare simulation directory
        if not self._prepare_sim_dir(case, result_dir):
            return RunResult(
                tc=case.tc,
                mode=case.mode,
                run_id=run_id,
                seed=seed,
                passed=False,
                exit_code=-1,
                log_path=log_path,
                duration=0.0,
                error_message="Failed to prepare simulation directory"
            )

        # Build command
        cmd = self.build_sim_command(case, seed, result_dir)

        self.logger.info("Command: %s", ' '.join(cmd))

        # Track status
        case_key = ""
        if self.status_tracker:
            case_key = self.status_tracker.start_case(case.tc, case.mode, seed, cmd)

        start_time = datetime.now()
        process = None

        try:
            # Execute simulation
            process = subprocess.Popen(
                cmd,
                cwd=os.getcwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Track running process
            with self._process_lock:
                self._running_processes.add(process)

            # Wait for completion or stop signal
            try:
                exit_code = process.wait(timeout=self.config.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise

            # Remove from tracking
            with self._process_lock:
                self._running_processes.discard(process)

            duration = (datetime.now() - start_time).total_seconds()

            # Check result
            check_result = self.checker.check(log_path, exit_code)

            # Extract UVM summary
            uvm_summary = ResultChecker.extract_uvm_summary(log_path)

            # Update status tracker
            if self.status_tracker and case_key:
                self.status_tracker.end_case(case_key, check_result.passed)

            run_result = RunResult(
                tc=case.tc,
                mode=case.mode,
                run_id=run_id,
                seed=seed,
                passed=check_result.passed,
                exit_code=exit_code,
                log_path=log_path,
                duration=duration,
                error_message=check_result.error_message,
                uvm_summary=uvm_summary
            )

            return run_result

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()

            # Update status tracker
            if self.status_tracker and case_key:
                self.status_tracker.end_case(case_key, False)

            return RunResult(
                tc=case.tc,
                mode=case.mode,
                run_id=run_id,
                seed=seed,
                passed=False,
                exit_code=-1,
                log_path=log_path,
                duration=duration,
                error_message=f"Simulation timed out after {self.config.timeout}h"
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()

            # Update status tracker
            if self.status_tracker and case_key:
                self.status_tracker.end_case(case_key, False)

            return RunResult(
                tc=case.tc,
                mode=case.mode,
                run_id=run_id,
                seed=seed,
                passed=False,
                exit_code=-1,
                log_path=log_path,
                duration=duration,
                error_message=str(e)
            )

        finally:
            # Ensure process is cleaned up
            if process:
                with self._process_lock:
                    self._running_processes.discard(process)

    def _run_with_retry(self, case: TestCase, run_id: int) -> RunResult:
        """Run a single simulation with retry.

        Args:
            case: TestCase object
            run_id: Run number

        Returns:
            RunResult object
        """
        result = self._run_single(case, run_id)

        if result.passed:
            return result

        # Check if stopped
        if self._stop_event.is_set():
            return result

        # Retry loop
        for retry in range(self.config.retry):
            # Check if stopped before retry
            if self._stop_event.is_set():
                break

            retry_count = retry + 1
            self.logger.info("Retrying %s run%d (attempt %d/%d)", case.tc, run_id, retry_count, self.config.retry)

            # Use the same seed for retry
            retry_result = self._run_single(case, run_id)
            retry_result.retry_count = retry_count

            if retry_result.passed:
                return retry_result

        # All retries failed
        result.retry_count = self.config.retry
        return result

    def _execute_case(self, case: TestCase) -> CaseResult:
        """Execute all runs for a test case.

        Args:
            case: TestCase object

        Returns:
            CaseResult object
        """
        case_result = CaseResult(
            tc=case.tc,
            mode=case.mode,
            times=case.times
        )

        # Run all times sequentially
        for run_id in range(1, case.times + 1):
            # Check if stopped
            if self._stop_event.is_set():
                break

            self.logger.info("Running %s run%d/%d", case.tc, run_id, case.times)

            run_result = self._run_with_retry(case, run_id)
            case_result.runs.append(run_result)

            # Update progress
            with self._lock:
                self._completed_count += 1

            # Print result
            status = "PASS" if run_result.passed else "FAIL"
            duration = run_result.duration
            retry_info = f" (after {run_result.retry_count} retries)" if run_result.retry_count > 0 else ""
            self.logger.info("%s: %s run%d [%.1fs]%s", status, case.tc, run_id, duration, retry_info)

        return case_result

    def _print_progress(self):
        """Print progress report."""
        elapsed = time.time() - self._start_time if self._start_time else 0.0
        running_count = 0
        failed_count = 0
        pending_count = 0
        if self.status_tracker:
            stats = self.status_tracker.get_statistics()
            running_count = stats['running']
            failed_count = stats['failed']
            pending_count = stats['pending']
        else:
            pending_count = max(0, self._total_count - self._completed_count)

        self.logger.info(
            "[Progress] total=%d completed=%d running=%d pending=%d failed=%d elapsed=%s",
            self._total_count,
            self._completed_count,
            running_count,
            pending_count,
            failed_count,
            format_duration(elapsed),
        )


    def stop(self):
        """Stop all running simulations gracefully."""
        self._stop_event.set()

        # Kill running processes
        with self._process_lock:
            for process in self._running_processes:
                try:
                    process.kill()
                except Exception:
                    pass
            self._running_processes.clear()

        # Stop status tracker
        if self.status_tracker:
            self.status_tracker.stop()

    def is_stopped(self) -> bool:
        """Check if executor is stopped.

        Returns:
            True if stopped
        """
        return self._stop_event.is_set()

    def _update_report(self, results: Dict[str, CaseResult]):
        """Update HTML report with current results.

        Args:
            results: Current results dictionary
        """
        if not self._reporter or not self._report_path:
            return

        try:
            runtime_snapshot = self.status_tracker.get_snapshot() if self.status_tracker else None
            self._reporter.update_results(results)
            self._reporter.update_runtime_snapshot(runtime_snapshot)
            self._reporter.generate_html(self._report_path)
        except Exception as e:
            if self.config.debug:
                self.logger.debug("Failed to update report: %s", e)

    def run_all(self, cases: List[TestCase],
                reporter: Optional['Reporter'] = None,
                report_path: str = "") -> Dict[str, CaseResult]:
        """Run all test cases in parallel.

        Args:
            cases: List of TestCase objects
            reporter: Optional Reporter instance for dynamic HTML updates
            report_path: Path to HTML report file

        Returns:
            Dictionary mapping unique case identity (see case_identity) to
            CaseResult
        """
        results = {}
        self._total_count = sum(case.times for case in cases)
        self._completed_count = 0
        self._start_time = time.time()
        self._last_progress_time = self._start_time
        self._stop_event.clear()

        # Store reporter for dynamic updates
        self._reporter = reporter
        self._report_path = report_path

        # Set status tracker total
        if self.status_tracker:
            self.status_tracker.set_total(self._total_count)
            self.status_tracker.set_start_time(self._start_time)

        self.logger.info(
            "Starting regression with %d cases, %d total runs, %d parallel jobs",
            len(cases),
            self._total_count,
            self.config.jobs,
        )

        # Progress reporter thread
        progress_stop = threading.Event()

        def progress_reporter():
            while not progress_stop.is_set() and not self._stop_event.is_set():
                time.sleep(180)  # Print every 3 minutes
                if not progress_stop.is_set() and not self._stop_event.is_set():
                    self._print_progress()

        # HTML report updater thread
        report_stop = threading.Event()

        def report_updater():
            while not report_stop.is_set() and not self._stop_event.is_set():
                time.sleep(30)  # Update every 30 seconds
                if not report_stop.is_set() and not self._stop_event.is_set():
                    self._update_report(results)

        if self.config.jobs > 1:
            progress_thread = threading.Thread(target=progress_reporter, daemon=True)
            progress_thread.start()

        # Start report updater thread if reporter is provided
        if reporter and report_path:
            report_thread = threading.Thread(target=report_updater, daemon=True)
            report_thread.start()

        try:
            with ThreadPoolExecutor(max_workers=self.config.jobs) as executor:
                # Submit all cases
                self._running_futures = {
                    executor.submit(self._execute_case, case): case
                    for case in cases
                }

                # Collect results
                for future in as_completed(self._running_futures):
                    # Check if stopped
                    if self._stop_event.is_set():
                        # Cancel remaining futures
                        for f in self._running_futures:
                            if not f.done():
                                f.cancel()
                        break

                    case = self._running_futures[future]
                    key = case_identity(case)
                    try:
                        case_result = future.result()
                        results[key] = case_result
                    except Exception as e:
                        self.logger.error("Failed to execute %s: %s", case.tc, e)
                        results[key] = CaseResult(
                            tc=case.tc,
                            mode=case.mode,
                            times=case.times
                        )

        finally:
            progress_stop.set()
            report_stop.set()
            self._running_futures.clear()

            # Final report update
            if reporter and report_path and results:
                self._update_report(results)

        return results

    def generate_urg_report(self, modes: List[str]) -> Tuple[bool, str]:
        """Generate URG coverage report.

        Args:
            modes: List of modes to merge coverage from

        Returns:
            Tuple of (success, output_dir)
        """
        if not self.config.urg_report:
            return True, ""

        # Collect all vdb directories
        vdb_dirs = []
        for mode in modes:
            vdb_path = self.compiler.get_simv_vdb_path(mode)
            if os.path.exists(vdb_path):
                vdb_dirs.append(vdb_path)

        if not vdb_dirs:
            self.logger.warning("No coverage data found")
            return False, ""

        output_dir = os.path.join(self.result_dir, "coverage_report")
        os.makedirs(output_dir, exist_ok=True)

        # Build URG command
        cmd = ['urg', '-dir'] + vdb_dirs + ['-report', output_dir]

        self.logger.info("Generating URG report: %s", ' '.join(cmd))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode == 0:
                self.logger.info("URG report generated: %s", output_dir)
                return True, output_dir
            else:
                self.logger.error("URG failed: %s", result.stderr.strip())
                return False, ""
        except Exception as e:
            self.logger.error("URG error: %s", e)
            return False, ""
