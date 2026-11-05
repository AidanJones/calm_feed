import os
import sys
import tempfile
from pathlib import Path

# Must be set before calmfeed.config is imported.
os.environ["CALM_DATA_DIR"] = tempfile.mkdtemp(prefix="calmfeed-test-")
os.environ["GOOGLE_CLIENT_ID"] = "test-client"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
