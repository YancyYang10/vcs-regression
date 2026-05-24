#!/usr/bin/env python3
"""
IC Verification Regression Simulation Script

This script automates the execution of IC verification test cases with:
- Parallel execution
- Failure retries
- Result collection
- HTML report generation
- Graceful shutdown on CTRL+C
- Dry-run mode for command preview
- Skip compilation option

Usage:
    python3 regr_run.py [options]

Examples:
    python3 regr_run.py -c regress.cfg -l case.lst -j 4
    python3 regr_run.py --makefile Makefile --result-dir ./results --jobs 8
    python3 regr_run.py --dry-run  # Print commands without executing
    python3 regr_run.py --skip-compile  # Skip compilation
"""

import os
import sys
import time
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from regr.config import RegressionConfig, create_argument_parser
from regr.case_parser import CaseParser
from regr.compiler import Compiler
from regr.executor import Executor
from regr.reporter import Reporter
from regr.status_tracker import StatusTracker
from regr.utils import get_timestamp, get_git_hash, format_duration, setup_logger, ensure_dir


class RegressionRunner:
    """Main runner class for regression simulation.

    Handles:
    - Signal handling for graceful shutdown
    - Orchestration of compilation and simulation
    - Report generation
    """

    def __init__(self):
        """Initialize runner."""
        self._interrupted = False
        self._results = {}
        self._executor: Optional[Executor] = None
        self._status_tracker: Optional[StatusTracker] = None
        self._config: Optional[RegressionConfig] = None
        self._logger = None

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signal."""
        if self._interrupted:
            # Second interrupt, force exit
            if self._logger:
                self._logger.warning("Force exit...")
            else:
                print("\n\nForce exit...")
            sys.exit(130)

        self._interrupted = True
        if self._logger:
            self._logger.warning("Received interrupt signal, stopping and generating report...")
        else:
            print("\n\nReceived interrupt signal, stopping and generating report...")

        # Stop running simulations
        if self._executor:
            self._executor.stop()

    def run(self) -> int:
        """Run the regression.

        Returns:
            Exit code (0 for success, non-zero for failure)
        """
        # Setup signal handlers
        self.setup_signal_handlers()

        # Parse command-line arguments
        parser = create_argument_parser()
        args = parser.parse_args()

        # Load configuration
        try:
            self._config = RegressionConfig.load(args)
        except Exception as e:
            print(f"ERROR: Failed to load configuration: {e}")
            return 1

        config = self._config

        # Setup append-only logging
        ensure_dir(config.result_dir)
        logging_path = os.path.join(config.result_dir, "logging.txt")
        self._logger = setup_logger(logging_path)

        # Validate configuration
        errors = config.validate()
        if errors:
            self._logger.error("Configuration errors:")
            for error in errors:
                self._logger.error("  - %s", error)
            return 1

        # Get timestamp for this regression run
        timestamp = get_timestamp()

        # Get git hash
        git_hash = get_git_hash()

        start_time = time.time()
        exit_code = 0

        try:
            self._logger.info("=" * 60)
            self._logger.info("IC Verification Regression Simulation")
            self._logger.info("Regression started at: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self._logger.info("Work directory: %s", os.getcwd())
            self._logger.info("Git commit: %s", git_hash)
            self._logger.info("Case list: %s", config.case_list)
            self._logger.info("%s", config)

            self._logger.info("Step 1: Parsing test case list")
            self._logger.info("-" * 60)
            case_parser = CaseParser()

            try:
                cases = case_parser.parse(config.case_list)
            except FileNotFoundError as e:
                self._logger.error("%s", e)
                exit_code = 1
                return exit_code
            except ValueError as e:
                self._logger.error("%s", e)
                exit_code = 1
                return exit_code

            if not cases:
                self._logger.warning("No test cases found in case list")
                exit_code = 0
                return exit_code

            self._logger.info("Found %d test cases", len(cases))

            # Get unique modes
            modes = CaseParser.get_modes(cases)
            self._logger.info("Modes: %s", ', '.join(modes))

            total_runs = CaseParser.get_case_count(cases)
            self._logger.info("Total simulation runs: %d", total_runs)

            # Dry-run mode: print commands and exit
            if config.dry_run:
                exit_code = self._run_dry_run(config, modes, cases, timestamp)
                return exit_code

            self._logger.info("Step 2: Compilation phase")
            self._logger.info("-" * 60)

            # Use current directory as work directory
            work_dir = os.getcwd()
            compiler = Compiler(config, work_dir)

            if config.skip_compile:
                self._logger.info("Skipping compilation (using existing simv)")
                missing_modes = []
                for mode in modes:
                    simv_path = compiler.get_simv_path(mode)
                    if not os.path.exists(simv_path):
                        missing_modes.append(mode)

                if missing_modes:
                    self._logger.error("simv not found for modes: %s", ', '.join(missing_modes))
                    self._logger.error("Please run without --skip-compile first")
                    exit_code = 1
                    return exit_code
            else:
                compile_results = compiler.compile_all_modes(modes)
                failed_compiles = [r for r in compile_results if not r.success]
                if failed_compiles:
                    self._logger.error("Compilation failed for modes:")
                    for r in failed_compiles:
                        self._logger.error("  - %s: %s", r.mode, r.error_message)
                    exit_code = 1
                    return exit_code

            if config.compile_only:
                self._logger.info("Compile-only mode complete")
                exit_code = 0
                return exit_code

            if self._interrupted:
                self._logger.warning("Regression interrupted after compilation")
                exit_code = 130
                return exit_code

            self._logger.info("Step 3: Simulation phase")
            self._logger.info("-" * 60)

            self._status_tracker = StatusTracker()

            report_path = os.path.join(config.result_dir, f"report_{timestamp}.html")
            reporter = Reporter(config, {}, timestamp, git_hash)

            self._executor = Executor(
                config, compiler, config.result_dir, timestamp,
                status_tracker=self._status_tracker
            )

            self._results = self._executor.run_all(cases, reporter, report_path)

            if config.urg_report and not self._interrupted:
                self._logger.info("Step 4: Generating URG coverage report")
                self._logger.info("-" * 60)
                self._executor.generate_urg_report(modes)

            self._logger.info("Step 5: Generating HTML report")
            self._logger.info("-" * 60)
            if reporter.generate_html(report_path):
                self._logger.info("Report generated: %s", report_path)
            else:
                self._logger.error("Failed to generate report")

            self._logger.info("Summary")
            self._logger.info("-" * 60)

            duration = time.time() - start_time
            total_cases = len(self._results)
            passed_cases = sum(1 for r in self._results.values() if r.passed)
            failed_cases = total_cases - passed_cases

            total_runs = sum(r.times for r in self._results.values())
            passed_runs = sum(r.pass_count for r in self._results.values())
            failed_runs = sum(r.fail_count for r in self._results.values())

            self._logger.info("Regression completed at: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            self._logger.info("Total duration: %s", format_duration(duration))

            if self._interrupted:
                self._logger.warning("Regression was interrupted by user")

            case_rate = (passed_cases / total_cases * 100) if total_cases > 0 else 0.0
            run_rate = (passed_runs / total_runs * 100) if total_runs > 0 else 0.0
            self._logger.info("Cases: %d/%d passed (%.1f%%)", passed_cases, total_cases, case_rate)
            self._logger.info("Runs: %d/%d passed (%.1f%%)", passed_runs, total_runs, run_rate)

            if failed_cases > 0:
                self._logger.info("Failed cases:")
                for tc, case_result in sorted(self._results.items()):
                    if not case_result.passed:
                        self._logger.info("  - %s: %d/%d runs failed", tc, case_result.fail_count, case_result.times)

            self._logger.info("Report: %s", report_path)

            if self._interrupted:
                self._logger.warning("REGRESSION INTERRUPTED")
                exit_code = 130
            elif failed_cases > 0:
                self._logger.error("REGRESSION FAILED")
                exit_code = 1
            else:
                self._logger.info("REGRESSION PASSED")
                exit_code = 0

        except Exception as e:
            if self._logger:
                self._logger.error("ERROR: %s", e)
            else:
                print(f"\nERROR: {e}")
            if config.debug:
                import traceback
                traceback.print_exc()
            exit_code = 1

        finally:
            if self._logger:
                self._logger.info("Logging file: %s", logging_path)

        return exit_code

    def _run_dry_run(self, config: RegressionConfig, modes: list, cases: list, timestamp: str) -> int:
        """Run in dry-run mode: print commands without executing.

        Args:
            config: Regression configuration
            modes: List of simulation modes
            cases: List of test cases
            timestamp: Regression timestamp

        Returns:
            Exit code (always 0 for dry-run)
        """
        self._logger.info("Dry-run mode: printing commands")
        self._logger.info("-" * 60)

        work_dir = os.getcwd()
        compiler = Compiler(config, work_dir)
        executor = Executor(config, compiler, config.result_dir, timestamp)

        self._logger.info("=== Compilation Commands ===")
        for mode in modes:
            cmd = compiler.build_compile_command(mode)
            self._logger.info("Compile %s:", mode)
            self._logger.info("  %s", ' '.join(cmd))

        self._logger.info("=== Simulation Commands ===")
        for case in cases:
            times_str = f" (x{case.times})" if case.times > 1 else ""
            self._logger.info("Sim %s%s:", case.tc, times_str)
            for run_id in range(1, case.times + 1):
                seed = case.seed if case.seed is not None else run_id
                result_dir = os.path.join(config.result_dir, case.mode)
                cmd = executor.build_sim_command(case, seed, result_dir)
                prefix = f"run{run_id}:" if case.times > 1 else ""
                if prefix:
                    self._logger.info("  %s %s", prefix, ' '.join(cmd))
                else:
                    self._logger.info("  %s", ' '.join(cmd))

        self._logger.info("DRY-RUN COMPLETE (no commands executed)")
        return 0


def main():
    """Main entry point for regression simulation."""
    runner = RegressionRunner()
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())