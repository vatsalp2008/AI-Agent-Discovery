import sys
import os

# Add backend to path
sys.path.append(os.path.abspath('backend'))

from scraper import seed_data

if __name__ == '__main__':
    seed_data()
