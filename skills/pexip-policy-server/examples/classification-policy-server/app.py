"""Minimal Flask policy server with classification and role ladder.

Demonstrates:
- /policy/v1/service/configuration with PIN validation and view normalization
- /policy/v1/participant/properties with classification levels, role ladder, rejection
- Alias normalization, breakout room stripping, response helpers
"""

import logging
from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("policy-server")

# --- Configuration (hardcoded for demo; use DB/env in production) ---

CONFERENCE_PIN = "1234"

CLASSIFICATION_MAP = {
    "private": 1,
    "corporal": 2,
    "sergeant": 3,
    "captain": 4,
    "colonel": 5,
    "general": 6,
}

AUTO_ADMIT_MIN_LEVEL = 6  # L6+ auto-admitted as chair
L1_REJECTION_THRESHOLD = 3  # L1-L3 rejected when meeting is above their level

# Simulated meeting state (use SQLite in production)
_meeting_levels = {}  # alias -> current classification level

# --- Helpers ---

_VALID_VIEWS = frozenset({
    "one_main_zero_pips", "one_main_seven_pips", "one_main_twentyone_pips",
    "two_mains_twentyone_pips", "four_mains_zero_pips", "nine_mains_zero_pips",
    "sixteen_mains_zero_pips", "twentyfive_mains_zero_pips",
    "one_main_thirtythree_pips", "one_main_twelve_around",
    "two_mains_eight_around", "one_main_nine_around",
    "one_main_twentyone_around", "five_mains_seven_pips",
})
_VIEW_ALIASES = {"ac": "five_mains_seven_pips", "carousel": "one_main_twentyone_pips"}


def _normalize_alias(alias):
    """Strip SIP URI: 'sip:name@domain' -> 'name'."""
    if alias.startswith("sip:"):
        alias = alias[4:]
    if "@" in alias:
        alias = alias.split("@")[0]
    return alias


def _normalize_view(view):
    """Map to a valid Infinity view value or default."""
    if not view:
        return "one_main_twentyone_pips"
    if view in _VALID_VIEWS:
        return view
    return _VIEW_ALIASES.get(view, "one_main_twentyone_pips")


def _is_breakout(alias):
    if not alias:
        return False
    s = alias.lower()
    return "_breakout_" in s or s.startswith("breakout_") or s.endswith("_breakout")


def _json_ok(result):
    """Successful policy response. NEVER use for rejections."""
    return jsonify({"status": "success", "action": "continue", "result": result})


def _json_passthrough():
    """Empty pass-through — Pexip uses its local config."""
    return jsonify({"status": "success", "action": "continue", "result": {}})


# --- Routes ---

@app.route("/policy/v1/service/configuration", methods=["GET", "POST"])
def service_configuration():
    local_alias = _normalize_alias(request.args.get("local_alias", ""))
    remote_alias = request.args.get("remote_alias", "")

    if not local_alias:
        return _json_passthrough()

    is_policy_server = remote_alias in ("Policy Server", "PDP Connectivity Test")
    is_breakout = _is_breakout(local_alias) or _is_breakout(
        request.args.get("unique_service_name", "")
    )

    result = {
        "service_type": "conference",
        "name": local_alias,
        "local_alias": local_alias,
        "service_tag": "classification-demo",
        "enable_overlay_text": True,
        "view": _normalize_view("ac"),
        "non_idp_participants": "allow_if_trusted",
    }

    if is_breakout:
        # Breakout: no PIN, no allow_guests (rule #1 and #4)
        result["locked"] = False
    else:
        result["allow_guests"] = True
        result["locked"] = True
        result["pin"] = CONFERENCE_PIN

    logger.info("service_config: alias=%s ps=%s breakout=%s", local_alias, is_policy_server, is_breakout)
    return _json_ok(result)


@app.route("/policy/v1/participant/properties", methods=["GET", "POST"])
@app.route("/policy/v1/participant", methods=["GET", "POST"])
def participant_properties():
    local_alias = _normalize_alias(request.args.get("local_alias", ""))
    remote_alias = request.args.get("remote_alias", "")
    remote_display_name = request.args.get("remote_display_name", "")

    if not local_alias:
        return _json_passthrough()

    # --- Tier 1: Policy Server participant (MUST be first) ---
    is_ps = remote_alias in ("Policy Server", "PDP Connectivity Test") or \
            "policy" in (remote_display_name or "").lower()
    if is_ps:
        logger.info("Policy Server participant on '%s' -> chair + bypass", local_alias)
        return _json_ok({
            "preauthenticated_role": "chair",
            "bypass_lock": True,
            "remote_display_name": "Policy Server",
        })

    # --- Extract IdP attributes ---
    body = request.get_json(silent=True) or {}
    idp_attributes = body.get("idp_attributes", {})
    if not isinstance(idp_attributes, dict):
        idp_attributes = {}

    title = idp_attributes.get("title", "") or idp_attributes.get("Title", "")
    if isinstance(title, list):
        title = title[0] if title else ""
    title = str(title).strip()

    first_name = idp_attributes.get("firstName", "")
    if isinstance(first_name, list):
        first_name = first_name[0] if first_name else ""
    last_name = idp_attributes.get("lastName", "")
    if isinstance(last_name, list):
        last_name = last_name[0] if last_name else ""

    idp_uuid = request.args.get("idp_uuid", "")
    has_idp = bool(idp_uuid or idp_attributes)

    # --- Classification level ---
    level = CLASSIFICATION_MAP.get(title.lower(), 0) if title else 0

    # --- Tier 2 + 3: IdP participants ---
    if has_idp and level > 0:
        # Check L1 rejection threshold
        current_meeting_level = _meeting_levels.get(local_alias)
        if level <= L1_REJECTION_THRESHOLD and current_meeting_level and level < current_meeting_level:
            logger.warning("REJECT L%d '%s': meeting at L%d", level, remote_display_name, current_meeting_level)
            # MUST use bare jsonify, NOT _json_ok
            return jsonify({
                "status": "success",
                "action": "reject",
                "result": {"reject_reason": "Insufficient clearance for this meeting"},
            })

        # Build display name
        name = f"{first_name} {last_name}".strip() or remote_display_name
        display = f"{name} | {title.title()} (L{level})" if title else f"{name} | L{level}"

        result = {
            "service_tag": f"level-{level}",
            "remote_display_name": display,
            "overlay_text": f"L{level}",
        }

        if level >= AUTO_ADMIT_MIN_LEVEL:
            result["preauthenticated_role"] = "chair"
            result["bypass_lock"] = True
        else:
            result["preauthenticated_role"] = "guest"

        # Breakout: always bypass lock
        if _is_breakout(request.args.get("unique_service_name", "")) or _is_breakout(local_alias):
            result["bypass_lock"] = True

        # Track for classification (simplified — use SQLite in production)
        _meeting_levels.setdefault(local_alias, level)

        logger.info("IdP participant L%d '%s' on '%s' -> %s", level, display, local_alias, result.get("preauthenticated_role"))
        return _json_ok(result)

    # --- Tier 4: Non-IdP (SIP/PSTN) — passthrough preauthenticated_role ---
    logger.info("Non-IdP participant '%s' on '%s' -> passthrough", remote_alias, local_alias)
    return _json_passthrough()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
