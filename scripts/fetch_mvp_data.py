#!/usr/bin/env python3
"""Ponto de entrada executável, independente do diretório corrente."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earth_detectives.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
