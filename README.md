# Pexip Claude Skills

A collection of [Claude Agent Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) for working with [Pexip Infinity](https://www.pexip.com/) and the wider Pexip platform. Each skill captures hard-won, field-tested knowledge that makes Claude meaningfully better at a specific Pexip task — without you having to re-explain context every conversation.

## What's in here

| Skill | Purpose |
|---|---|
| [`pexip-external-policy`](skills/pexip-external-policy/) | Designing and implementing Pexip Infinity External Policy servers and local Jinja2 policy scripts. Covers all six request types, ABAC patterns, breakout rooms, and common gotchas. |
| [`pexip-event-sink`](skills/pexip-event-sink/) | Building and operating Pexip Infinity Event Sink receivers — the webhook stream for conference and participant lifecycle events. Covers the wire protocol, the operational patterns (idempotency, fast ACK, durable persistence, replay), and common integrations (CDR/billing, BI, real-time dashboards). |
| [`pexip-call-rca`](skills/pexip-call-rca/) | Root cause analysis for Pexip Infinity call failures from Management Node and Conferencing Node logs (support snapshot, folder of per-node files, or a single log). Bundles a log parser plus reference material on SIP, WebRTC, and Pexip-specific failure patterns. |
| [`pexip-management-api`](skills/pexip-management-api/) | Working with the Pexip Infinity Management Node REST API (`/api/admin/{configuration,status,command,history}/v1/`). Ships the full schema for all 154 resources as searchable markdown so Claude can write correct payloads without guessing field names; covers auth, bulk PATCH, rate limits, and the gotchas around DELETE/PUT on list URIs. |
| [`pexip-client-api`](skills/pexip-client-api/) | Building applications against the Pexip Infinity Client REST API (`/api/client/v2/conferences/<alias>/…`) — the token-based HTTP+SSE protocol every endpoint and bot uses to join a meeting. Covers the `request_token`/`refresh_token` lifecycle, the `/events` SSE stream and its `participant_sync_*` bracket, WebRTC negotiation via `/calls` (transcoded vs direct media), breakouts, host vs guest control, and the operational patterns (refresh cadence, reconnect, idempotency) the docs leave implicit. |
| [`pexip-js-sdks`](skills/pexip-js-sdks/) | Choosing between, and building with, the two JS SDK families that sit on top of the Client API: the legacy `pexrtc.js` browser wrapper and the modern `@pexip/*` npm packages (`@pexip/infinity`, `@pexip/media`, `@pexip/components`, etc.). Decision tree, full PexRTC reference, the `@pexip/signal` deep-dive, the media-pipeline composition rules, and runnable examples for both stacks. |
| [`pexip-webapp3-plugin`](skills/pexip-webapp3-plugin/) | Building, packaging, and deploying Pexip Infinity webapp3 plugins with `@pexip/plugin-api` — the sandboxed iframe extensions that add buttons, toasts, and side panels to the stock meeting UI. Covers the plugin SDK (registration, events, UI primitives, `sendRequest`), the Vite project scaffold, the branding ZIP / `manifest.json` structure, uploading via the Management API, webapp alias routing, and 22 production-tested gotchas. |
| [`pexip-infinity-debugging`](skills/pexip-infinity-debugging/) | Problem-oriented debugging playbook for **live** Pexip Infinity deployments — symptom → log source → search term → fix. Covers external policy debugging (silent 404, response validation, PIN rejection), event sink delivery issues, classification state problems, IdP/SAML auth failures, and infrastructure quirks (config replication, licensing, ngrok). Pair with `pexip-call-rca` for downloaded log archives. |
| [`pexip-policy-server`](skills/pexip-policy-server/) | Production patterns for building and operating Pexip Infinity External Policy servers with participant classification, access control, and conference lifecycle management. Covers `service_configuration` and `participant_properties` response validation, classification levels and role ladders (chair/guest/bypass_lock), `avatar_request` JPEG handling (Keycloak), Client-API-driven conference classification, event-sink integration for admission and breakout migration, and 40 production-tested gotchas. The advanced companion to `pexip-external-policy`. |
| _(more to come)_ | |

## What is a Claude Skill?

A skill is a folder containing a `SKILL.md` (with YAML frontmatter describing when to trigger it) plus optional reference files and scripts. Claude consults relevant skills automatically based on the conversation. Skills work with:

- **Claude Code** (CLI) — drop the skill into `~/.claude/skills/<skill-name>/` or `<project>/.claude/skills/<skill-name>/`
- **Claude.ai apps** (Pro/Max/Team/Enterprise) — upload a packaged `.skill` file via Settings → Capabilities → Skills
- **Claude API / Agent SDK** — load via the code execution tool

The format is plain markdown plus YAML frontmatter — portable, reviewable, and version-controllable.

## Installation

### Install all skills (recommended)

Clone the repo and run the install script:

```bash
git clone https://github.com/lorist/pexip-claude-skills.git
cd pexip-claude-skills
./scripts/install.sh
```

This copies every skill in `skills/` to `~/.claude/skills/`, making them available in Claude Code immediately. Override the destination with `CLAUDE_SKILLS_DIR=/custom/path ./scripts/install.sh`.

### Install a single skill

```bash
./scripts/install-one.sh pexip-external-policy
```

### Install for Claude.ai (web/desktop)

Build packaged `.skill` files and upload them via the Claude.ai settings:

```bash
./scripts/package.sh                # outputs dist/<skill-name>.skill for every skill
```

Then in Claude.ai: **Settings → Capabilities → Skills → Upload skill** and pick the `.skill` file. (Available on Pro / Max / Team / Enterprise plans.)

### Manual install (no script)

A skill is just a folder. Copy it into your skills directory:

```bash
cp -r skills/pexip-external-policy ~/.claude/skills/
```

Or, for active development against a single machine, symlink it:

```bash
ln -s "$(pwd)/skills/pexip-external-policy" ~/.claude/skills/pexip-external-policy
```

Symlinking means `git pull` instantly updates the installed skill.

## Using a skill in Claude Code

Once installed, you can invoke a skill two ways.

### Just ask — Claude picks it up automatically

Each skill's `SKILL.md` declares the topics it covers in its frontmatter `description`. Natural prompts on a relevant topic pull the skill in without any ceremony:

> "Help me build a FastAPI policy server that overrides participant roles based on IdP groups."

> "What's the correct response shape for a Pexip breakout room?"

> "My `media_location` response isn't being applied — what should I check?"

Claude reads the relevant `SKILL.md` plus any `references/` files it needs and answers with field-accurate guidance.

### Invoke explicitly with a slash command

To force-load a skill at the start of a turn — useful when the topic isn't obvious from the prompt, or when you want to make sure Claude is grounded in the skill before you start — type the skill name as a slash command:

```
/pexip-external-policy create a sample external policy server that rejects calls from unauthenticated IdP groups
```

Claude loads the skill and treats the rest of your message as the request.

### Confirming a skill is installed

```bash
ls ~/.claude/skills/
```

You should see one directory per installed skill, each containing a `SKILL.md`.

### Worked end-to-end examples

For complete builds — code, README, and a case study evaluating how the skill performed during the actual build — see [`skills/pexip-external-policy/examples/`](skills/pexip-external-policy/examples/).

## Contributing a new skill

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md). Short version: copy `docs/skill-template/` into `skills/<your-skill-name>/`, fill in the SKILL.md and any references, and run `./scripts/validate.sh` before opening a PR.

## Versioning

This repo uses single-tag semantic versioning across all skills. Tagged releases (`v1.0.0`, `v1.1.0`, …) on GitHub include built `.skill` files as release assets for easy distribution to non-developers.

## Licence

[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — free to share and adapt for non-commercial use, with attribution. See [`LICENSE`](LICENSE) for the full notice.

## Acknowledgements

These skills are distilled from real-world Pexip deployments — production policy servers, ABAC enforcement, Webapp3 plugins, partner integrations, and a lot of trial and error. If you find a gap, please open an issue or PR.
