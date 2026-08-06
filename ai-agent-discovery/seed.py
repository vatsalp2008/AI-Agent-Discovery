import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from logging_setup import configure
from scraper import CatalogueError, seed_data

if __name__ == '__main__':
    configure()
    try:
        # --append keeps the existing index and adds on top of it; the default
        # rebuilds so repeated runs stay idempotent.
        seed_data(rebuild='--append' not in sys.argv)
    except CatalogueError as e:
        # The message already says which file and entry is at fault; a
        # traceback through json internals would only bury it.
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
