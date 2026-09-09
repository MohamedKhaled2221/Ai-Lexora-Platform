"""
Shared pytest configuration.

The test suite must not depend on the developer's local .env
security configuration.

FastAPI TestClient uses the host "testserver", so normal unit/API
tests run with development security defaults unless a test explicitly
supplies its own APISecuritySettings.
"""

import os


os.environ["API_ENVIRONMENT"] = "development"
os.environ["API_TRUSTED_HOST_ENFORCEMENT"] = "false"
