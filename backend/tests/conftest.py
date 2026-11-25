"""Pytest configuration and shared fixtures."""
import os
import sys
from pathlib import Path
import pytest

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set test environment defaults before importing app modules
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JOBVETTA_API_KEY", "test_key_not_real")
os.environ.setdefault("OPENAI_API_KEY", "")
