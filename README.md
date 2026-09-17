# Hermes Talk

**Realtime duplex voice for your own agent — talk to it, it runs real work in the background, it reports back out loud.**

<p>
  <a href="https://github.com/TheSmokeDev/hermes-talk/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/TheSmokeDev/hermes-talk/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/TheSmokeDev/hermes-talk/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://github.com/TheSmokeDev/hermes-talk/actions/workflows/codeql.yml/badge.svg"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/TheSmokeDev/hermes-talk"><img alt="OpenSSF Scorecard" src="https://api.scorecard.dev/projects/github.com/TheSmokeDev/hermes-talk/badge"></a>
  <a href="https://pypi.org/project/hermes-talk/"><img alt="PyPI" src="https://img.shields.io/pypi/v/hermes-talk?cacheSeconds=3600"></a>
  <a href="https://pypi.org/project/hermes-talk/"><img alt="PyPI downloads" src="https://img.shields.io/pypi/dw/hermes-talk"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-16a34a"></a>
</p>

Hermes Talk is a realtime voice plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent): you speak, it answers out loud, and it calls the agent's own tools without leaving the conversation. It runs in the terminal (`hermes talk`), in a Discord voice channel (`/talk join`), and in the Hermes dashboard **Talk** tab.

**It rides your ChatGPT or SuperGrok subscription. No API key required.**

The realtime lanes are **OpenAI Realtime** (`gpt-realtime-2.1`, on your ChatGPT subscription through `codex login`), **xAI Grok Voice** (on an X Premium or SuperGrok login, no key), and **Gemini Live** (which does need a `GEMINI_API_KEY` — free-tier AI Studio keys work); **GPT-Live** is selected separately by `TALK_VOICE_MODE=live` and runs `gpt-live-1-codex` on the Codex subscription or `gpt-live-1` on explicitly chosen API billing.

Talk calls the host's tools, delegates background work while you keep talking, reports results, and handles current approval requests. Provider support differs by surface; see the tables below.

**What it is:** a plug-in that adds interruptible, duplex speech-to-speech voice to an
existing Hermes Agent install — one bidirectional audio session in which the agent uses
its real tools, hands work to background agents, and speaks the results when they land.

**Who it is for:** people already running Hermes Agent who would rather talk to it than
type at it, and who want to keep talking while it works. It is not a standalone
assistant, and it does not replace Hermes's built-in turn-based voice mode — that is a
different shape, and a good one.

<!-- Regenerate this GIF (needs ffmpeg): python docs/render-dashboard-gif.py -->
![The Talk tab in the Hermes dashboard — a live voice session, a background agent delegated mid-conversation, its result landing in the runs panel (8× speed)](docs/dashboard.gif)

### 🔊 [Watch the 2:27 cut with sound](https://github.com/TheSmokeDev/hermes-talk/releases/download/v0.3.0/hermes-talk-dashboard-cut.mp4) — delegate, keep talking, hear the result land.

*Real Realtime session, 8× speed in the GIF, recorded at v0.3.0. It does not demonstrate the new GPT-Live or Codex-worker integration.*

## Install

```bash
hermes plugins install TheSmokeDev/hermes-talk --enable
pip install "hermes-talk[audio]"   # mic + speaker support (sounddevice); skip if dashboard-only
```

Needs Python ≥ 3.11 and a Hermes host ≥ v0.17. GPT-Live, shared task attachment
and Codex workers need additional host capabilities; the full list is in
[Prerequisites](docs/OPERATING.md#prerequisites).

## Quickstart

**Terminal** — start here:

```bash
hermes talk
```

You are live: speak, and it answers out loud in the same breath. Ctrl+C hangs
up. → [Use](docs/OPERATING.md#use)

**Discord** — the call happens inside a voice channel, not in chat:

```
/voice join     # put Hermes in the voice channel first
/talk join      # Talk borrows that connection — it never opens a second one
```

Talk answers in the room everyone can hear; `/talk leave` ends it. Mutating
tools stay denied until you set `TALK_DISCORD_OPERATOR_USER_IDS`.
→ [Discord voice](docs/OPERATING.md#discord-voice--talking-in-the-channel-hermes-is-already-in)

**Dashboard** — browser audio, no local mic drivers:

```bash
hermes dashboard    # then open the Talk tab and hit Start
```

Allow the microphone and talk. You see the live transcript plus a list of
background runs. → [Dashboard tab](docs/OPERATING.md#dashboard-tab)

## New in 0.20.0

- A floating Talk panel shared by the dashboard tab and the Desktop Talk view, with a runtime that survives collapsing the controls and browsing other tasks.
- `POST /text/input` and a `textInput` descriptor on `GET /status`: one authenticated route for explicit operations from the panel.
- Live replay — `POST /live/speech` with `replay:true` re-announces a terminal result into the exact bound Live session.
- `POST /native/attach` accepts `input_mode:"typed"` for microphone-off use that mints no voice credentials, plus read-only recipient catalog, history, status and selection routes.
- Result presentation across transports: result ready, context submitted, playback started, playback finished, interrupted and unknown stay separate facts; native terminal and Discord gain `/replay EVENT_ID`.
- Talk inside the current Desktop conversation, plug-and-play: open a conversation, **Talk**, **Connect**.

Every version with its receipts: [CHANGELOG.md](CHANGELOG.md).

## Providers and billing

| Lane | How it authenticates | Default model | Surfaces |
|---|---|---|---|
| OpenAI Realtime (`TALK_PROVIDER=openai`, default) | ChatGPT subscription through `codex login`, or `TALK_OPENAI_API_KEY` / `OPENAI_API_KEY` | `gpt-realtime-2.1` | every surface |
| GPT-Live (`TALK_VOICE_MODE=live`) | `TALK_LIVE_AUTH=subscription` (the default, on the Codex subscription) or explicitly chosen `api` billing; no automatic paid fallback | `gpt-live-1-codex` (subscription) / `gpt-live-1` (API) | terminal, Discord, dashboard, Desktop — on an explicit task |
| xAI Grok Voice (`TALK_PROVIDER=grok`) | an X Premium or SuperGrok login (`hermes auth add xai-oauth`) — **no API key** — or `TALK_XAI_API_KEY` / `XAI_API_KEY` | `grok-voice-latest` | terminal + Discord |
| Gemini Live (`TALK_PROVIDER=gemini`) | `GEMINI_API_KEY` / `TALK_GEMINI_API_KEY` — free-tier AI Studio keys work | `gemini-3.1-flash-live-preview` | terminal + `hermes realtime`; Discord refuses it for now |
| Cascade voice (`TALK_VOICE_MODE=cascade`) | `TALK_ELEVENLABS_API_KEY` / `ELEVENLABS_API_KEY`, on top of the OpenAI Realtime lane | `eleven_flash_v2_5` | terminal, Discord, dashboard |

The provider knob is fail-closed and never inferred from which keys exist.
Per-lane detail and the credential order: [docs/PROVIDERS.md](docs/PROVIDERS.md).
Speaking in a voice of your own: [docs/CASCADE.md](docs/CASCADE.md).

## Surfaces

## Custom voice — the cascade lane (ElevenLabs)

Native mode speaks with the provider's own voices, and those voices are
provider-locked. Cascade mode splits the call: the realtime provider stays
the brain (listening, thinking, tools, turn-taking) and hands its answer
TEXT to a streaming ElevenLabs TTS, so the assistant speaks in any voice on
your ElevenLabs account — including a clone of your own.

```bash
TALK_VOICE_MODE=cascade \
TALK_ELEVENLABS_VOICE_ID=<your-voice-id> \
hermes talk
```

The key comes from `TALK_ELEVENLABS_API_KEY` or `ELEVENLABS_API_KEY`
(Talk-scoped wins; set-but-blank refuses), and the TTS model defaults to
`eleven_flash_v2_5` (override: `TALK_ELEVENLABS_MODEL`). To clone your own
voice, create it in ElevenLabs VoiceLab first (VoiceLab → your voice → copy
the ID); voice management stays in your ElevenLabs account, not the plugin.

The trade, stated plainly: native provider audio starts ~300–600ms after
turn end, and the cascade adds roughly one extra half-second on the FIRST
sentence (sentence chunking plus TTS first-audio, ~490ms measured) — later
sentences pipeline under playback. You trade ~0.5s of first-word latency
for your voice.

Cascade is OpenAI-only for now (it is the one provider whose text-output
mode is wired and verified — picking grok or gemini fails closed and names
the provider). Barge-in cuts the cloned voice off exactly like native:
SpeechStarted aborts the in-flight TTS stream and drains playback in the
same synchronous step, so a cancelled sentence never speaks. A TTS failure
degrades that one answer to text-only with a single logged receipt; the
call itself survives. `TALK_VOICE_MODE` is fail-closed and defaults to
`native`, which is byte-identical to the pre-cascade behavior. Doctor gains
a `cascade` check: mode, TTS provider, redacted key presence, voice-id
status — no live probe.

### OpenAI-compatible cascade TTS — self-hosted or gatewayed

`TALK_CASCADE_TTS=openai` selects the second cascade lane: one `POST
{base_url}/audio/speech` REST call per sentence chunk, instead of
ElevenLabs' stream-input socket. `openai` here names the WIRE CONTRACT,
never a vendor — any endpoint serving that shape qualifies: a self-hosted
TTS model, or a gateway such as LiteLLM in front of one.

```bash
TALK_VOICE_MODE=cascade \
TALK_CASCADE_TTS=openai \
TALK_CASCADE_OPENAI_BASE_URL=https://your-gateway/v1 \
TALK_CASCADE_OPENAI_MODEL=your-tts-model \
TALK_CASCADE_OPENAI_VOICE=your-voice-id \
hermes talk
```

The key comes from `TALK_CASCADE_OPENAI_API_KEY`, falling back to
`TALK_OPENAI_API_KEY`, then `OPENAI_API_KEY` (set-but-blank refuses on
every one of the three, same rule as every other Talk key); leaving all
three unset sends no `Authorization` header at all, which many self-hosted
endpoints expect. The response format is fixed to raw PCM (16-bit LE,
24kHz): the sink sees headerless samples, and if a gateway wraps the reply
in a WAV container anyway — as a LiteLLM gateway proxying a self-hosted
model does — the container is unwrapped to its `data` chunk before the
samples are emitted, so a 44-byte header never plays as audio and a
container that disagreed with "24kHz mono s16le" cannot corrupt the
answer. Both lanes therefore reach the same playback sink the WebSocket
lane feeds, and are interchangeable from the relay's point of view,
including barge-in (cancels whichever request is in flight) and the
one-response-degrades-to-text-only failure rule. Model and voice ids are backend-defined — this plugin does not know
or validate the set your endpoint serves.

The cascade speaks on every Talk surface:

| Surface | How the cascade speaks |
| --- | --- |
| Terminal (`hermes talk`) | The provider session opens in text-output mode; the cascade feeds the SAME playback sink the relay feeds. |
| Discord (`talk join`) | The same shared session loop; cascade PCM24k takes the relay's exact path through the 24k→48k voice-channel conversion. |
| Dashboard tab | The browser keeps its WebRTC socket but mints a text-output session and relays the model's text deltas to `POST /api/plugins/hermes-talk/cascade-tts`; the server-side cascade speaks them and streams PCM back. The ElevenLabs key never reaches the browser — the route sits behind the same `TALK_DASHBOARD_TOKEN` / loopback gate as the mint, and barge-in aborts the fetch, which cancels the TTS exactly like the terminal lane. |
| Desktop app (plugin) | The desktop lane takes one direction per door: the model's text goes up on `POST /api/plugins/hermes-talk/cascade-feed`, the PCM24k comes down on the plugin's own WebSocket twin at `/cascade-tts?stream=<id>`. A plugin cannot stream an upload (its REST door answers JSON through the app's main process) and cannot read a byte stream back, so neither direction fits the HTTP lane's single streaming POST; the two doors meet in one server-side pipeline instead of a second implementation of the chunker. `{"abort": true}` is the barge-in: the TTS is cancelled, not flushed. The socket carries `TALK_DASHBOARD_TOKEN` as `?talk_token=` because an upgrade request cannot set a header; a stream exists only while its socket does, and a dropped socket releases it. |

## Use

```bash
hermes talk       # terminal duplex voice session
hermes talk setup # detect → ask only missing decisions → confirm/write → verify
hermes talk doctor # strictly read-only configuration and host diagnostics
hermes talk check  # doctor + one live provider turn + one bounded Hermes run; exit 0 = proven
hermes talk diagnostics --bundle  # redacted support bundle for issue reports, written owner-only
```

Setup commits all individually confirmed settings to the active Hermes home's
`.env` as one secure atomic transaction and updates the current process to match.
On failure it rolls both surfaces back when possible, emits a value-free
applied/rolled-back/failed receipt, attempts and verifies every secret-bearing
temporary-file cleanup, and reruns doctor whenever a mutation may remain. Any
surviving temp is a surviving mutation: setup returns `failed` and identifies
the cleanup slot/error class without printing the path nonce or secret value.
New secret files keep POSIX `0600` behavior and receive a protected owner-only
DACL on Windows; an existing Windows destination DACL is preserved. A healthy
configuration asks no questions and performs no writes. Doctor never delegates
to setup.

or `/talk` inside an interactive Hermes session, which additionally reaches the
agent-loop-only tools (`memory`, `session_search`, `honcho_search`,
`delegate_task`). A spoken memory lookup tries the transcript first
(`session_search`) and remembered profile facts second (`honcho_search`), and
says which of the two it answered from — a recollection can be stale in a way
a verbatim line cannot, and nothing is on screen to check it against.

**Pause the microphone without hanging up.** Say "stop listening" (or "mute
the mic") and the model calls `pause_voice_input`: the call stays connected,
playback keeps playing, background work keeps running and its results are
still announced — only your speech stops reaching the provider. A paused
microphone cannot hear the word "resume", so the way back is your own control,
and **the pause is offered only where that control is guaranteed to exist**:

- **`hermes talk` in a real terminal** — **Enter** toggles (`p` and `r` are
  explicit; on Windows they are single keys, elsewhere type the word and
  Enter). The connected line says `Enter to pause or resume the microphone`
  when the key is live. With a piped or non-tty stdin (Git Bash's mintty
  reports no tty to Python; launcher wrappers) there is no key, so no pause is
  offered and a pause call is refused with a receipt that says why.
- **`/talk` typed at the Hermes prompt** — the prompt owns that terminal for
  the whole call, so the session never watches it for a key, and offers no
  pause either. Use `hermes talk` on its own when you want the control.
- **Discord** — `/talk pause` and `/talk resume`, typed. The model-side tool
  is offered on the legacy provider-owned lane; on the `provider-host-tools`
  lane the host supplies the tool list and the typed commands are the path.

Both directions get a spoken receipt, the receipt names the control for the
room you are in, and Ctrl+C still hangs up.

**In Discord**, `/talk join` runs the call in the voice channel Hermes is
already in — same conversation, same tools, same steering, in a room other
people can hear. Talk now reports speaker transitions to the model using the
member's immutable Discord user ID; display names are quoted as untrusted data,
and an unknown SSRC stays unresolved and unauthorized. Configure immutable IDs
with `TALK_DISCORD_OPERATOR_USER_IDS=<id>[,<id>...]`. Only those speakers may
run `delegate_task`, `steer_agent`, `redirect_agent`, or `stop_work`; everyone
may still converse and use read-only tools — including `pause_voice_input`,
which can only narrow what the session does; `/talk resume` (text) brings
listening back. Unset, blank, or any malformed list
authorizes nobody. Talk binds permission to the exact Discord PCM, VAD input
item, and opaque Realtime response metadata — never a display name, SSRC,
model argument, or whichever person spoke most recently. Mixed, missing, or
unresolved attribution fails closed with a spoken denial. Terminal microphone
and dashboard sessions retain their existing behavior. Talk borrows the host's
own voice connection rather than opening a second one. Details:
[docs/OPERATING.md](docs/OPERATING.md#discord-voice--talking-in-the-channel-hermes-is-already-in).

What can you actually say? The full say-this → hear-this card, with what
each spoken receipt commits to: [docs/VOICE-COMMANDS.md](docs/VOICE-COMMANDS.md).

## Dashboard tab

The demo at the top of this README is this tab. Start the dashboard and Talk
appears in the nav:

```bash
hermes plugins enable hermes-talk   # already done by `install --enable`
hermes dashboard                    # then open the Talk tab
```

Hit **Start**, allow the microphone, and talk. The page mints an ephemeral
secret server-side, dials OpenAI directly over WebRTC, relays every function
call back into the plugin's real tool surface, and shows the transcript plus a
live list of background runs. Nothing to install — the bundle ships with the
plugin and the host serves it.

**Memory writeback currently covers terminal and Discord Talk sessions.** Those
rooms share the server-side Realtime relay, which durably captures completed
turns. The dashboard's Realtime events stay in the browser, so matching durable
capture requires a separate authenticated transcript endpoint; until that lane
exists, the tab does not claim to write its conversation back to memory.

The tile at the top of the tab reads **attached**, **api-server**, or **out of
process** — which of the three agent lanes below this session would actually
use. It is not a guess; it is the lane the next tool call will take.

### `TALK_DASHBOARD_TOKEN` — the tab's own gate

Dashboard routes already sit behind the dashboard's session auth, but this
plugin's routes mint real credentials, so they carry a second check that never
fails open:

- **Unset (default): loopback only.** A browser on the same machine works with
  no configuration. Anything else is refused with a message naming this
  variable — including a request whose peer address this process cannot read
  at all, which is treated as remote rather than trusted.
- **Set: the token is required**, on loopback too, compared with
  `hmac.compare_digest`. Paste it into the field the tab offers when it gets
  refused; it's held in `sessionStorage`, so it dies with the tab.

Set it whenever the dashboard is reachable from anywhere but this machine.

## Reaching a real agent — the three lanes

Everything that needs an actual Hermes agent — a memory lookup, a delegated
task — goes down the same chain, and **every fall-through is said out loud**:

1. **Attached** — the agent loop this session is running inside. Only `/talk`
   has one. Answers come back inline, in the same breath.
2. **api-server** — a real, fully-tooled Hermes agent reached over the
   [api_server gateway platform](#turning-the-api-server-lane-on). This is what
   makes the dashboard tab and a standalone `hermes talk` more than a fallback.
3. **Out of process** — no agent lane. Delegation still spawns a detached
   `hermes -z` one-shot; a memory lookup refuses, naming exactly what's missing.

Lanes 2 and 3 answer with a receipt rather than the answer, and speak the
result when it lands. That is not a shortcut: an agent run takes seconds to
minutes, and the tool call that starts it runs on the same thread carrying your
microphone. Waiting there wouldn't be patience, it would be dead air.

### Turning the api-server lane on

```bash
# in your gateway environment (HERMES_HOME/.env works)
API_SERVER_KEY=<a strong key you choose — 16+ characters>
```

Restart the gateway. The platform enables itself when a usable key exists —
current hosts require the key (an unauthenticated api-server refuses to
start), so `API_SERVER_ENABLED` alone does nothing. Talk finds it by itself — no Talk-side configuration is
needed, because `API_SERVER_KEY` is the same variable the gateway reads. If you
want Talk to use a *different* key or a non-default address, set
`TALK_API_SERVER_KEY` / `TALK_API_SERVER_URL`.

Talk probes `GET /v1/capabilities` (which is authenticated, on purpose) at
session start, so a wrong key is reported as **"running but rejected my key"**
rather than as "not reachable" — those send you to two different places.

## Background work

Say "go audit the site and tell me what's broken" and it starts a real agent,
then keeps talking to you. When the work lands, Talk speaks the result
unprompted. Ask "how's that going?" in the meantime and `check_work` answers.

Between the receipt and the landing, the session speaks bounded progress
milestones: "accepted", "executing — Reading files", "waiting on an approval",
and periodic "still working" heartbeats. The only detail that can name what a
job is doing is a safe label from a fixed table — never the tool's arguments,
paths, or output.

Known limitation: delivery is bound to the exact session that started the
work. If you disconnect before it lands, reconnecting on the *same* Hermes
session adopts and speaks what you were owed, exactly once — a different
session, or one with no durable Hermes context, never receives it.

Delegation walks the [three lanes](#reaching-a-real-agent--the-three-lanes) and
then one more, and **every fall-through is said out loud** — the plugin never
silently does less than you asked:

1. **Hermes's own agent loop** — inside `/talk`, where there's a parent agent
   to delegate into.
2. **A real agent over the api_server** — preferred over a spawn: it reuses a
   warm, fully-tooled agent instead of paying a process start.
3. **A detached `hermes -z` one-shot** — needs nothing enabled, so this is the
   lane that always exists as long as `hermes` is on the PATH.
4. None available — a refusal naming all three missing lanes.

### Two jobs, one checkout — admission control

Delegate two tasks that both touch the same repository and, left alone, they
race: two agents editing one checkout, two deploys to one target. Since #101
the model can say what a task touches, and the run registry refuses the second
job instead of letting it collide:

- `delegate_task` takes two optional arguments. `resource_keys` names up to
  eight stable things the task touches — an absolute repo path, a deployment
  target, a service name (whitespace-collapsed and case-folded, so two
  spellings of one path are one key). `execution_mode` is `exclusive` (the
  default) or `parallel_read_only`.
- Two live runs that share any key never overlap unless **both** are
  `parallel_read_only`. The check happens before a run id is minted, before
  the acceptance record is written, before the worker starts — a refused job
  burns nothing and leaves no `lost` record behind.
- A refusal is a spoken tool result naming the run in the way: "run 4 (audit
  the repo) is still running and touches the same resource ('/srv/app'); wait
  for it, stop it, or re-delegate without that key." Never a hang, never a
  silent queue. `check_work` reads out what each running job is holding.
- **`parallel_read_only` is believed only when you say so.** The declaration
  is the delegating model's own claim about work it has not done yet — policy
  input, not a sandbox — so by default it is downgraded to `exclusive` and
  recorded that way. `TALK_TRUST_DECLARED_READ_ONLY=true` lets read-only jobs
  on a shared key run together; the knob is read at admission time, so turning
  it back off closes every overlap it had allowed. It is the only thing that
  can widen behavior.
- No keys means no fence, in either direction: a task that names nothing is
  exactly the task Talk always ran, record and all.

The fence is per process and covers the api-server and detached lanes, whose
runs this registry owns. Inside `/talk`, the host's own delegation registry
runs the child: the job is still checked against the keys this registry
holds — never started on top of one — but it holds none itself afterwards,
and its `WORK_STARTED` receipt says so.

| Surface | Entry point |
|---|---|
| Terminal | `hermes talk` — task attachment with `hermes talk --task TARGET` |
| Inside a Hermes session | `/talk` — the one surface with an **attached** agent loop, so lookups and delegation answer inline |
| Discord voice channel | `/voice join`, then `/talk join [TARGET]` |
| Dashboard **Talk** tab | `hermes dashboard`, select a task, **Start** |
| Desktop **Talk** composer action | open a conversation → **Talk** → **Connect**; works on stock Desktop, with a floating window on the Talk-enabled build ([host lanes](docs/DESKTOP.md)) |

## Is it working?

```bash
hermes plugins list        # → hermes-talk · enabled · current version
hermes talk doctor         # → read-only: auth lane, provider, model/voice, audio, host lanes
hermes talk check          # → doctor + one live provider turn + one bounded Hermes run
# then, in any session: say "status report" — talk_status answers with
# version, auth lane, agent lane, and audio state.
```

Doctor is read-only by design: it names which lane came up and what is missing,
and never writes, probes, or refreshes a token. `check` is the other half and is
deliberately **not** read-only — one short provider turn and one short agent run,
exit 0 only if every step passed. A mock can never go green.

**Filing an issue?** `hermes talk diagnostics --bundle` writes one redacted,
owner-only file — versions, the *names* of the variables you have set, device and
host facts, and every doctor outcome; no values, logs, prompts, transcripts,
audio, or paths. It is safe to paste into a public issue and it is what the
[bug template](.github/ISSUE_TEMPLATE/bug_report.yml) asks for.

**Upgrade** with `hermes plugins update hermes-talk` — not a second `install` —
then **restart the gateway**: a running process keeps executing the old code
until you do.

The full diagnostic walk, every receipt, and the upgrade runbook:
[docs/OPERATING.md](docs/OPERATING.md#verify--the-receipts).

Runs are tracked in `$HERMES_HOME/state/talk-runs.jsonl`. The work is
detached, so ending the call does **not** stop it — but the watcher that would
have spoken the result dies with the session, so a run from a previous session
is reported as `lost`, never as "still running". Steering, redirecting, and
stopping a running job — `list_agents`, `steer_agent`, `redirect_agent`,
`stop_work` — is covered in
[docs/BACKGROUND-WORK.md](docs/BACKGROUND-WORK.md#redirecting-work-thats-already-running).

## What the voice can do — the capability bridge

The session prompt carries a bounded, live-catalog section: how many skills
are installed, which tool categories are usable *right now*, and the two rules
that keep the model honest — it can **delegate anything Hermes can do**, and it
must **never invent tool names**. The section is assembled from the real
catalog lanes (the host's own registries in-process, or the api-server's
`/v1/skills` + `/v1/toolsets` + `/v1/capabilities` out of process); when the
catalog is unreachable the section is simply absent, and the session runs on
the plain preamble exactly as before.

That changes three everyday exchanges:

- **"What can you do?"** is answered from the catalog — live evidence, never
  a recited prompt. A toolset whose tools all failed the host's availability
  gates is not claimed.
- **"Check my screen" / anything past the advertised tools** delegates by
  default. The classification table in `talk_operator_auth` decides what a
  host tool call may do at the voice surface: a short curated read-only list
  (`web_search`, `web_extract`, `vision_analyze`, `session_search`) runs
  inline; `computer_use`'s read actions (`capture`, `wait`, `list_apps`,
  `list_windows`) need a fresh spoken operator permit; everything else — and
  every destructive computer-use action, whose in-handler gate fails open
  without a real approval context — delegates. The classification applies on
  every transport, the local terminal lane included: mutating host tools
  steer to delegation with spoken approvals rather than running bare. A
  denied call never refuses flat: you hear "I can't do that directly in a
  voice call — I can spin up an agent that can. Want me to?"
- **Delegated work that hits a gated action now asks you out loud.** The run
  lane streams the host's `approval.request` events; Talk speaks the request
  ("run 3 wants to run a shell command — once, this session, or no?") and your
  spoken answer resolves it via the new `resolve_approval` tool, which on
  Discord rides the same fresh-speech permit machinery as the other mutating
  tools. **Voice can grant `once`, `session`, or `deny` — never `always`**:
  the choice set is narrowed in code, in the tool schema, and in the prompt,
  and `session` is scoped to that run. Fail closed on everything ambiguous: an
  unanswered question times out into a deny (`TALK_APPROVAL_PROMPT_TIMEOUT_S`,
  default 60s), and interrupting the question denies it too — a question not
  fully heard is not a question answered. Progress and the result still arrive
  through the existing milestone/result machinery.

### `TALK_AGENT_PROFILE` — which profile the background agent runs under

If your model config lives in a **profile** rather than the root
`config.yaml`, a bare `hermes -z` cannot resolve a model and dies with
`Invalid length for parameter modelId, value: 0`. Talk handles this for you:

- `TALK_AGENT_PROFILE=<name>` — spawn `hermes --profile <name> -z …`.
- **Unset (default): auto-detect.** If the root `config.yaml` names a
  `model.default`, no flag is added. If it doesn't and *exactly one* profile
  under `$HERMES_HOME/profiles/` does, that profile is used.
- Zero matching profiles, or two or more → no flag, deliberately. Guessing
  between profiles would be invisible until the wrong agent had already run;
  the spawn's own error names the problem better.
- Set-but-blank (`TALK_AGENT_PROFILE=`) is an explicit opt out: never pass a
  flag, even if detection would have found one.

## Knobs

The common ones. Every variable — api-server probe internals included —
with defaults and failure modes: [docs/OPERATING.md](docs/OPERATING.md#configuration--every-knob).

| Variable | Default | What it does |
|---|---|---|
| `TALK_MODEL` | `gpt-realtime-2.1` | Realtime model; doctor certifies only the bounded duplex-audio + tool-calling policy and labels other Realtime-shaped ids compatibility-unknown |
| `TALK_VOICE` | `cedar` | Realtime voice (fail-closed on unknown ids) |
| `TALK_PROVIDER` | `openai` | Realtime voice provider: `openai`, `grok`, or `gemini` (fail-closed; never inferred from which keys exist) |
| `TALK_GROK_MODEL` | `grok-voice-latest` | Grok realtime model |
| `TALK_GROK_VOICE` | `ara` | Grok voice: `ara`, `rex`, `sal`, `eve`, `leo` (fail-closed) |
| `TALK_XAI_API_KEY` / `XAI_API_KEY` | unset | xAI key for the Grok lane, Talk-scoped first; set-but-blank refuses; unset both to ride the `hermes auth add xai-oauth` subscription login |
| `TALK_PREFER_XAI_OAUTH` | unset | `true` requires the xAI subscription login and refuses key fallback; absent/`false` keeps key-first precedence |
| `TALK_GEMINI_MODEL` | `gemini-3.1-flash-live-preview` | Gemini Live model (bare id; the adapter adds the wire prefix) |
| `TALK_GEMINI_VOICE` | `Puck` | Gemini Live voice: `Puck`, `Charon`, `Kore`, `Fenrir`, `Aoede` (fail-closed, case-sensitive) |
| `TALK_GEMINI_API_KEY` / `GEMINI_API_KEY` | unset | Gemini key for the Gemini lane, Talk-scoped first; set-but-blank refuses; free-tier keys work |
| `TALK_VOICE_MODE` | `native` | `native`, `cascade` (ElevenLabs voice), or `live` (GPT-Live); invalid values refuse |
| `TALK_LIVE_AUTH` | `subscription` | GPT-Live billing: `subscription` or explicit `api`; no automatic paid fallback |
| `TALK_LIVE_SUBSCRIPTION_MODEL` / `TALK_LIVE_SUBSCRIPTION_VOICE` | `gpt-live-1-codex` / `cove` | Subscription-only Live settings; [validated choices](docs/GPT-LIVE.md#choose-billing-and-voice) |
| `TALK_LIVE_API_MODEL` / `TALK_LIVE_API_VOICE` | `gpt-live-1` / `marin` | API-only Live settings |
| `TALK_TASK_API_URL` / `TALK_TASK_TARGET` | unset | Authenticated Hermes dashboard origin and explicit terminal task; [attachment guide](docs/GPT-LIVE.md#start-and-control-a-task) |
| `TALK_CASCADE_TTS` | `elevenlabs` | Cascade TTS provider: `elevenlabs` or `openai` (fail-closed) |
| `TALK_ELEVENLABS_API_KEY` / `ELEVENLABS_API_KEY` | unset | ElevenLabs key for the cascade lane, Talk-scoped first; set-but-blank refuses; rides the `xi-api-key` header, never the URL |
| `TALK_ELEVENLABS_VOICE_ID` | unset | Voice the cascade speaks with — **required** in cascade mode (stock or cloned, from your ElevenLabs account) |
| `TALK_ELEVENLABS_MODEL` | `eleven_flash_v2_5` | ElevenLabs TTS model for the cascade lane |
| `TALK_CASCADE_OPENAI_BASE_URL` | unset | Base URL of your OpenAI-compatible TTS endpoint — **required** when `TALK_CASCADE_TTS=openai` |
| `TALK_CASCADE_OPENAI_API_KEY` / `TALK_OPENAI_API_KEY` / `OPENAI_API_KEY` | unset | Key for the OpenAI-compatible cascade lane, in that fallback order; set-but-blank refuses; all unset sends no Authorization header |
| `TALK_CASCADE_OPENAI_MODEL` | unset | TTS model id your endpoint serves — **required** when `TALK_CASCADE_TTS=openai` |
| `TALK_CASCADE_OPENAI_VOICE` | unset | Voice/speaker id your endpoint serves — **required** when `TALK_CASCADE_TTS=openai` |
| `TALK_PREFER_CODEX_OAUTH` | unset | `true` requires Codex OAuth and refuses key fallback; absent/`false` keeps key-first precedence |
| `TALK_INPUT_DEVICE` / `TALK_OUTPUT_DEVICE` | auto | sounddevice overrides |
| `TALK_AGENT_PROFILE` | auto-detect | Profile for the detached background agent |
| `TALK_API_SERVER_URL` | `http://127.0.0.1:8642` | Where the api-server lane looks |
| `TALK_API_SERVER_KEY` | `API_SERVER_KEY` | Key for the api-server lane (blank = send none) |
| `TALK_AGENT_TIMEOUT_S` | `1800` | Budget for one background run, and its watcher |
| `TALK_TRUST_DECLARED_READ_ONLY` | `false` | Believe a delegated task's `parallel_read_only` declaration, letting read-only runs share a `resource_key`; off downgrades every run to `exclusive` |
| `TALK_IDENTITY_INCLUDE` | all | Which identity sections ride the prompt |
| `TALK_MEMORY_SEARCH_TIMEOUT_S` | `10.0` | Wait bound for the in-process remembered-context (Honcho) lookup |
| `TALK_SESSION_KEY` | unset | Stable operator scope sent as `X-Hermes-Session-Key` on api-server runs, so host-side memory survives `/clear` (blank = send none). **Not a session boundary: every voice-channel participant shares this scope** — memory reads are not gated by the operator ledger, so do not set it in multi-user channels until per-speaker scoping lands |
| `TALK_DASHBOARD_TOKEN` | unset | Token for the dashboard tab's routes (unset = loopback only) |
| `TALK_DISCORD_OPERATOR_USER_IDS` | none | Comma-separated immutable Discord IDs allowed to run mutating tools; malformed = nobody |

### `TALK_IDENTITY_INCLUDE` — what the session starts knowing

Three sections are resolved at session start, each independently and each
optional:

- **`PERSONA`** — your `SOUL.md`, read through Hermes's own loader (so it gets
  the same injection scan the text agent's copy does).
- **`MEMORY`** — the system-prompt block your configured memory provider
  contributes. Inside `/talk` this is the live agent's already-assembled
  block; standalone, Talk loads the configured provider itself, reads the
  block, and shuts it down again.
- **`WORKING`** — `memories/WORKING.md`, the one identity file **you** write
  rather than the model: who you are, which repos and plugins you mean by
  name, what an alias maps to. Entries are separated by `\n§\n`, the same
  delimiter Hermes uses for `MEMORY.md`, and each is threat-scanned
  independently — one bad entry costs that entry, not your whole table. When
  a host is attached, one sentence is appended pointing at `search_memory`
  for names *not* in the file. The rule to ASK when a spoken name could match
  more than one thing rides the voice preamble itself, on every lane — it
  depends on no file, no tool, and no include list, so nothing can drop it.

A broken or missing provider costs that section and nothing else — the call
still starts. `talk_status` reports which sections resolved and how many
characters each contributes, never their content.

`WORKING.md` is what stops a voice session asking who you are every call.
Nothing fills it for you — no producer writes installed plugins or recent
work into it; what you curate by hand is all a session gets. It is read once
at session mint and stays frozen for the call: an edit lands on the NEXT
session, never the live one. Keep it short — the resolved prompt is resident
and paid for on every turn:

```markdown
Pedro, solo operator. Ships at night, prefers blunt answers.
§
"Talk" or "hermes-talk" means TheSmokeDev/hermes-talk (this plugin).
§
"Dograh" (often heard as "Dobra" or "Dog Bras") is the voice stack.
```

## Documentation

Everything Hermes Talk does, in depth:

- [OPERATING.md](docs/OPERATING.md) — install, upgrade, use, every knob, the three agent lanes, the Discord lane, the dashboard tab, current boundaries, troubleshooting.
- [PROVIDERS.md](docs/PROVIDERS.md) — per-lane provider detail and the fail-closed OpenAI credential order.
- [BACKGROUND-WORK.md](docs/BACKGROUND-WORK.md) — delegation, admission control, steering a running agent, and the capability bridge.
- [CASCADE.md](docs/CASCADE.md) — the cascade lane: your own ElevenLabs voice over a realtime provider.
- [GPT-LIVE.md](docs/GPT-LIVE.md) — GPT-Live billing and voice, task attachment, Codex workers, operator acceptance.
- [DESKTOP.md](docs/DESKTOP.md) — Talk in the Hermes desktop app: the stock lane, and what the Talk-enabled build adds.
- [VOICE-COMMANDS.md](docs/VOICE-COMMANDS.md) — say this, hear this, and what each spoken receipt commits to.
- [REALTIME-ORCHESTRATOR.md](docs/REALTIME-ORCHESTRATOR.md) — architecture map of the tool-calling realtime lane.
- [dashboard-task-continuity.md](docs/dashboard-task-continuity.md) — joining, continuing and reconnecting to a canonical Hermes task.
- [recipient-routing.md](docs/recipient-routing.md) — addressing an existing application task from a voice task.
- [codex-workers.md](docs/codex-workers.md) — selecting a Codex background worker from a bound task.
- [task-event-projection.md](docs/task-event-projection.md) — the worker-side library that restores task and work state.
- [passive-attachment-client.md](docs/passive-attachment-client.md) — the shared passive-history client used by all three surfaces.
- [PROVIDER-RECEIPT.md](docs/PROVIDER-RECEIPT.md) — how to report a provider lane that worked, or broke, for you.
- [CAPABILITY-KERNEL-PORT.md](docs/CAPABILITY-KERNEL-PORT.md) — the capability-plugin kernel adaptation guide.

## Design rules

The three that shaped everything else:

- **Nothing fails quietly.** A degraded backend, a missing tool, a run whose
  watcher died — each is said out loud in the conversation. A voice surface
  that silently does less than you asked is worse than one that refuses.
- **The credential never leaves the process.** Key or OAuth token hits exactly
  one OpenAI endpoint (the mint) and the socket only ever sees the ephemeral
  secret it returns.
- **Hermes owns the tools and the session.** The Realtime layer is ears, mouth,
  and turn-taking. It never owns the agent loop.

## Background

Hermes Talk began as a plugin and became a reference implementation for the
speech-to-speech contract Hermes core now carries:

- [RFC NousResearch/hermes-agent#77111](https://github.com/NousResearch/hermes-agent/issues/77111)
  — filed from this repo: a `RealtimeVoiceProvider` ABC for Hermes core.
- [PR NousResearch/hermes-agent#101808](https://github.com/NousResearch/hermes-agent/pull/101808)
  — the core contract, orchestrator, and first built-in provider, ported from
  this plugin's orchestrator and OpenAI transport. hermes-talk already publishes
  its three lanes on that contract
  ([details](docs/OPERATING.md#hermes-core-realtime-contract)).
- [PR NousResearch/hermes-agent#97325](https://github.com/NousResearch/hermes-agent/pull/97325)
  — a pointer to this plugin on the official Voice Mode docs page.

## Status

Under active development; the PyPI badge above is the released version.
Every version with its receipts: [CHANGELOG.md](CHANGELOG.md). Open epics and
threads:
[#19](https://github.com/TheSmokeDev/hermes-talk/issues/19) provider-neutral
Realtime voice platform,
[#32](https://github.com/TheSmokeDev/hermes-talk/issues/32) operator-grade
orchestration UX,
[#43](https://github.com/TheSmokeDev/hermes-talk/issues/43) Talk over the Bot
Mode roster,
[#44](https://github.com/TheSmokeDev/hermes-talk/issues/44) channel-neutral
voice transport.

## Contributing

`uv sync --extra dev` (or `pip install -e ".[dev]"`), `pytest -q`, `ruff check .`
— offline, no keys, seconds. Priorities, the path for each kind of change
(a provider, a surface, a tool, a fix), the merge bar, and the one test trap
on a box that has Hermes installed: [CONTRIBUTING.md](CONTRIBUTING.md).
First response within 24 hours;
[`good first issue`](https://github.com/TheSmokeDev/hermes-talk/issues?q=is%3Aopen+label%3A%22good+first+issue%22)
fits in one sitting; a provider that works or broke for you is a
contribution too ([docs/PROVIDER-RECEIPT.md](docs/PROVIDER-RECEIPT.md)).

Contributors adapting The Homie's v1.7.0 capability-plugin lessons to Hermes
should use the [capability-kernel port plan](docs/CAPABILITY-KERNEL-PORT.md).
It maps the reusable safety and lifecycle contracts onto Hermes-owned APIs;
it does not claim that hot lifecycle support already exists here.

### Contributors

[@danclaw93](https://github.com/danclaw93): room-scoped spoken approvals send
the `request_id` the Hermes run API reads, so they stop failing with HTTP 400
(0.17.1).

[@kvnloo](https://github.com/kvnloo): PulseAudio WebRTC echo cancellation
on Linux, and the fix that stopped quiet words being clipped during
playback ([#81](https://github.com/TheSmokeDev/hermes-talk/pull/81));
semantic turn-detection controls across the three lanes
([#107](https://github.com/TheSmokeDev/hermes-talk/pull/107), in review).
[@TheAngryPit](https://github.com/TheAngryPit) — a renderer-owned Realtime
transport for the Hermes desktop app that keeps core as the single chat
authority ([#80](https://github.com/TheSmokeDev/hermes-talk/pull/80), in
review). [@webdevtodayjason](https://github.com/webdevtodayjason) —
field-tested feedback from a second live consumer on the upstream
`RealtimeVoiceProvider` contract these lanes register on
([hermes-agent#81404](https://github.com/NousResearch/hermes-agent/pull/81404)).

## License

[MIT](LICENSE). Adapted-source licenses and contributor credits are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
