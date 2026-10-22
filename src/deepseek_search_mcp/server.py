"""MCP 协议层：暴露 search 与 fetch 两个工具。

stdio 传输下 stdout 只属于 JSON-RPC，日志一律走 stderr。
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.types import ASGIApp, Receive, Scope, Send

from . import core

logger = logging.getLogger("deepseek_search_mcp")

INSTRUCTIONS = (
  "本服务提供 DeepSeek 的网页搜索与网页抓取：search 按关键词返回结构化结果，"
  "fetch 把单个网页抓成 Markdown。需要实时信息或读取网页正文时使用。"
  "搜索支持 site:、lang:、after:、before: 等语法。"
)


class BearerAuthMiddleware:
  """给 Streamable HTTP 端点加一层简单的 Bearer 令牌校验。"""

  def __init__(self, app: ASGIApp, token: str):
    self.app = app
    self.token = token
    self._expected = f"Bearer {token}".encode("utf-8")

  async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] == "http":
      headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
      }
      actual = headers.get("authorization", "").encode("utf-8")
      if not secrets.compare_digest(actual, self._expected):
        body = b'{"error":"unauthorized"}'
        await send(
          {
            "type": "http.response.start",
            "status": 401,
            "headers": [
              (b"content-type", b"application/json"),
              (b"content-length", str(len(body)).encode()),
            ],
          }
        )
        await send({"type": "http.response.body", "body": body})
        return
    await self.app(scope, receive, send)


def _error_payload(exc: core.DeepSeekError) -> dict[str, Any]:
  return {"error": str(exc), "status": getattr(exc, "status", None)}


def create_server(host: str = "127.0.0.1", port: int = 8765) -> FastMCP:
  server = FastMCP(
    name="deepseek-search",
    instructions=INSTRUCTIONS,
    host=host,
    port=port,
    # 局域网部署时 Host 头是机器 IP，默认的 DNS rebinding 白名单会拒绝；
    # 访问控制由 Bearer 令牌负责。
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
  )

  @server.tool(
    name="search",
    title="DeepSeek 网页搜索",
    description=(
      "用 DeepSeek 自研搜索引擎检索网页，返回 title、url、snippet、summary、"
      "date、authority 等字段。需要正文时把 need_content 设为 true。"
    ),
  )
  def search(
    query: Annotated[str, Field(description="搜索词，1-128 个字符，支持 site:/lang:/after: 等语法")],
    count: Annotated[int, Field(description="返回条数，1-50", ge=1, le=50)] = 10,
    need_content: Annotated[bool, Field(description="是否在结果中附带网页正文")] = False,
  ) -> dict[str, Any]:
    try:
      return core.search(query, count, need_content)
    except core.DeepSeekError as exc:
      return _error_payload(exc)

  @server.tool(
    name="fetch",
    title="DeepSeek 网页抓取",
    description="抓取单个 http/https 网页，返回 Markdown 正文（超长内容会截断并标记）。",
  )
  def fetch(
    url: Annotated[str, Field(description="要抓取的网页地址，必须带 http/https 和 host")],
  ) -> dict[str, Any]:
    try:
      return core.fetch(url)
    except core.DeepSeekError as exc:
      return _error_payload(exc)

  return server


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(prog="deepseek_search_mcp.server")
  parser.add_argument(
    "--transport",
    choices=["stdio", "http"],
    default=os.environ.get("DEEPSEEK_SEARCH_TRANSPORT", "stdio"),
    help="stdio 给本机客户端；http 给局域网客户端（默认读 DEEPSEEK_SEARCH_TRANSPORT）",
  )
  parser.add_argument(
    "--host",
    default=os.environ.get("DEEPSEEK_SEARCH_HOST", "127.0.0.1"),
    help="监听地址；局域网共享用 0.0.0.0",
  )
  parser.add_argument(
    "--port",
    type=int,
    default=int(os.environ.get("DEEPSEEK_SEARCH_PORT", "8765")),
    help="监听端口，默认 8765",
  )
  parser.add_argument(
    "--token",
    default=os.environ.get("DEEPSEEK_SEARCH_TOKEN"),
    help="访问令牌；http 模式下强烈建议设置（默认读 DEEPSEEK_SEARCH_TOKEN）",
  )
  return parser.parse_args(argv)


def _run_http(server: FastMCP, host: str, port: int, token: str | None) -> None:
  import uvicorn

  app = server.streamable_http_app()
  if token:
    app = BearerAuthMiddleware(app, token)
  else:
    logger.warning("未设置访问令牌：局域网内任何人都能调用并消耗你的 DeepSeek 配额")
  logger.info("Streamable HTTP 监听 http://%s:%s/mcp", host, port)
  uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
  logging.basicConfig(
    level=os.environ.get("DEEPSEEK_SEARCH_LOG_LEVEL", "INFO").upper(),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
  )
  args = _parse_args()
  server = create_server(host=args.host, port=args.port)
  logger.info("启动 deepseek-search MCP：transport=%s pid=%s", args.transport, os.getpid())
  if args.transport == "stdio":
    server.run(transport="stdio")
  else:
    _run_http(server, args.host, args.port, args.token)


if __name__ == "__main__":
  main()
