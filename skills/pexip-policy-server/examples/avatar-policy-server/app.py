"""Minimal Flask avatar policy server for Pexip Infinity v40+.

Demonstrates:
- /policy/v1/participant/avatar/<alias> endpoint
- User lookup by idp_uuid (stubbed to in-memory dict)
- Base64 decode -> PIL -> JPEG conversion at exact requested dimensions
- Proper Content-Type: image/jpeg + Cache-Control
- 404 handling (Pexip caches 404s per session)
"""

import base64
import io
import logging
import re

from flask import Flask, Response, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("avatar-server")

# Stubbed user database — in production, look up from Keycloak or another IdP.
# Keys: idp_uuid or username. Values: base64-encoded image data.
# Generate test data: base64.b64encode(open("photo.jpg", "rb").read()).decode()
USERS = {
    "user-001": {
        "name": "Heidi Smith",
        # Tiny 1x1 red JPEG as placeholder (replace with real base64 photo)
        "avatar_b64": (
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP/////////////////////////////////"
            "//////////////////////wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAB//EABQQAQAA"
            "AAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AN//Z"
        ),
    },
}


@app.route("/policy/v1/participant/avatar/<path:alias>", methods=["GET"])
def participant_avatar(alias):
    """Serve participant avatar as JPEG.

    Pexip v40+ avatar_request endpoint. Returns image/jpeg at the exact
    requested dimensions, or 404 (which Pexip caches per session).
    """
    try:
        idp_uuid = request.args.get("idp_uuid", "").strip()
        remote_display_name = request.args.get("remote_display_name", "").strip()

        try:
            width = int(request.args.get("width", "256"))
            height = int(request.args.get("height", "256"))
        except ValueError:
            width = height = 256

        # Extract username from alias (strip scheme prefix and domain)
        alias_user = re.sub(r"^[a-zA-Z0-9+.\-]+:", "", alias).split("@")[0]

        # Look up user — try idp_uuid first, then alias username
        user = None
        if idp_uuid and idp_uuid in USERS:
            user = USERS[idp_uuid]
        elif alias_user and alias_user in USERS:
            user = USERS[alias_user]

        if not user or not user.get("avatar_b64"):
            logger.info("No avatar for alias=%s uuid=%s", alias, idp_uuid)
            return ("", 404)  # Pexip caches this per session

        # Decode base64 -> PIL Image -> RGB -> resize -> JPEG
        from PIL import Image

        raw_bytes = base64.b64decode(user["avatar_b64"])
        img = Image.open(io.BytesIO(raw_bytes))
        img = img.convert("RGB")  # MUST be RGB, not RGBA
        img = img.resize((width, height), Image.LANCZOS)  # MUST match exact dimensions

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)  # MUST be JPEG, not PNG

        logger.info("Serving avatar for %s (%dx%d)", user.get("name", alias), width, height)

        return Response(
            buf.getvalue(),
            mimetype="image/jpeg",
            headers={"Cache-Control": "public, max-age=300"},
        )

    except Exception as e:
        logger.exception("Avatar error for alias=%s: %s", alias, e)
        return ("", 404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
