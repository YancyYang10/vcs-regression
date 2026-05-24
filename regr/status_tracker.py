"""
Status tracking module for regression simulation.

Provides real-time tracking of running simulations.
"""

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class CaseStatus:
    """Status of a running simulation case.

    Attributes:
        tc: Test case name
        mode: Simulation mode
        seed: Random seed
        cmd: Command being executed
        start_time: Start timestamp
        status: Current status ('running', 'completed', 'failed')
    """
    tc: str
    mode: str
    seed: int
    cmd: List[str]
    start_time: float
    status: str = 'running'


class StatusTracker:
    """Track running simulation status in memory."""

    def __init__(self, status_file: str = ""):
        """Initialize status tracker.

        Args:
            status_file: Deprecated; retained for compatibility only
        """
        self.status_file = status_file
        self._lock = threading.Lock()
        self._running_cases: Dict[str, CaseStatus] = {}
        self._completed_count = 0
        self._failed_count = 0
        self._total_count = 0
        self._start_time: Optional[float] = None
        self._stop_event = threading.Event()

    def set_total(self, total: int):
        """Set total number of simulations.

        Args:
            total: Total simulation count
        """
        with self._lock:
            self._total_count = total

    def set_start_time(self, start_time: float):
        """Set regression start time.

        Args:
            start_time: Start timestamp
        """
        with self._lock:
            self._start_time = start_time

    def start_case(self, tc: str, mode: str, seed: int, cmd: List[str]) -> str:
        """Record case start.

        Args:
            tc: Test case name
            mode: Simulation mode
            seed: Random seed
            cmd: Command being executed

        Returns:
            Case key for later reference
        """
        case_key = f"{tc}_{mode}_{seed}"

        with self._lock:
            self._running_cases[case_key] = CaseStatus(
                tc=tc,
                mode=mode,
                seed=seed,
                cmd=cmd,
                start_time=time.time(),
                status='running'
            )

        return case_key

    def end_case(self, case_key: str, success: bool):
        """Record case end.

        Args:
            case_key: Case key returned by start_case
            success: Whether the case succeeded
        """
        with self._lock:
            if case_key in self._running_cases:
                del self._running_cases[case_key]

            if success:
                self._completed_count += 1
            else:
                self._failed_count += 1

    def get_elapsed_seconds(self) -> float:
        """Get elapsed time since regression start in seconds."""
        if self._start_time is None:
            return 0.0
        return max(0.0, time.time() - self._start_time)

    def get_elapsed_time(self) -> str:
        """Get elapsed time since regression start.

        Returns:
            Formatted elapsed time string (HH:MM:SS)
        """
        return self._format_duration(self.get_elapsed_seconds())

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to HH:MM:SS.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def get_statistics(self) -> Dict[str, int]:
        """Get current statistics.

        Returns:
            Dictionary with current counts
        """
        with self._lock:
            running = len(self._running_cases)
            return {
                'total': self._total_count,
                'completed': self._completed_count,
                'failed': self._failed_count,
                'running': running,
                'pending': max(0, self._total_count - self._completed_count - self._failed_count - running)
            }

    def get_running_cases(self) -> List[dict]:
        """Get running case snapshots for HTML rendering."""
        with self._lock:
            now = time.time()
            running_cases = []
            for status in self._running_cases.values():
                elapsed_seconds = max(0.0, now - status.start_time)
                running_cases.append({
                    'tc': status.tc,
                    'mode': status.mode,
                    'seed': status.seed,
                    'command': ' '.join(status.cmd),
                    'start_time': datetime.fromtimestamp(status.start_time).strftime('%Y-%m-%d %H:%M:%S'),
                    'elapsed_seconds': elapsed_seconds,
                    'elapsed': self._format_duration(elapsed_seconds),
                    'status': status.status,
                })

            running_cases.sort(key=lambda item: (item['tc'], item['mode'], item['seed']))
            return running_cases

    def get_snapshot(self) -> Dict[str, object]:
        """Get complete runtime snapshot for HTML rendering."""
        stats = self.get_statistics()
        return {
            'stats': stats,
            'running_cases': self.get_running_cases(),
            'elapsed': self.get_elapsed_time(),
            'elapsed_seconds': self.get_elapsed_seconds(),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stopped': self.is_stopped(),
        }

    def stop(self):
        """Stop the status tracker."""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """Check if tracker is stopped.

        Returns:
            True if stopped
        """
        return self._stop_event.is_set()
