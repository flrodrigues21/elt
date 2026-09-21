"""Replace OpenMetadata's initial admin password with the generated lab secret."""

from __future__ import annotations

import base64
import os

import requests

OPENMETADATA_URL = os.environ.get("OPENMETADATA_URL", "http://openmetadata-server:8585/api").rstrip(
    "/"
)
ADMIN_USERNAME = "admin@open-metadata.org"
ADMIN_PASSWORD = os.environ.get("OM_ADMIN_PASSWORD")
INITIAL_PASSWORD = "admin"


def login(password: str) -> str | None:
    encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
    response = requests.post(
        f"{OPENMETADATA_URL}/v1/users/login",
        json={"email": ADMIN_USERNAME, "password": encoded},
        timeout=30,
    )
    if response.status_code in (400, 401):
        return None
    response.raise_for_status()
    return response.json()["accessToken"]


def main() -> None:
    if not ADMIN_PASSWORD:
        raise RuntimeError("OM_ADMIN_PASSWORD is required")
    if ADMIN_PASSWORD == INITIAL_PASSWORD:
        raise RuntimeError("OM_ADMIN_PASSWORD must not use the OpenMetadata default")

    if login(ADMIN_PASSWORD):
        print("OpenMetadata admin password is already configured")
        return

    token = login(INITIAL_PASSWORD)
    if not token:
        raise RuntimeError("OpenMetadata rejected both the generated and initial admin passwords")

    response = requests.put(
        f"{OPENMETADATA_URL}/v1/users/changePassword",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "oldPassword": INITIAL_PASSWORD,
            "newPassword": ADMIN_PASSWORD,
            "confirmPassword": ADMIN_PASSWORD,
            "requestType": "SELF",
        },
        timeout=30,
    )
    response.raise_for_status()

    if not login(ADMIN_PASSWORD):
        raise RuntimeError("OpenMetadata password rotation could not be verified")
    print("OpenMetadata admin password rotated successfully")


if __name__ == "__main__":
    main()
