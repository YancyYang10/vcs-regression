"""
Configuration management module for regression simulation.
"""

import argparse
import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List


@dataclass
class RegressionConfig:
    """Configuration for regression simulation.

    Supports loading from:
    1. Command-line arguments (highest priority)
    2. Configuration file
    3. Default values (lowest priority)
    """

    # Path configuration
    case_list: str = "case.lst"
    target: str = "sim"

    # Execution configuration
    jobs: int = 1
    retry: int = 0
    timeout: int = 1  # hours (internally converted to seconds)
    timeout_seconds: int = field(default=3600, init=False, repr=False)  # internal use

    # UVM print level
    pl: str = "UVM_MEDIUM"

    # Coverage configuration
    coverage: bool = True
    coverage_args: str = "-cm line+cond+branch+fsm+tgl+assert"
    urg_report: bool = False

    # Result judgment
    fail_keywords: str = r"UVM_FATAL\s*:\s*[1-9]\d*|UVM_ERROR\s*:\s*[1-9]\d*"
    pass_keywords: str = ""

    # Global arguments
    global_args: str = ""

    # Debug mode
    debug: bool = False

    # Dry-run mode: print commands without executing
    dry_run: bool = False

    # Show commands only (alias of dry-run intent)
    show_commands: bool = False

    # Compile only
    compile_only: bool = False

    # Skip compilation: run simulation directly
    skip_compile: bool = False

    # Simulate only (alias of skip_compile intent)
    sim_only: bool = False

    # Result directory (auto-generated)
    result_dir: str = field(default="", init=False)

    def __post_init__(self):
        """Post-initialization processing."""
        # Convert timeout from hours to seconds
        self.timeout_seconds = self.timeout * 3600

        # Auto-generate result_dir as ./regress_results_YYYYMMDD
        from datetime import datetime
        date_str = datetime.now().strftime('%Y%m%d')
        self.result_dir = f"./regress_results_{date_str}"

    @classmethod
    def load(cls, args: Optional[argparse.Namespace] = None) -> "RegressionConfig":
        """Load configuration from command-line arguments and config file.

        Priority: Command-line > Config file > Default

        Args:
            args: Parsed command-line arguments

        Returns:
            RegressionConfig instance
        """
        config = cls()

        if args is None:
            return config

        # Load from config file first
        config_file = args.config if hasattr(args, 'config') else "regress.cfg"
        if os.path.exists(config_file):
            config._load_from_file(config_file)

        # Override with command-line arguments
        config._override_from_args(args)

        return config

    def _load_from_file(self, filepath: str) -> None:
        """Load configuration from file.

        Args:
            filepath: Path to configuration file
        """
        parser = configparser.ConfigParser()
        # Add a default section for flat config files
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # If no section, add DEFAULT section
        if not content.strip().startswith('['):
            content = '[DEFAULT]\n' + content

        parser.read_string(content)

        # Get all items from DEFAULT section
        items = dict(parser['DEFAULT'])

        # Map config file keys to class attributes
        key_mapping = {
            'jobs': ('jobs', int),
            'retry': ('retry', int),
            'timeout': ('timeout', int),  # hours
            'time_out': ('timeout', int),  # Alternative name
            'case_list': ('case_list', str),
            'caselist': ('case_list', str),  # Alternative name
            'pl': ('pl', str),  # UVM print level
            'target': ('target', str),
            'coverage': ('coverage', lambda x: x.lower() in ('true', '1', 'yes')),
            'coverage_args': ('coverage_args', str),
            'urg_report': ('urg_report', lambda x: x.lower() in ('true', '1', 'yes')),
            'urg': ('urg_report', lambda x: x.lower() in ('true', '1', 'yes')),  # Alternative name
            'fail_keywords': ('fail_keywords', str),
            'log_keywords': ('fail_keywords', str),  # Alternative name
            'pass_keywords': ('pass_keywords', str),
            'global_args': ('global_args', str),
        }

        for key, value in items.items():
            key_lower = key.lower().strip()
            if key_lower in key_mapping:
                attr_name, converter = key_mapping[key_lower]
                try:
                    setattr(self, attr_name, converter(value))
                except (ValueError, TypeError):
                    pass  # Keep default value on conversion error

        # Convert timeout from hours to seconds after loading
        self.timeout_seconds = self.timeout * 3600

    def _override_from_args(self, args: argparse.Namespace) -> None:
        """Override configuration with command-line arguments.

        Args:
            args: Parsed command-line arguments
        """
        # Map argument names to config attributes
        arg_mapping = {
            'case_list': 'case_list',
            'jobs': 'jobs',
            'retry': 'retry',
            'timeout': 'timeout',
            'pl': 'pl',
            'coverage': 'coverage',
            'coverage_args': 'coverage_args',
            'urg': 'urg_report',
            'fail_keywords': 'fail_keywords',
            'pass_keywords': 'pass_keywords',
            'global_args': 'global_args',
            'debug': 'debug',
            'target': 'target',
            'dry_run': 'dry_run',
            'show_commands': 'show_commands',
            'compile_only': 'compile_only',
            'skip_compile': 'skip_compile',
            'sim_only': 'sim_only',
        }

        for arg_name, attr_name in arg_mapping.items():
            if hasattr(args, arg_name):
                value = getattr(args, arg_name)
                if value is not None:
                    setattr(self, attr_name, value)

        # Handle special no_coverage flag
        if hasattr(args, 'no_coverage') and args.no_coverage:
            self.coverage = False

        # Convert timeout from hours to seconds after override
        self.timeout_seconds = self.timeout * 3600

    def validate(self) -> List[str]:
        """Validate configuration.

        Returns:
            List of error messages, empty if valid
        """
        errors = []

        # Normalize aliases and validate mutually exclusive modes
        if self.show_commands:
            self.dry_run = True

        if self.sim_only:
            self.skip_compile = True

        if self.compile_only and self.skip_compile:
            errors.append("--compile-only and --sim-only/--skip-compile are mutually exclusive")

        # Check case list file exists
        if not os.path.exists(self.case_list):
            errors.append(f"Case list file not found: {self.case_list}")

        # Validate numeric parameters
        if self.jobs < 1:
            errors.append(f"jobs must be >= 1, got {self.jobs}")

        if self.retry < 0:
            errors.append(f"retry must be >= 0, got {self.retry}")

        if self.timeout < 1:
            errors.append(f"timeout must be >= 1 hour, got {self.timeout}")

        return errors

    def __str__(self) -> str:
        """Return string representation of configuration."""
        lines = ["Regression Configuration:"]
        lines.append("-" * 40)
        lines.append(f"  Case list:    {self.case_list}")
        lines.append(f"  Result dir:   {self.result_dir}")
        lines.append(f"  Target:       {self.target}")
        lines.append(f"  Jobs:         {self.jobs}")
        lines.append(f"  Retry:        {self.retry}")
        lines.append(f"  Timeout:      {self.timeout}h ({self.timeout_seconds}s)")
        lines.append(f"  UVM Level:    {self.pl}")
        lines.append(f"  Coverage:     {self.coverage}")
        if self.coverage:
            lines.append(f"  Cov args:     {self.coverage_args}")
        lines.append(f"  URG report:   {self.urg_report}")
        lines.append(f"  Fail pattern: {self.fail_keywords}")
        lines.append(f"  Pass pattern: {self.pass_keywords}")
        lines.append(f"  Global args:  {self.global_args}")
        lines.append(f"  Debug:        {self.debug}")
        lines.append(f"  Dry-run:      {self.dry_run}")
        lines.append(f"  Show cmds:    {self.show_commands}")
        lines.append(f"  Compile only: {self.compile_only}")
        lines.append(f"  Skip compile: {self.skip_compile}")
        lines.append(f"  Sim only:     {self.sim_only}")
        return "\n".join(lines)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create argument parser for regression script.

    Returns:
        ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description="IC Verification Regression Simulation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -c regress.cfg -l case.lst -j 4
  %(prog)s -j 4 --retry 2 --coverage --urg --pl UVM_HIGH
        """
    )

    # Configuration file
    parser.add_argument(
        '-c', '--config',
        default='regress.cfg',
        help='Configuration file path (default: regress.cfg)'
    )

    # File paths
    parser.add_argument(
        '-l', '--case-list',
        help='Test case list file path (default: case.lst)'
    )
    parser.add_argument(
        '--target',
        default='sim',
        help='Make target (default: sim)'
    )

    # Execution options
    parser.add_argument(
        '-j', '--jobs',
        type=int,
        help='Number of parallel jobs (default: 1)'
    )
    parser.add_argument(
        '-r', '--retry',
        type=int,
        help='Number of retries on failure (default: 0)'
    )
    parser.add_argument(
        '-t', '--timeout',
        type=int,
        help='Timeout for single simulation in hours (default: 1)'
    )
    parser.add_argument(
        '--pl',
        choices=['UVM_LOW', 'UVM_MEDIUM', 'UVM_HIGH', 'UVM_FULL', 'UVM_DEBUG'],
        help='UVM print level (default: UVM_MEDIUM)'
    )

    # Coverage options
    parser.add_argument(
        '--coverage',
        action='store_true',
        default=None,
        help='Enable coverage collection (default: enabled)'
    )
    parser.add_argument(
        '--no-coverage',
        action='store_true',
        help='Disable coverage collection'
    )
    parser.add_argument(
        '--coverage-args',
        help='Coverage arguments for VCS (default: -cm line+cond+branch+fsm+tgl+assert)'
    )
    parser.add_argument(
        '--urg',
        action='store_true',
        help='Generate URG coverage report'
    )

    # Result judgment
    parser.add_argument(
        '--fail-keywords',
        help='Regex pattern for failure keywords in logs'
    )
    parser.add_argument(
        '--pass-keywords',
        help='Regex pattern for success keywords in logs'
    )

    # Global arguments
    parser.add_argument(
        '-g', '--global-args',
        help='Global make arguments for all cases'
    )

    # Debug
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug mode'
    )

    # Dry-run mode
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print compile and simulation commands without executing'
    )
    parser.add_argument(
        '--show-commands',
        action='store_true',
        help='Show compile and simulation commands only (same as --dry-run)'
    )

    # Execution mode control
    parser.add_argument(
        '--compile-only',
        action='store_true',
        help='Compile only, do not run simulations'
    )

    # Skip compilation
    parser.add_argument(
        '--skip-compile',
        action='store_true',
        help='Skip compilation and run simulation directly'
    )
    parser.add_argument(
        '--sim-only',
        action='store_true',
        help='Run simulation only (same as --skip-compile)'
    )

    return parser