"""MCP stdio 客户端：列举工具、单次调用、端到端冒烟。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

SRC_DIR = Path(__file__).resolve().parents[1]


def server_params() -> StdioServerParameters:
  env = dict(os.environ)
  env.setdefault("PYTHONIOENCODING", "utf-8")
  return StdioServerParameters(
    command=sys.executable,
    args=["-m", "deepseek_search_mcp.server"],
    env=env,
    cwd=str(SRC_DIR),
  )


def connect(url: str | None, token: str | None):
  """按 URL 选择 Streamable HTTP，否则起本地 stdio 子进程。"""
  if not url:
    return stdio_client(server_params())
  headers = {"Authorization": f"Bearer {token}"} if token else None
  return streamablehttp_client(url, headers=headers)


def unwrap(result: Any) -> Any:
  if isinstance(result, tuple) and len(result) == 2:
    result = result[1]
  structured = getattr(result, "structuredContent", None)
  if isinstance(structured, dict):
    return structured.get("result", structured)
  texts = [
    block.text
    for block in (getattr(result, "content", None) or [])
    if isinstance(block, types.TextContent)
  ]
  joined = "\n".join(texts)
  try:
    return json.loads(joined)
  except (ValueError, TypeError):
    return joined


async def list_tools(url: str | None = None, token: str | None = None) -> int:
  async with connect(url, token) as (read, write, *_):
    async with ClientSession(read, write) as session:
      init = await session.initialize()
      tools = await session.list_tools()
      print(f"server={init.serverInfo.name} 协议={init.protocolVersion}")
      for tool in tools.tools:
        required = tool.inputSchema.get("required", [])
        print(f"- {tool.name}: {tool.description} 必填={required or '无'}")
      return 0


async def call_one(
  tool: str, raw_args: str, url: str | None = None, token: str | None = None
) -> int:
  args = json.loads(raw_args) if raw_args else {}
  async with connect(url, token) as (read, write, *_):
    async with ClientSession(read, write) as session:
      await session.initialize()
      result = await session.call_tool(tool, args)
      print(json.dumps(unwrap(result), ensure_ascii=False, indent=2, default=str))
      return 1 if result.isError else 0


async def smoke(url: str | None = None, token: str | None = None) -> int:
  async with connect(url, token) as (read, write, *_):
    async with ClientSession(read, write) as session:
      init = await session.initialize()
      print(f"1) 握手成功 server={init.serverInfo.name}")

      tools = await session.list_tools()
      names = sorted(tool.name for tool in tools.tools)
      print(f"2) 工具列表 {names}")
      if names != ["fetch", "search"]:
        print("   工具列表不符合预期")
        return 1

      found = unwrap(await session.call_tool("search", {"query": "DeepSeek V4", "count": 3}))
      count = found.get("returned") if isinstance(found, dict) else None
      print(f"3) search → returned={count} 首条={found.get('results', [{}])[0].get('title') if count else '-'}")
      if not count:
        return 1

      page = unwrap(
        await session.call_tool(
          "fetch", {"url": "https://api-docs.deepseek.com/zh-cn/guides/search"}
        )
      )
      chars = page.get("content_chars") if isinstance(page, dict) else None
      print(f"4) fetch → title={page.get('title') if isinstance(page, dict) else '-'} chars={chars}")
      return 0 if chars else 1


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(prog="deepseek_search_mcp.client")
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument("--list", action="store_true", help="列出工具")
  group.add_argument("--call", metavar="TOOL", help="调用某个工具")
  group.add_argument("--smoke", action="store_true", help="端到端冒烟")
  parser.add_argument("--args", default="{}", help="--call 的 JSON 参数")
  parser.add_argument("--url", help="远端 Streamable HTTP 地址，例如 http://192.168.1.5:8765/mcp")
  parser.add_argument(
    "--token",
    default=os.environ.get("DEEPSEEK_SEARCH_TOKEN"),
    help="远端访问令牌（也读 DEEPSEEK_SEARCH_TOKEN）",
  )
  options = parser.parse_args(argv)

  if options.list:
    return asyncio.run(list_tools(options.url, options.token))
  if options.call:
    return asyncio.run(call_one(options.call, options.args, options.url, options.token))
  return asyncio.run(smoke(options.url, options.token))


if __name__ == "__main__":
  raise SystemExit(main())
