"""Enable ``python -m bis_rag …`` as an alias for the ``bis-rag`` command."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
