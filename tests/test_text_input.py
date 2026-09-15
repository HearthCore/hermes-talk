"""Explicit text input drives the real route, stores, coordinator and fixture hosts."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from test_dashboard_steering import SteeringHost
from test_live_coordinator import Decision
from test_recipient_history import NATIVE_HOST, NativeHost
from test_target_switching import CatalogHost

import talk_audio
from talk_dashboard_gateway import DashboardTaskError
from talk_dashboard_tasks import DashboardOwnerContext
from talk_passive import HistoryTransport, digest
from talk_recipients import IDENTITY_FIELDS
from talk_target_catalog import TargetCatalog
from talk_target_selection import TargetSelection

TOKENS = ("typed-dashboard-token", "typed-desktop-token", "fixture-gateway-key")
OWNER_TEXT = "Inspect this exact original request.\nKeep this spacing."
STEER_TEXT = "Use exactly $42.\nPlease."


class Bridge(NativeHost):
    """The read-only recipient bridge plus the two control operations the read tests refuse."""

    def __init__(self):
        super().__init__(None)
        self.journal, self.torn = {}, False

    def __call__(self, request):
        operation = request.url.path.rsplit("/", 1)[1]
        if operation not in {"send", "reconcile"}:
            return super().__call__(request)
        body = json.loads(request.content)
        self.calls.append((operation, body, request))
        assert request.headers["Authorization"].startswith("Bearer ")
        target = next((row for row in [*self.rows, self.live]
                       if row["target_token"] == body.get("target_token")), None)
        if target is None:
            return httpx.Response(404, json={"error": "recipient_not_found"})
        identity = {key: target.get(key, NATIVE_HOST) for key in IDENTITY_FIELDS}
        if operation == "send":
            assert "commit_token" not in body and body["operation_id"] not in self.journal
            self.journal[body["operation_id"]] = {
                **identity, "operation_id": body["operation_id"], "status": "posted",
            }
            if self.torn:
                self.torn = False
                raise httpx.ReadError("bridge acknowledgement lost", request=request)
        receipt = self.journal.get(body["operation_id"])
        if receipt is None:
            return httpx.Response(404, json={"error": "recipient_not_found"})
        return httpx.Response(200, json=receipt)

    def sends(self):
        return [call for call in self.calls if call[0] == "send"]


class SeamHost(SteeringHost, CatalogHost):
    """The fleet's local host with run steering, a Codex worker and a recipient bridge."""

    def __init__(self, store_id):
        CatalogHost.__init__(self, store_id)
        # SteeringHost's state, without its no-argument constructor.
        self.controls, self.deliveries = {}, []
        self.steering_supported, self.ordinary_origin = True, False
        self.kind, self.turn = "linked_child", "host:turn:1"
        self.before_steer = self.before_target = self.drop = None
        self.read_unavailable, self.receipt_override = False, None
        self.codex_worker = True
        self.bridge = Bridge()

    def __call__(self, request):
        if "/v1/recipient-bridge/" in request.url.path:
            return self.bridge(request)
        response = super().__call__(request)
        if self.codex_worker and request.url.path.endswith("/v1/capabilities"):
            data = response.json()
            data["features"]["linked_child_dispatch"]["external_workers"] = {
                "version": 1, "names": ["hermes-talk-codex"],
            }
            return self.response(200, data)
        return response

    def posts(self, suffix):
        return [(path, body) for method, path, body, _ in self.requests
                if method == "POST" and path.endswith(suffix)]


class RemoteRequest:
    """A peer the gate must refuse before the body is ever read."""

    def __init__(self):
        self.headers = {}
        self.client = SimpleNamespace(host="203.0.113.9")


def build_fleet(manager, tmp_path):
    """The target-switching fleet, rebuilt around the module's own TASKS.

    The mounted routes captured ``TASKS`` at import, so the fixture wires the
    fleet INTO that object instead of swapping the module attribute.
    """
    hosts = {"local": SeamHost("local-store")}
    request = SimpleNamespace(state=SimpleNamespace(principal="actor-one"))

    def resolve(req, profile=None):
        profile = profile or "default"
        if profile != "default":
            raise DashboardTaskError("context_denied", 403)
        return DashboardOwnerContext(
            req.state.principal, "verified_subject", profile, tmp_path / profile, "local-store"
        )

    def local(context):
        return HistoryTransport(
            "http://127.0.0.1:8642", context.profile_name, "fixture-gateway-key",
            named_profile=context.profile_name != "default",
            actor_scope=digest([context.principal_id, context.store_id]),
            _http_transport=httpx.MockTransport(hosts["local"]),
        )

    manager.resolve_context, manager.transport_factory = resolve, local
    catalog = TargetCatalog(
        manager, profiles=lambda: [{"name": "default", "display_name": "Main Bot"}],
        peers=lambda: [], resolve_peer=lambda name, profile, home: pytest.fail(name),
        local_factory=local, remote_factory=None,
    )
    selection = TargetSelection(manager, catalog=catalog)
    return SimpleNamespace(manager=manager, catalog=catalog, selection=selection,
                           request=request, hosts=hosts, root=tmp_path)


@pytest.fixture
def seam(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("text_input_route_fixture", source)
    api = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = api
    spec.loader.exec_module(api)
    fleet = build_fleet(api.TASKS, tmp_path)
    monkeypatch.setattr(api, "TARGETS", fleet.selection)
    monkeypatch.setattr(api.talk_dashboard_tasks, "resolve_context", fleet.manager.resolve_context)
    monkeypatch.setenv("TALK_DASHBOARD_TOKEN", "typed-dashboard-token")
    monkeypatch.setenv("HERMES_DESKTOP_TALK_TOKEN", "typed-desktop-token")

    def forbidden(*args, **kwargs):
        pytest.fail("Text input must not resolve voice configuration, auth, or transport")

    for module, name in (
        (api, "_resolve_voice_mode"),
        (api, "_mint"),
        (api.talk_auth, "resolve_auth"),
        (api.talk_live_config, "resolve_live_config"),
        (api.talk_live_config, "resolve_live_auth"),
        (api.LIVE_SESSIONS, "create"),
        (talk_audio.DuplexAudio, "start"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    decision = Decision()
    coordinator = api.LIVE_SESSIONS.coordinator
    assert coordinator.manager is fleet.manager
    coordinator.targets, coordinator.tools, coordinator.decide = (
        fleet.selection, api._session_tools, decision,
    )
    named = {handler.__name__: handler for handler in (
        *api.TEXT_INPUT_ROUTE_HANDLERS, *api.LIVE_ROUTE_HANDLERS, *api.RECIPIENT_ROUTE_HANDLERS,
    )}
    paths = {
        "/text/input": ("POST", named["text_input"]),
        "/native/attach": ("POST", api.native_task_attach),
        "/targets": ("POST", api.task_targets),
        "/state": ("POST", api.task_state),
        "/close": ("POST", api.task_close),
        "/status": ("GET", api.talk_status),
        "/live/operation": ("GET", named["live_operation"]),
        "/recipients/catalog": ("POST", named["recipient_catalog"]),
        "/recipients/select": ("POST", named["recipient_select"]),
    }

    def endpoint(handler):
        async def call(request):
            request.state.principal = request.headers.get("x-actor", "actor-one")
            try:
                result = await handler(request)
            except api.HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            return result if isinstance(result, Response) else JSONResponse(result)

        return call

    app = Starlette(routes=[
        Route(path, endpoint(handler), methods=[method])
        for path, (method, handler) in paths.items()
    ])
    return SimpleNamespace(api=api, fleet=fleet, app=app, decision=decision,
                           coordinator=coordinator, host=fleet.hosts["local"],
                           text_input=named["text_input"])


def client_for(seam):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=seam.app),
                             base_url="http://hermes.test",
                             headers={"x-talk-token": "typed-dashboard-token"})


async def attach(client, **fields):
    catalog = await client.post("/targets", json={})
    assert catalog.status_code == 200, catalog.text
    selected = next(row["target_id"] for row in catalog.json()["targets"]
                    if row["session_id"] == "task-a")
    return await client.post("/native/attach", json={
        "input_mode": "typed", "surface": "dashboard", "target_id": selected,
        **({} if "connection_id" in fields else {"tab_id": "typed-tab"}), **fields,
    })


def context(response):
    assert response.status_code == 200, response.text
    return {key: response.json()["task"][key] for key in ("connection_id", "generation")}


async def send(client, owner, operation, text, input_id, headers=None, **extra):
    return await client.post("/text/input", headers=headers or {}, json={
        **owner, "input_id": input_id, "text": text, "operation": operation,
        "attachments": [], **extra,
    })


def code(response):
    return response.json()["detail"]["code"]


async def job(client, owner, *, input_id="start-one", text="Start the background worker"):
    """Start a Codex worker through the seam and return its reply and /state card."""
    started = await send(client, owner, "start_worker", text, input_id)
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "accepted"
    state = await client.post("/state", json=owner)
    assert state.status_code == 200, state.text
    card = next(row for row in state.json()["jobs"] if row["run_id"] == started.json()["run_id"])
    return started.json(), {"run_id": card["run_id"], "action_id": card["action_id"]}


async def select(client, owner, *, read_only=False):
    catalog = await client.post("/recipients/catalog", json=owner)
    assert catalog.status_code == 200, catalog.text
    row = next(row for row in catalog.json()["recipients"]
               if row["read_only"] is read_only and row["app"] == "codex_desktop")
    identity = {key: row[key] for key in IDENTITY_FIELDS}
    selected = await client.post("/recipients/select", json={
        **owner, **identity, "action_id": "select-" + row["recipient_id"],
    })
    assert selected.status_code == 200 and selected.json()["state"] == "selected", selected.text
    return identity


def records(seam, owner):
    bound = seam.fleet.manager.binding(seam.fleet.request, owner)
    return bound.stages.records(bound.token)


def history(seam):
    return [row["content"] for row in seam.host.rows[("default", "task-a")]]


def test_owner_message_without_recipient_admits_one_coordinator_operation(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            reply = await send(client, owner, "message", OWNER_TEXT, "typed_owner")
            assert reply.status_code == 200, reply.text
            assert reply.headers["cache-control"] == "no-store"
            body = reply.json()
            assert body["ok"] is True and body["input_id"] == "typed_owner"
            assert body["operation"] == "message" and body["state"] == "queued"
            assert body["operation_id"] and "run_id" not in body
            await asyncio.wait_for(asyncio.gather(*seam.coordinator._tasks.values()), 10)
            settled = await client.get("/live/operation", params={
                **owner, "operation_id": body["operation_id"],
            })
            assert settled.status_code == 200 and settled.json()["pending"] is False
            assert settled.json()["result"]["action"]["state"] == "accepted"
            assert len(seam.host.posts("/v1/runs")) == len(seam.decision.calls) == 1
            assert history(seam).count(OWNER_TEXT) == 1
            repeat = await send(client, owner, "message", OWNER_TEXT, "typed_owner")
            assert repeat.json()["operation_id"] == body["operation_id"]
            assert len(seam.host.posts("/v1/runs")) == 1
            status = await client.get("/status")
            assert status.json()["textInput"] == {
                "version": 1, "attachments": False,
                "operations": ["message", "start_worker", "steer", "cancel", "approval"],
            }

    asyncio.run(run())


@pytest.mark.parametrize("operation", ["start_worker", "cancel", "approval", "message"])
def test_same_input_id_twice_dispatches_once_per_operation(seam, operation):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            host = seam.host
            if operation == "start_worker":
                fields = {"text": "Start the background worker"}
            elif operation == "message":
                fields = {"text": "Tell the desktop app exactly this.",
                          "recipient": await select(client, owner)}
            else:
                _, card = await job(client, owner)
                fields = {**card, "text": "Cancel this job." if operation == "cancel" else "once"}
                if operation == "approval":
                    host.pending = [{"request_id": "approval-a", "allow_session": False}]
                    fields.update(request_id="approval-a", choice="once")
            text = fields.pop("text")
            first = await send(client, owner, operation, text, "repeat-" + operation, **fields)
            assert first.status_code == 200, first.text
            second = await send(client, owner, operation, text, "repeat-" + operation, **fields)
            assert second.status_code == 200, second.text
            assert second.json() == first.json()
            expected = {"start_worker": "accepted", "cancel": "posted",
                        "approval": "accepted", "message": "posted"}[operation]
            assert first.json()["state"] == expected
            jobs = 0 if operation == "message" else 1
            assert len(host.posts("/v1/runs")) == jobs and len(host.jobs) == jobs
            assert len(host.posts("/stop")) == (1 if operation == "cancel" else 0)
            approvals = host.posts("/approval")
            assert [body for _, body in approvals] == (
                [{"request_id": "approval-a", "choice": "once"}] if operation == "approval" else []
            )
            assert len(host.bridge.sends()) == (1 if operation == "message" else 0)
            if operation == "message":
                assert {key: first.json()["recipient"][key] for key in IDENTITY_FIELDS} == (
                    fields["recipient"]
                )
            interactions, _ = records(seam, owner)
            assert [row["input_id"] for row in interactions].count("repeat-" + operation) == 1
            assert history(seam).count(text) == 1

    asyncio.run(run())


def test_same_input_id_with_different_text_is_event_conflict(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            first = await send(client, owner, "start_worker", "Start the worker", "same-id")
            assert first.status_code == 200, first.text
            conflict = await send(client, owner, "start_worker", "Start a DIFFERENT worker",
                                  "same-id")
            assert conflict.status_code == 409 and code(conflict) == "event_conflict"
            interactions, _ = records(seam, owner)
            assert [row["input_id"] for row in interactions] == ["same-id"]
            assert len(seam.host.posts("/v1/runs")) == 1
            assert "Start a DIFFERENT worker" not in history(seam)

    asyncio.run(run())


def test_stale_generation_and_foreign_actor_refuse_before_persistence(seam):
    async def run():
        async with client_for(seam) as client:
            old = context(await attach(client))
            fresh = context(await attach(client, **old))
            assert fresh != old
            requests_before = len(seam.host.requests_all)
            for owner, headers, statuses in ((old, {}, {409}),
                                             (fresh, {"x-actor": "foreign-actor"}, {403, 409})):
                for operation, extra in (("message", {}), ("start_worker", {}),
                                         ("cancel", {"run_id": 1, "action_id": "card"})):
                    reply = await send(client, owner, operation, "Do not dispatch", "late",
                                       headers=headers, **extra)
                    assert reply.status_code in statuses, reply.text
                    if owner is old:
                        assert code(reply) == "connection_stale"
            interactions, actions = records(seam, fresh)
            assert interactions == [] and actions == []
            assert not seam.host.jobs and not seam.host.bridge.sends()
            mutations = [request for request in seam.host.requests_all[requests_before:]
                         if request.method == "POST"]
            assert mutations == []
            assert "Do not dispatch" not in history(seam)

    asyncio.run(run())


def test_recipient_identity_mismatch_refuses_without_send(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            identity = await select(client, owner)
            reply = await send(client, owner, "message", "Do not deliver this", "mismatch",
                               recipient={**identity, "task_id": "other-task"})
            assert reply.status_code == 409 and code(reply) == "recipient_selection_mismatch"
            assert not seam.host.bridge.sends()
            interactions, _ = records(seam, owner)
            assert interactions == [] and "Do not deliver this" not in history(seam)
            same = await send(client, owner, "message", "Do deliver this", "match",
                              recipient=identity)
            assert same.status_code == 200 and same.json()["state"] == "posted"

    asyncio.run(run())


def test_read_only_recipient_message_refused(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            identity = await select(client, owner, read_only=True)
            reply = await send(client, owner, "message", "Do not deliver this", "read-only",
                               recipient=identity)
            assert reply.status_code == 409 and code(reply) == "recipient_control_unavailable"
            assert not seam.host.bridge.sends()
            interactions, _ = records(seam, owner)
            assert interactions == [] and "Do not deliver this" not in history(seam)

    asyncio.run(run())


def test_recipient_message_persists_original_once_and_returns_bridge_status(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            identity = await select(client, owner)
            bridge = seam.host.bridge
            first = await send(client, owner, "message", "Exact words for the desktop app.",
                               "msg-one", recipient=identity)
            assert first.status_code == 200, first.text
            assert first.json()["state"] == "posted"
            assert {key: first.json()["recipient"][key] for key in IDENTITY_FIELDS} == identity
            assert "private-target" not in first.text
            assert history(seam).count("Exact words for the desktop app.") == 1
            assert bridge.sends()[0][1]["message"] == "Exact words for the desktop app."
            bridge.torn = True
            torn = await send(client, owner, "message", "A second exact message.", "msg-two",
                              recipient=identity)
            assert torn.status_code == 200 and torn.json()["state"] == "unknown", torn.text
            assert len(bridge.sends()) == 2
            repeat = await send(client, owner, "message", "A second exact message.", "msg-two",
                                recipient=identity)
            assert repeat.status_code == 200 and repeat.json()["state"] == "posted", repeat.text
            assert len(bridge.sends()) == 2
            assert sum(call[0] == "reconcile" for call in bridge.calls) == 1
            assert history(seam).count("A second exact message.") == 1
            interactions, actions = records(seam, owner)
            assert [row["input_id"] for row in interactions] == ["msg-one", "msg-two"]
            assert all(action["name"] == "send_agent_message" for action in actions)

    asyncio.run(run())


def test_start_worker_refused_when_codex_worker_unavailable(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            seam.host.codex_worker = False
            reply = await send(client, owner, "start_worker", "Start the worker", "no-codex")
            assert reply.status_code == 409 and code(reply) == "child_dispatch_unsupported"
            assert not seam.host.posts("/v1/runs") and not seam.host.jobs
            interactions, _ = records(seam, owner)
            assert interactions == [] and "Start the worker" not in history(seam)
            hermes = await send(client, owner, "start_worker", "Start the worker", "hermes",
                                worker="hermes")
            assert hermes.status_code == 200 and hermes.json()["state"] == "accepted"
            [(_, body)] = seam.host.posts("/v1/runs")
            assert "worker" not in body["child"] and body["input"] == "Start the worker"

    asyncio.run(run())


def test_steer_uses_original_words_and_returns_host_receipt_state(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            _, card = await job(client, owner)
            reply = await send(client, owner, "steer", STEER_TEXT, "steer-one",
                               run_id=card["run_id"])
            assert reply.status_code == 200, reply.text
            assert reply.json()["state"] == "queued" and reply.json()["run_id"] == card["run_id"]
            assert seam.host.deliveries[0]["input"] == STEER_TEXT
            _, actions = records(seam, owner)
            steer = next(action for action in actions if action["name"] == "steer_work")
            assert steer["control_input"] == STEER_TEXT
            assert steer["control_receipt"]["status"] == "queued"
            stale = await send(client, owner, "steer", "Again", "steer-two",
                               run_id=steer["run_id"])
            assert stale.status_code == 409 and code(stale) == "steering_target_denied"
            assert len(seam.host.deliveries) == 1 and "Again" not in history(seam)

    asyncio.run(run())


def test_cancel_on_unowned_run_or_stale_action_id_refused(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            _, card = await job(client, owner)
            host = seam.host
            remote = next(iter(host.jobs))
            host.jobs[remote]["session_id"] = "task-b"
            foreign = await send(client, owner, "cancel", "Cancel this job.", "cancel-foreign",
                                 **card)
            assert foreign.status_code == 403 and code(foreign) == "context_denied"
            host.jobs[remote]["session_id"] = "task-a"
            stale = await send(client, owner, "cancel", "Cancel this job.", "cancel-stale",
                               run_id=card["run_id"], action_id="stale-card")
            assert stale.status_code == 409 and code(stale) == "event_conflict"
            host.jobs[remote]["status"] = "completed"
            finished = await send(client, owner, "cancel", "Cancel this job.", "cancel-done",
                                  **card)
            assert finished.status_code == 409 and code(finished) == "gateway_refused"
            assert not host.posts("/stop")
            assert history(seam).count("Cancel this job.") == 1  # the refused terminal cancel
            host.jobs[remote]["status"] = "running"
            live = await send(client, owner, "cancel", "Cancel this job.", "cancel-live", **card)
            assert live.status_code == 200 and live.json()["state"] == "posted", live.text
            assert len(host.posts("/stop")) == 1 and host.jobs[remote]["status"] == "cancelled"

    asyncio.run(run())


def test_approval_with_stale_request_id_refused_and_actionable_flag_exposed(seam):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            _, card = await job(client, owner)
            host = seam.host
            host.pending = [{"request_id": "approval-a", "allow_session": False,
                             "command": "never-echo-this-command"}]
            state = await client.post("/state", json=owner)
            approval = state.json()["jobs"][0]["approval"]
            assert approval["actionable"] is True
            assert [row["request_id"] for row in approval["approvals"]] == ["approval-a"]
            assert "never-echo-this-command" not in state.text
            stale = await send(client, owner, "approval", "once", "approve-stale", **card,
                               request_id="approval-zzz", choice="once")
            assert stale.status_code == 409, stale.text
            assert not host.posts("/approval")
            assert host.pending[0]["request_id"] == "approval-a"
            live = await send(client, owner, "approval", "once", "approve-live", **card,
                              request_id="approval-a", choice="once")
            assert live.status_code == 200 and live.json()["state"] == "accepted", live.text
            assert [body for _, body in host.posts("/approval")] == [
                {"request_id": "approval-a", "choice": "once"}
            ]
            state = await client.post("/state", json=owner)
            assert state.json()["jobs"][0]["approval"] == {
                "state": "current", "approvals": [], "actionable": False,
            }

    asyncio.run(run())


@pytest.mark.parametrize("fields", [
    {"operation": "launch"},
    {"operation": "message", "run_id": 1},
    {"operation": "message", "recipient": {"recipient_id": "x"}},
    {"operation": "start_worker", "recipient": {}},
    {"operation": "start_worker", "worker": "gemini"},
    {"operation": "steer"},
    {"operation": "steer", "run_id": True},
    {"operation": "cancel", "run_id": 1, "action_id": "bad id"},
    {"operation": "approval", "run_id": 1, "action_id": "a", "request_id": "r", "choice": "maybe"},
    {"operation": "cancel", "run_id": 1, "action_id": "a", "attachments": [{"kind": "file"}]},
    {"operation": "cancel", "run_id": 1, "action_id": "a", "target_token": "private"},
    {"operation": "message", "text": ""},
    {"operation": "message", "input_id": "bad id"},
])
def test_invalid_shapes_refuse_before_binding_or_host_io(seam, fields):
    async def run():
        async with client_for(seam) as client:
            owner = context(await attach(client))
            before = len(seam.host.requests_all)
            reply = await client.post("/text/input", json={
                **owner, "input_id": "shape", "text": "Do not dispatch", "attachments": [],
                **fields,
            })
            assert reply.status_code == 400, reply.text
            assert code(reply) == "invalid_event"
            assert len(seam.host.requests_all) == before
            interactions, _ = records(seam, owner)
            assert interactions == []

    asyncio.run(run())


def test_no_token_in_any_error_body(seam, monkeypatch):
    errors, successes = [], []

    async def run():
        async with client_for(seam) as client:
            old = context(await attach(client))
            owner = context(await attach(client, **old))
            errors.append(await send(client, owner, "launch", "x", "shape"))
            errors.append(await send(client, old, "start_worker", "x", "stale"))
            errors.append(await send(client, owner, "start_worker", "x", "foreign",
                                     headers={"x-actor": "foreign-actor"}))
            identity = await select(client, owner)
            errors.append(await send(client, owner, "message", "x", "mismatch",
                                     recipient={**identity, "task_id": "other"}))
            stored = await select(client, owner, read_only=True)
            errors.append(await send(client, owner, "message", "x", "read-only", recipient=stored))
            successes.append(await select(client, owner))
            _, card = await job(client, owner)
            errors.append(await send(client, owner, "cancel", "x", "stale-card",
                                     run_id=card["run_id"], action_id="stale"))
            errors.append(await send(client, owner, "approval", "once", "stale-request", **card,
                                     request_id="approval-zzz", choice="once"))
            remote = next(iter(seam.host.jobs))
            seam.host.jobs[remote]["status"] = "completed"
            errors.append(await send(client, owner, "cancel", "x", "terminal", **card))
            seam.host.codex_worker = False
            errors.append(await send(client, owner, "start_worker", "x", "no-codex"))

    asyncio.run(run())
    assert all(reply.status_code >= 400 for reply in errors)
    monkeypatch.delenv("TALK_DASHBOARD_TOKEN")
    with pytest.raises(seam.api.HTTPException) as gate:
        asyncio.run(seam.text_input(RemoteRequest()))
    assert gate.value.status_code == 403
    bodies = [reply.text for reply in errors] + [json.dumps(gate.value.detail)]
    for body in bodies:
        assert "detail" in body or "TALK_DASHBOARD_TOKEN" in body
        for token in (*TOKENS, "private-target", "never-echo"):
            assert token not in body, body
