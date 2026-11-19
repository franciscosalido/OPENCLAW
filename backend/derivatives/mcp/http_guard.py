"""Guardas de entrada do servidor local, antes da validação e dos logs do SDK."""
from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP
from mcp.types import (
    CallToolRequest, CallToolRequestParams, CallToolResult, ClientNotification, ClientRequest,
    JSONRPCMessage, JSONRPCNotification, JSONRPCRequest, ServerResult, TextContent,
)
from starlette.requests import ClientDisconnect, Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _valid_call(name: str, arguments: object, demo_enabled: bool) -> bool:
    if name == "derivatives_health":
        return arguments is None or arguments == {}
    if name != "derivatives_chain" and not (demo_enabled and name == "derivatives_chain_demo"):
        return False
    return (isinstance(arguments, dict) and arguments.keys() == {"symbol", "due_date"}
            and all(isinstance(value, str) for value in arguments.values()))


def guard_tool_dispatch(server: FastMCP[Any], *, demo_enabled: bool) -> None:
    # O SDK consulta o cache e registra nomes em DEBUG antes do middleware FastMCP.
    # Protege também o transporte em memória, apenas nesta instância do servidor.
    handlers = server._mcp_server.request_handlers
    dispatch = handlers[CallToolRequest]

    async def guarded(request: CallToolRequest) -> ServerResult:
        params = request.params
        if not _valid_call(params.name, params.arguments, demo_enabled):
            return ServerResult(CallToolResult(
                isError=True, content=[TextContent(type="text", text="INVALID_TOOL_CALL")]))
        return await dispatch(request)

    handlers[CallToolRequest] = guarded


def _reject_json_constant(_: str) -> None:
    raise ValueError("invalid_json")


class LoopbackHeaders:
    def __init__(self, app: ASGIApp, *, port: int, demo_enabled: bool) -> None:
        self.demo_enabled = demo_enabled
        self.app = app
        self.authorities = {f"{host}:{port}".encode("ascii") for host in ("127.0.0.1", "localhost")}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = scope["headers"]
            hosts = [v for k, v in headers if k.lower() == b"host"]
            origins = [v for k, v in headers if k.lower() == b"origin"]
            if (
                len(hosts) != 1
                or hosts[0] not in self.authorities
                or (origins and origins != [b"http://" + hosts[0]])
            ):
                await Response(status_code=403)(scope, receive, send)
                return
            if scope["method"] == "POST":
                await self._post(scope, receive, send)
                return
        await self.app(scope, receive, send)

    async def _post(self, scope: Scope, receive: Receive, send: Send) -> None:
        # O SDK registra entradas inválidas. Valide sem registrar antes de delegar.
        body = bytearray()
        try:
            async for chunk in Request(scope, receive).stream():
                if len(body) + len(chunk) > 64 * 1024:
                    await Response(status_code=413)(scope, receive, send)
                    return
                body.extend(chunk)
        except ClientDisconnect:
            return
        request_id: int | str | None = None
        try:
            raw = json.loads(body.decode("utf-8"), parse_constant=_reject_json_constant)
            if not isinstance(raw, dict):
                raise ValueError("invalid_envelope")
            raw_id = raw.get("id")
            if type(raw_id) in (int, str):
                request_id = raw_id
            envelope = JSONRPCMessage.model_validate(raw).root
            if "method" in raw and "id" in raw:
                if not isinstance(envelope, JSONRPCRequest):
                    raise ValueError("invalid_request")
                ClientRequest.model_validate(raw)
                if raw["method"] == "tools/call":
                    params = CallToolRequestParams.model_validate(raw.get("params"))
                    if params.name not in ("derivatives_chain", "derivatives_health",
                                            "derivatives_chain_demo"):
                        # O SDK responde à ferramenta desconhecida sem receber o nome original.
                        raw["params"] = {"name": "unknown_tool", "arguments": {}}
                        body = bytearray(json.dumps(raw).encode())
                    elif not _valid_call(params.name, params.arguments, self.demo_enabled):
                        raise ValueError("invalid_tool_call")
            elif "method" in raw:
                if not isinstance(envelope, JSONRPCNotification):
                    raise ValueError("invalid_notification")
                ClientNotification.model_validate(raw)
        except (ValueError, RecursionError):
            await JSONResponse(
                {"jsonrpc": "2.0", "id": request_id, "error": {
                    "code": -32600, "message": "Invalid request",
                }},
                status_code=400,
            )(scope, receive, send)
            return
        first = True

        async def replay() -> Message:
            nonlocal first
            if first:
                first = False
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
