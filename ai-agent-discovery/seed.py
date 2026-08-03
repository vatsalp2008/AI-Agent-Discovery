import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from logging_setup import configure
from scraper import seed_data

if __name__ == '__main__':
    configure()
    seed_data()
