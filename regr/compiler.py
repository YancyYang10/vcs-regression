"""
Compiler management module for regression simulation.
"""

import logging
import os
import subprocess
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Optional, List, Set
from datetime import datetime

from .config import RegressionConfig


@dataclass
class CompileResult:
    """Result of compilation.

    Attributes:
        mode: Simulation mode
        success: Whether compilation succeeded
        log_path: Path to compilation log
        simv_path: Path to compiled simulator
        duration: Compilation duration in seconds
        error_message: Error message if failed
    """
    mode: str
    success: bool
    log_path: str
    simv_path: str
    duration: float = 0.0
    error_message: str = ""


class Compiler:
    """Compiler manager for simulation modes.

    Handles:
    - Checking if recompilation is needed
    - Executing compilation commands
    - Managing compile cache
    """

    def __init__(self, config: RegressionConfig, work_dir: str):
        """Initialize compiler.

        Args:
            config: Regression configuration
            work_dir: Working directory for compilation
        """
        self.config = config
        self.work_dir = os.path.abspath(work_dir)
        self.result_dir = os.path.abspath(config.result_dir)

        self.compiled_modes: Set[str] = set()
        self.logger = logging.getLogger("regr")

    def get_simv_path(self, mode: str) -> str:
        """Get path to compiled simulator for a mode.

        Args:
            mode: Simulation mode

        Returns:
            Path to simv_<mode>
        """
        return os.path.join(self.result_dir, mode, f"simv_{mode}")

    def get_simv_vdb_path(self, mode: str) -> str:
        """Get path to coverage database for a mode.

        Args:
            mode: Simulation mode

        Returns:
            Path to simv_<mode>.vdb
        """
        return os.path.join(self.result_dir, mode, f"simv_{mode}.vdb")

    def need_recompile(self, mode: str) -> bool:
        """Check if recompilation is needed for a mode.

        Checks:
        1. Whether simv_<mode> exists
        2. Whether source files are newer than simv

        Args:
            mode: Simulation mode

        Returns:
            True if recompilation is needed
        """
        simv_path = self.get_simv_path(mode)

        # Check if simv exists
        if not os.path.exists(simv_path):
            return True

        # Check if simv is executable
        if not os.access(simv_path, os.X_OK):
            return True

        # Get simv modification time
        simv_mtime = os.path.getmtime(simv_path)

        # Check source files
        source_files = self._get_source_files()
        for src_file in source_files:
            if os.path.exists(src_file):
                if os.path.getmtime(src_file) > simv_mtime:
                    return True

        return False

    def _get_source_files(self) -> List[str]:
        """Get list of source files to check for changes.

        Returns:
            List of source file paths
        """
        source_files = []

        # Check for common source file patterns
        patterns = ['*.v', '*.sv', '*.vh', '*.svh', '*.f']

        # Search in common directories
        search_dirs = ['.', 'rtl', 'tb', 'bench', 'src', 'verif']

        for search_dir in search_dirs:
            dir_path = os.path.join(self.work_dir, search_dir)
            if os.path.exists(dir_path):
                for pattern in patterns:
                    for ext in ['v', 'sv', 'vh', 'svh']:
                        pattern_path = os.path.join(dir_path, f'*.{ext}')
                        # Use glob to find files
                        import glob
                        source_files.extend(glob.glob(pattern_path))

        # Also check file lists
        for flist in ['rtl.f', 'tb.f']:
            flist_path = os.path.join(self.work_dir, flist)
            if os.path.exists(flist_path):
                source_files.append(flist_path)

        return source_files

    def compile_mode(self, mode: str) -> CompileResult:
        """Compile a simulation mode.

        Args:
            mode: Simulation mode

        Returns:
            CompileResult object
        """
        start_time = datetime.now()
        simv_path = self.get_simv_path(mode)

        # Create mode-specific result directory
        mode_result_dir = os.path.join(self.result_dir, mode)
        os.makedirs(mode_result_dir, exist_ok=True)

        log_path = os.path.join(mode_result_dir, f"compile_{mode}.log")

        # Build compile command
        cmd = self._build_compile_command(mode)

        self.logger.info("Compile: %s", ' '.join(cmd))

        try:
            # Execute compilation
            with open(log_path, 'w', encoding='utf-8') as log_file:
                result = subprocess.run(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    cwd=self.work_dir,
                    timeout=self.config.timeout_seconds * 2  # Allow more time for compilation
                )

            duration = (datetime.now() - start_time).total_seconds()

            if result.returncode == 0:
                self.compiled_modes.add(mode)
                return CompileResult(
                    mode=mode,
                    success=True,
                    log_path=log_path,
                    simv_path=simv_path,
                    duration=duration
                )
            else:
                return CompileResult(
                    mode=mode,
                    success=False,
                    log_path=log_path,
                    simv_path=simv_path,
                    duration=duration,
                    error_message=f"Compilation failed with exit code {result.returncode}"
                )

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            return CompileResult(
                mode=mode,
                success=False,
                log_path=log_path,
                simv_path=simv_path,
                duration=duration,
                error_message=f"Compilation timed out after {self.config.timeout * 2}h"
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            return CompileResult(
                mode=mode,
                success=False,
                log_path=log_path,
                simv_path=simv_path,
                duration=duration,
                error_message=str(e)
            )

    def build_compile_command(self, mode: str) -> List[str]:
        """Build compile command for a mode.

        Public method for dry-run mode support.

        Args:
            mode: Simulation mode

        Returns:
            List of command arguments
        """
        # Use Makefile from current directory
        cmd = ['make', '-f', 'Makefile', 'compile']

        # Add mode
        cmd.append(f'mode={mode}')

        # Add result directory (mode-specific)
        mode_result_dir = os.path.join(self.result_dir, mode)
        cmd.append(f'RESULT_DIR={mode_result_dir}')

        # Add simv name
        cmd.append(f'SIMV_NAME=simv_{mode}')

        # Add coverage arguments if enabled
        if self.config.coverage:
            cmd.append(f'COV_ARGS={self.config.coverage_args}')
            cmd.append('cov=1')
        else:
            cmd.append('cov=0')

        # Add global arguments
        if self.config.global_args:
            cmd.extend(self.config.global_args.split())

        return cmd

    # Keep backward compatibility alias
    _build_compile_command = build_compile_command

    def compile_all_modes(self, modes: List[str], force: bool = True) -> List[CompileResult]:
        """Compile all required modes.

        Args:
            modes: List of modes to compile
            force: Force recompilation (default True to avoid version mismatch)

        Returns:
            List of CompileResult objects
        """
        results = []

        for mode in modes:
            # Default behavior: always recompile to avoid version mismatch
            # Only check cache when force=False (not used by default)
            need_compile = force or self.need_recompile(mode)

            if need_compile:
                self.logger.info("Compiling mode: %s", mode)
                result = self.compile_mode(mode)
                results.append(result)

                if not result.success:
                    self.logger.error("Compilation failed for %s: %s", mode, result.error_message)
                else:
                    self.logger.info("Compilation success for %s (%.1fs)", mode, result.duration)
            else:
                self.logger.info("Using cached simv for mode: %s", mode)
                self.compiled_modes.add(mode)
                results.append(CompileResult(
                    mode=mode,
                    success=True,
                    log_path="",
                    simv_path=self.get_simv_path(mode),
                    duration=0.0
                ))

        return results

    def get_all_compiled(self) -> bool:
        """Check if all modes are successfully compiled.

        Returns:
            True if all required modes are compiled
        """
        return len(self.compiled_modes) > 0