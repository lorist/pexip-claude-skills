# Classification Lifecycle Reference

Complete token lifecycle, cross-worker coordination, and recalculation patterns
for conference classification via the Pexip Client API.

---

## Architecture Overview

Conference classification works by:

1. A "Policy Server" participant joins the conference via Client API `request_token`
2. This participant holds a chair-role token used to set classification metadata
3. The classification level is `min(admitted_participant_levels)`
4. As participants join/leave, the level is recalculated via `set_classification_level`
5. A keepalive thread refreshes the token every 60s to prevent expiry

State is stored in a separate SQLite database (`/tmp/conference_state.db`), NOT in
the main application database. This isolates volatile conference state from
persistent configuration.

---

## Token Lifecycle

### Step 1: request_token

Creates a new visible participant in the conference roster. Returns a token for
subsequent Client API calls.

```python
from services.client_api import request_token

token, err = request_token(conf_fqdn, conference_alias, pin=pin)
if token:
    # Store token + timestamp in conference state
    update_conference(alias, token=token, token_time=time.time())
else:
    logger.warning("request_token failed: %s", err)
```

**Warning:** Every `request_token` call creates a NEW "Policy Server" participant.
If you call it twice without releasing the first token, the meeting roster shows
two Policy Server entries.

### Step 2: refresh_token (every 60s)

Lightweight token renewal that does NOT create a new participant:

```python
from services.client_api import refresh_token

new_token = refresh_token(conf_fqdn, conference_alias, old_token)
if new_token:
    update_conference(alias, token=new_token, token_time=time.time())
```

### Step 3: release_token

Cleanly disconnects the Policy Server participant:

```python
from services.client_api import release_token

release_token(conf_fqdn, conference_alias, token)
```

Safe to call even when the token is already expired -- returns False silently.

---

## apply_classification() Pattern

The initial classification trigger when the first IdP participant joins:

```python
def apply_classification(conf_fqdn, alias, level, pin="", meeting_subject=""):
    """Join as Policy Server participant and set initial classification level.

    Returns (True, token) on success or (False, error_message) on failure.
    """
    token, err = request_token(conf_fqdn, alias, pin=pin)
    if not token:
        return False, err

    # Brief delay for Pexip to register the participant
    time.sleep(1.5)

    ok = set_classification_level(conf_fqdn, alias, level, token)
    if not ok:
        return False, "set_classification_level failed"

    if meeting_subject:
        send_message(conf_fqdn, alias, meeting_subject, token)

    return True, token
```

---

## Token Refresh Fallback Chain

Minimize "token churn" (each new token creates a Policy Server participant).
Use a 4-step fallback:

```python
def get_or_refresh(self, conference_alias, pin=None):
    cached_token, age = self.tokens.get(conference_alias)

    # Step 1: Reuse young cached token
    if cached_token and age < self.TOKEN_VALID_MAX:
        return cached_token

    # Step 2: Refresh (does NOT create a new PS participant)
    if cached_token:
        new_token = refresh_token(conference_alias, cached_token)
        if new_token:
            self.tokens.set(conference_alias, new_token)
            return new_token

    # Step 3: Validate old token via get_participants
    if cached_token:
        participants = get_participants(conference_alias, cached_token)
        if participants is not None:
            self.tokens.set(conference_alias, cached_token)  # renew timestamp
            return cached_token

    # Step 4: Request new token (last resort — creates new PS participant)
    token, err = request_token(conference_alias, pin=pin)
    if token:
        self.tokens.set(conference_alias, token)
    return token
```

**After requesting a new token, wait 1.5s** before calling
`set_classification_level` — the new PS participant needs time to be admitted
as chair. Without the delay, you get 403 "Invalid role":

```python
if not was_cached:
    time.sleep(1.5)
```

Retry backoff differs by error type:
- **Invalid token / 500**: `sleep(0.5 * (attempt + 1))` — 0.5s, 1s, 1.5s
- **Invalid role (PS still joining)**: `sleep(1.5 * (attempt + 1))` — 1.5s, 3s, 4.5s

**Never disconnect duplicate Policy Server participants after token refresh.**
Disconnecting ANY PS participant can invalidate the token bound to it, causing
a cascade: 403 → new token → new duplicate → disconnect → 403. Duplicates are
harmless and clean up when the conference ends. **(field-tested)**

---

## Early Classification

Don't wait for the event sink `participant_updated` — set the meeting
classification level immediately in the `participant_properties` response
path (the first moment you know a participant's level):

```python
if (is_idp_authenticated and not is_pexipdemo
        and not _is_breakout(alias) and classification_level is not None):
    if not flag_cache.is_set(alias, "early_classification"):
        flag_cache.set(alias, "early_classification")
        classification_mgr.update_level(alias, classification_level)
```

The flag ensures this fires only once per conference. Without early
classification, there's a several-second delay while waiting for the
event sink round-trip. **(field-tested)**

---

## Conference Generation Counter

A conference can end and restart with the same alias. Use a SQLite-based
generation counter to prevent stale cleanup threads from clearing caches
that a restarted conference is actively using:

```python
# Schema
# CREATE TABLE conference_generation (
#     conference_alias TEXT PRIMARY KEY,
#     generation INTEGER NOT NULL DEFAULT 0
# );

# On conference_started — increment generation (UPSERT)
conn.execute(
    "INSERT INTO conference_generation (conference_alias, generation) VALUES (?, 1) "
    "ON CONFLICT(conference_alias) DO UPDATE SET generation = generation + 1",
    (conference_alias,)
)
generation_at_start = get_generation(conference_alias)

# In cleanup thread (background, after conference_ended)
if get_generation(conference_alias) != generation_at_start:
    return  # Conference restarted — abort cleanup
```

Pair with an `_ending_conferences` set that blocks new token requests
during the cleanup window:

```python
_ending_conferences = set()

# On conference_ended:
_ending_conferences.add(conference_alias)

# In get_or_refresh():
if conference_alias in _ending_conferences:
    return cached_token  # Don't create new PS during teardown
```

Without this, cleanup operations that trigger recalculation would request
new tokens during teardown, creating ghost PS participants that keep the
conference alive. **(field-tested)**

---

## try_mark_classified() Pattern

Atomic cross-worker dedup gate. With multiple Gunicorn workers, two concurrent
IdP participant joins can race to trigger classification. Python threading locks
do NOT work across processes.

```python
import sqlite3

def try_mark_classified(alias):
    """Atomic cross-worker claim. Returns True only for the first caller.

    Uses INSERT (not INSERT OR IGNORE) so the IntegrityError tells us
    someone else already claimed this alias.
    """
    with get_state_db() as conn:
        try:
            conn.execute(
                "INSERT INTO classified_conferences (alias) VALUES (?)",
                (alias,)
            )
            return True
        except sqlite3.IntegrityError:
            return False

def unmark_classified(alias):
    """Release the classification claim (conference ended or classify failed)."""
    with get_state_db() as conn:
        conn.execute(
            "DELETE FROM classified_conferences WHERE alias = ?", (alias,)
        )
```

The `classified_conferences` table has a UNIQUE constraint on `alias`. The
IntegrityError on duplicate insert is the atomic gate.

---

## _refresh_token_if_needed() Code

```python
def _refresh_token_if_needed(conference_alias):
    """Proactively refresh the Client API token if older than 60 seconds.

    Uses refresh_token (lightweight) first, falls back to request_token
    only if refresh fails.
    """
    state = get_conference(conference_alias)
    if not state:
        return None

    token = state.get("token")
    conf_fqdn = state.get("conf_fqdn", "")
    pin = state.get("pin", "")
    token_time = state.get("token_time", 0)

    if not token or not conf_fqdn:
        return None

    age = time.time() - token_time
    if age > 60:
        # Try lightweight refresh first
        new_token = refresh_token(conf_fqdn, conference_alias, token)
        if new_token:
            update_conference(conference_alias, token=new_token, token_time=time.time())
            return new_token

        # Refresh failed -- release old PS participant, request new token
        _release_stale_ps_participant(conf_fqdn, conference_alias, token)
        new_token, err = request_token(conf_fqdn, conference_alias, pin=pin)
        if new_token:
            time.sleep(1.5)
            update_conference(conference_alias, token=new_token, token_time=time.time())
            return new_token
        else:
            return token  # Return stale token as last resort

    return token
```

---

## _release_stale_ps_participant() Code

```python
def _release_stale_ps_participant(conf_fqdn, conference_alias, old_token):
    """Disconnect the old Policy Server participant before creating a new one.

    Prevents duplicate "Policy Decission Point Server" entries in the roster.
    Safe to call even when old_token is already expired.
    """
    if not conf_fqdn or not old_token:
        return
    try:
        release_token(conf_fqdn, conference_alias, old_token)
    except Exception:
        pass  # Best-effort cleanup
```

---

## Recalculation Flow

Triggered when a participant is admitted, leaves, or moves between rooms:

```python
def _recalculate_classification(conference_alias):
    """Recalculate as min(admitted participant levels).

    For main VMR: only counts participants with in_main_vmr=True.
    For breakout: counts all admitted participants.
    """
    is_breakout = _is_breakout(conference_alias)

    # Refresh token first
    token = _refresh_token_if_needed(conference_alias)

    state = get_conference(conference_alias)
    if not state or not token:
        return

    conf_fqdn = state.get("conf_fqdn", "")
    pin = state.get("pin", "")

    # Get admitted levels (filtered by main_vmr for non-breakout)
    admitted_levels = get_admitted_levels(
        conference_alias, main_vmr_only=not is_breakout
    )

    if not admitted_levels or not conf_fqdn:
        return

    new_level = min(admitted_levels)

    ok = set_classification_level(conf_fqdn, conference_alias, new_level, token)

    if not ok:
        # Token expired -- release old, get new, retry
        _release_stale_ps_participant(conf_fqdn, conference_alias, token)
        new_token, err = request_token(conf_fqdn, conference_alias, pin=pin)
        if new_token:
            time.sleep(1.5)
            ok = set_classification_level(conf_fqdn, conference_alias, new_level, new_token)
            if ok:
                update_conference(conference_alias, token=new_token, token_time=time.time())

    if ok:
        update_conference(conference_alias, classification_level=new_level)
```

---

## Token Keepalive Thread

Background daemon that refreshes all active conference tokens:

```python
_keepalive_thread = None
_keepalive_stop = threading.Event()

def _token_keepalive_loop():
    """Refresh tokens for all active conferences every 60s."""
    while not _keepalive_stop.is_set():
        _keepalive_stop.wait(60)
        if _keepalive_stop.is_set():
            break
        try:
            conferences = get_all_conferences()
            for alias, state in conferences.items():
                if state.get("token") and state.get("conf_fqdn"):
                    _refresh_token_if_needed(alias)
        except Exception as e:
            logger.warning("Keepalive error: %s", e)

def _start_keepalive():
    """Start the keepalive thread if not already running."""
    global _keepalive_thread
    if _keepalive_thread and _keepalive_thread.is_alive():
        return
    _keepalive_stop.clear()
    _keepalive_thread = threading.Thread(target=_token_keepalive_loop, daemon=True)
    _keepalive_thread.start()
```

Call `_start_keepalive()` after the first successful `apply_classification()`.
The thread is a daemon so it dies with the process.

---

## Conference Cleanup

When `conference_ended` fires in the event sink:

```python
if event_type == "conference_ended":
    unmark_classified(conference_alias)
    delete_conference(conference_alias)
    clear_debounce(conference_alias + ":")

    # Also clean up child breakout rooms
    if not _is_breakout(conference_alias):
        for br_alias in get_breakout_aliases(conference_alias):
            unmark_classified(br_alias)
            delete_conference(br_alias)
            clear_debounce(br_alias + ":")
```

This releases the classification claim, removes conference state, and clears
debounce entries so the alias is ready for reuse.
