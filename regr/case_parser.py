"""
Test case parser module for regression simulation.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple


@dataclass
class TestCase:
    """Test case definition.

    Attributes:
        tc: Test case name
        mode: Simulation mode (determines compilation options)
        times: Number of times to repeat the test
        seed: Random seed (None means auto-generate)
        extra_args: Additional arguments (udc, udr, etc.)
        line_num: Line number in case.lst file
    """
    tc: str
    mode: str
    times: int = 1
    seed: Optional[int] = None
    extra_args: Dict[str, str] = field(default_factory=dict)
    line_num: int = 0

    def __str__(self) -> str:
        """Return string representation."""
        args_str = " ".join(f"{k}={v}" for k, v in self.extra_args.items())
        return f"TestCase(tc={self.tc}, mode={self.mode}, times={self.times}, seed={self.seed}, {args_str})"

    def to_command_args(self) -> List[str]:
        """Convert to command-line arguments for make.

        Returns:
            List of KEY=VALUE argument strings
        """
        args = []
        for key, value in self.extra_args.items():
            args.append(f"{key}={value}")
        return args


class CaseParser:
    """Parser for test case list file.

    The case list file format:
    - Each line contains space-separated KEY=VALUE pairs
    - Mandatory keys: tc, mode
    - Optional keys: times, seed, and any other custom keys
    - Lines starting with # are comments
    - Empty lines are ignored
    """

    # Reserved keys that are not passed as extra arguments
    RESERVED_KEYS = {'tc', 'mode', 'times', 'seed'}

    def __init__(self):
        self.cases: List[TestCase] = []
        self.errors: List[Tuple[int, str]] = []  # (line_num, error_message)

    def parse(self, filepath: str) -> List[TestCase]:
        """Parse test case list file.

        Args:
            filepath: Path to case list file

        Returns:
            List of TestCase objects

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file has parsing errors
        """
        self.cases = []
        self.errors = []

        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Case list file not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse line
                case, error = self._parse_line(line, line_num)
                if case:
                    self.cases.append(case)
                elif error:
                    self.errors.append((line_num, error))

        if self.errors:
            error_msgs = [f"Line {num}: {msg}" for num, msg in self.errors]
            raise ValueError(f"Case list parsing errors:\n" + "\n".join(error_msgs))

        return self.cases

    def _parse_line(self, line: str, line_num: int) -> Tuple[Optional[TestCase], Optional[str]]:
        """Parse a single line from case list file.

        Args:
            line: Line content
            line_num: Line number

        Returns:
            Tuple of (TestCase or None, error message or None)
        """
        # Parse KEY=VALUE pairs
        pairs = {}
        parts = line.split()

        for part in parts:
            if '=' not in part:
                continue

            key, value = part.split('=', 1)
            pairs[key.lower()] = value

        # Validate mandatory fields
        if 'tc' not in pairs:
            return None, "Missing mandatory field 'tc'"

        if 'mode' not in pairs:
            return None, "Missing mandatory field 'mode'"

        # Extract fields
        tc = pairs['tc']
        mode = pairs['mode']

        # Parse optional fields
        times = 1
        if 'times' in pairs:
            try:
                times = int(pairs['times'])
                if times < 1:
                    return None, f"Invalid times value: {pairs['times']} (must be >= 1)"
            except ValueError:
                return None, f"Invalid times value: {pairs['times']} (not an integer)"

        seed = None
        if 'seed' in pairs:
            try:
                seed = int(pairs['seed'])
                if seed < 0:
                    return None, f"Invalid seed value: {pairs['seed']} (must be >= 0)"
            except ValueError:
                return None, f"Invalid seed value: {pairs['seed']} (not an integer)"

        # Extract extra arguments
        extra_args = {}
        for key, value in pairs.items():
            if key not in self.RESERVED_KEYS:
                extra_args[key] = value

        case = TestCase(
            tc=tc,
            mode=mode,
            times=times,
            seed=seed,
            extra_args=extra_args,
            line_num=line_num
        )

        # Validate case
        is_valid, error = self.validate(case)
        if not is_valid:
            return None, error

        return case, None

    def validate(self, case: TestCase) -> Tuple[bool, Optional[str]]:
        """Validate a test case.

        Args:
            case: TestCase to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate tc name
        if not case.tc:
            return False, "Test case name cannot be empty"

        # Check for invalid characters in tc
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', case.tc):
            return False, f"Invalid test case name: {case.tc} (must be valid identifier)"

        # Validate mode
        if not case.mode:
            return False, "Mode cannot be empty"

        # Check for invalid characters in mode
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', case.mode):
            return False, f"Invalid mode name: {case.mode} (must be valid identifier)"

        # Validate times
        if case.times < 1:
            return False, f"Times must be >= 1, got {case.times}"

        # Validate seed if specified
        if case.seed is not None and case.seed < 0:
            return False, f"Seed must be >= 0, got {case.seed}"

        return True, None

    @staticmethod
    def get_modes(cases: List[TestCase]) -> List[str]:
        """Get unique modes from test cases.

        Args:
            cases: List of TestCase objects

        Returns:
            List of unique mode names (preserving order of first appearance)
        """
        seen = set()
        modes = []
        for case in cases:
            if case.mode not in seen:
                seen.add(case.mode)
                modes.append(case.mode)
        return modes

    @staticmethod
    def get_case_count(cases: List[TestCase]) -> int:
        """Get total execution count (sum of all times).

        Args:
            cases: List of TestCase objects

        Returns:
            Total number of simulation runs
        """
        return sum(case.times for case in cases)