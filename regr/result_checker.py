"""
Result checker module for regression simulation.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional, List


@dataclass
class CheckResult:
    """Result of log checking.

    Attributes:
        passed: Whether the test passed
        error_message: Error message if failed
        matched_fail: List of matched failure keywords
        matched_pass: List of matched success keywords
    """
    passed: bool
    error_message: str = ""
    matched_fail: List[str] = None
    matched_pass: List[str] = None

    def __post_init__(self):
        if self.matched_fail is None:
            self.matched_fail = []
        if self.matched_pass is None:
            self.matched_pass = []


class ResultChecker:
    """Checker for simulation results.

    Checks simulation results based on:
    1. Exit code (0 = success)
    2. Log file content (failure keywords)
    3. Log file content (success keywords, optional)
    """

    def __init__(self, fail_keywords: str = "", pass_keywords: str = ""):
        """Initialize result checker.

        Args:
            fail_keywords: Regex pattern for failure keywords
            pass_keywords: Regex pattern for success keywords
        """
        self.fail_keywords = fail_keywords
        self.pass_keywords = pass_keywords

        # Compile regex patterns
        self.fail_pattern = None
        self.pass_pattern = None

        if fail_keywords:
            try:
                self.fail_pattern = re.compile(fail_keywords, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"Invalid fail_keywords regex: {e}")

        if pass_keywords:
            try:
                self.pass_pattern = re.compile(pass_keywords, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"Invalid pass_keywords regex: {e}")

    def check(self, log_path: str, exit_code: int) -> CheckResult:
        """Check simulation result.

        Args:
            log_path: Path to simulation log file
            exit_code: Exit code of simulation process

        Returns:
            CheckResult object
        """
        matched_fail = []
        matched_pass = []

        # Check exit code first
        if exit_code != 0:
            return CheckResult(
                passed=False,
                error_message=f"Simulation exited with non-zero code: {exit_code}",
                matched_fail=[],
                matched_pass=[]
            )

        # Read log file
        log_content = ""
        if log_path and Path(log_path).exists():
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    log_content = f.read()
            except Exception as e:
                return CheckResult(
                    passed=False,
                    error_message=f"Failed to read log file: {e}",
                    matched_fail=[],
                    matched_pass=[]
                )

        # Check failure keywords
        if self.fail_pattern:
            matches = self.fail_pattern.findall(log_content)
            if matches:
                matched_fail = list(set(matches))  # Unique matches
                return CheckResult(
                    passed=False,
                    error_message=f"Failure keywords matched: {matched_fail}",
                    matched_fail=matched_fail,
                    matched_pass=[]
                )

        # Check success keywords (if configured)
        if self.pass_pattern:
            matches = self.pass_pattern.findall(log_content)
            if matches:
                matched_pass = list(set(matches))
                return CheckResult(
                    passed=True,
                    error_message="",
                    matched_fail=[],
                    matched_pass=matched_pass
                )
            # If success keywords are configured but not found, consider as failed
            return CheckResult(
                passed=False,
                error_message="Success keywords not found in log",
                matched_fail=[],
                matched_pass=[]
            )

        # No failure keywords matched and no success keywords required
        return CheckResult(
            passed=True,
            error_message="",
            matched_fail=[],
            matched_pass=[]
        )

    def check_exit_code_only(self, exit_code: int) -> CheckResult:
        """Check only exit code without log file.

        Args:
            exit_code: Exit code of simulation process

        Returns:
            CheckResult object
        """
        if exit_code != 0:
            return CheckResult(
                passed=False,
                error_message=f"Simulation exited with non-zero code: {exit_code}",
                matched_fail=[],
                matched_pass=[]
            )

        return CheckResult(
            passed=True,
            error_message="",
            matched_fail=[],
            matched_pass=[]
        )

    @staticmethod
    def extract_uvm_summary(log_path: str) -> Optional[dict]:
        """Extract UVM report summary from log file.

        Args:
            log_path: Path to simulation log file

        Returns:
            Dictionary with UVM counts or None if not found
        """
        if not Path(log_path).exists():
            return None

        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return None

        # Pattern for UVM report summary
        # Format: UVM_FATAL : N found, UVM_ERROR : N found, etc.
        pattern = r'UVM_(FATAL|ERROR|WARNING|INFO)\s*:\s*(\d+)\s*found'
        matches = re.findall(pattern, content)

        if not matches:
            return None

        summary = {}
        for level, count in matches:
            summary[f'UVM_{level}'] = int(count)

        return summary