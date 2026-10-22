"""进程内验证工具注册与软失败返回，不启动子进程。"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from deepseek_search_mcp import core, server as server_module


def call(server, tool: str, args: dict) -> dict:
  raw = asyncio.run(server.call_tool(tool, args))
  if isinstance(raw, tuple):
    raw = raw[1]
  if hasattr(raw, "structuredContent") and isinstance(raw.structuredContent, dict):
    raw = raw.structuredContent
  if isinstance(raw, dict):
    return raw.get("result", raw)
  texts = [block.text for block in getattr(raw, "content", [])]
  import json

  return json.loads("\n".join(texts))


class ServerTests(unittest.TestCase):
  def setUp(self):
    self.server = server_module.create_server()

  def test_tools_registered(self):
    tools = asyncio.run(self.server.list_tools())
    self.assertEqual(sorted(t.name for t in tools), ["fetch", "search"])

  def test_search_error_is_soft_failure(self):
    with mock.patch.object(core, "search", side_effect=core.DeepSeekError("boom", status=403)):
      payload = call(self.server, "search", {"query": "x"})
    self.assertIn("boom", payload["error"])
    self.assertEqual(payload["status"], 403)

  def test_fetch_returns_core_payload(self):
    with mock.patch.object(core, "fetch", return_value={"title": "T", "content": "C"}):
      payload = call(self.server, "fetch", {"url": "https://example.com"})
    self.assertEqual(payload["title"], "T")


if __name__ == "__main__":
  unittest.main()
