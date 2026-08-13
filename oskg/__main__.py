"""`python3 -m oskg` — the same entry point as the `oskg` script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
