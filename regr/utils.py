"""
Utility functions for regression simulation.
"""

import logging
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def get_timestamp() -> str:
    """Get current timestamp string.

    Returns:
        Timestamp string in format YYYYMMDD_HHMMSS
    """
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_git_hash(work_dir: str = ".") -> str:
    """Get current git commit hash.

    Args:
        work_dir: Working directory

    Returns:
        Git commit hash or "unknown" if not in a git repo
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return result.stdout.strip()[:8]  # Short hash
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "unknown"


def ensure_dir(path: str) -> bool:
    """Ensure directory exists, create if not.

    Args:
        path: Directory path

    Returns:
        True if directory exists or was created
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False




def setup_logger(log_path: str, logger_name: str = "regr") -> logging.Logger:
    """Create regression logger writing to terminal and append-only file.

    Args:
        log_path: Path to logging.txt
        logger_name: Logger name

    Returns:
        Configured logger
    """
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')

    file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def print_banner(title: str, width: int = 60):
    """Print a banner with title.

    Args:
        title: Banner title
        width: Banner width
    """
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def print_section(title: str, width: int = 60):
    """Print a section header.

    Args:
        title: Section title
        width: Line width
    """
    print(f"\n{title}")
    print("-" * width)


def get_relative_path(path: str, base: str) -> str:
    """Get relative path from base directory.

    Args:
        path: Target path
        base: Base directory

    Returns:
        Relative path string
    """
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return path


def find_makefile(start_dir: str = ".") -> Optional[str]:
    """Find Makefile in current or parent directories.

    Args:
        start_dir: Starting directory

    Returns:
        Path to Makefile or None if not found
    """
    current = os.path.abspath(start_dir)

    while current != '/':
        makefile = os.path.join(current, 'Makefile')
        if os.path.exists(makefile):
            return makefile

        # Check parent directory
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    return None


def check_tool_available(tool: str) -> bool:
    """Check if a command-line tool is available.

    Args:
        tool: Tool name

    Returns:
        True if tool is available
    """
    try:
        result = subprocess.run(
            ['which', tool],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


class ProgressTracker:
    """Simple progress tracker for regression runs."""

    def __init__(self, total: int):
        """Initialize progress tracker.

        Args:
            total: Total number of items
        """
        self.total = total
        self.completed = 0
        self.failed = 0
        self.start_time = datetime.now()

    def update(self, passed: bool = True):
        """Update progress.

        Args:
            passed: Whether the item passed
        """
        self.completed += 1
        if not passed:
            self.failed += 1

    def get_progress(self) -> Tuple[int, int, int]:
        """Get current progress.

        Returns:
            Tuple of (completed, total, failed)
        """
        return (self.completed, self.total, self.failed)

    def get_elapsed(self) -> float:
        """Get elapsed time in seconds.

        Returns:
            Elapsed time in seconds
        """
        return (datetime.now() - self.start_time).total_seconds()

    def get_summary(self) -> str:
        """Get progress summary string.

        Returns:
            Summary string
        """
        elapsed = self.get_elapsed()
        rate = (self.completed / self.total * 100) if self.total > 0 else 0

        return (f"Progress: {self.completed}/{self.total} ({rate:.1f}%) "
                f"| Failed: {self.failed} "
                f"| Elapsed: {format_duration(elapsed)}")


class Tee:
    """Tee output to both terminal and file.

    Redirects stdout to both terminal and a log file simultaneously.
    """

    def __init__(self, terminal, log_file):
        """Initialize Tee.

        Args:
            terminal: Original stdout (typically sys.stdout)
            log_file: Open file object for logging
        """
        self.terminal = terminal
        self.log_file = log_file

    def write(self, message):
        """Write message to both terminal and file.

        Args:
            message: String to write
        """
        self.terminal.write(message)
        self.log_file.write(message)
        self.log_file.flush()

    def flush(self):
        """Flush both streams."""
        self.terminal.flush()
        self.log_file.flush()

    def isatty(self):
        """Check if this is a TTY.

        Returns:
            False (Tee is not a TTY)
        """
        return False