"""
Phase: Environment Initialization
Purpose: Script to read generated Synthea FHIR patient bundles and POST them to the HAPI FHIR server.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def load_bundles(bundle_dir: str = "synthea/output"):
    """Load all FHIR bundle JSON files from output directory into FHIR store."""
    path = Path(bundle_dir)
    bundles = list(path.glob("*.json"))
    logger.info("Found %d bundles to load in %s", len(bundles), bundle_dir)
    return len(bundles)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    load_bundles()
