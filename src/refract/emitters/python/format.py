from __future__ import annotations

import subprocess

from refract.emitters.api import Formatter

_STDIN_NAME = "generated.py"


class RuffFormatter(Formatter):
    """The ruff post-pass authority: sort imports (rule I), then format."""

    def format(self, source: str) -> str:
        sorted_imports = self._run(
            ["ruff", "check", "--select", "I", "--fix", "--stdin-filename", _STDIN_NAME, "-"],
            source,
        )
        return self._run(["ruff", "format", "--stdin-filename", _STDIN_NAME, "-"], sorted_imports)

    @staticmethod
    def _run(cmd: list[str], source: str) -> str:
        try:
            result = subprocess.run(cmd, input=source, capture_output=True, text=True, check=True)
        except FileNotFoundError as error:  # ruff missing from PATH
            raise RuntimeError("ruff not found on PATH") from error
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"ruff failed ({' '.join(cmd)}):\n{error.stderr}") from error
        return result.stdout
