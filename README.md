# deepseek-search-mcp

把 DeepSeek 的网页搜索（`/v1/tools/search`）与抓取（`/v1/tools/fetch`）包装成
MCP 工具，供 Codex 等客户端在**不切换模型**的情况下使用。

`fetch` 会自动还原 DeepSeek 接口加在 Markdown 标点前的反斜杠（如 `\#`、`\[`），
同时保留 `C:\Users`、`\n` 这类正常文本。

## 为什么需要它

Codex 内置的 `web_search` 工具只有 `deepseek-v4-pro` 会真正执行；`deepseek-flash`
收到该工具后会静默忽略。这个 MCP 服务直接调用 DeepSeek 的独立 Search/Fetch API，
与当前使用哪个模型无关。

## 密钥

优先读环境变量 `DEEPSEEK_API_KEY`；没有时从 `~/.codex/config.toml`（或
`$CODEX_HOME/config.toml`）里的 `experimental_bearer_token` 读取。

本压缩包**不包含任何 API Key**，请使用接收方自己的 Key。

## 安装

需要 Python 3.10 及以上。解压后进入目录执行：

```powershell
python -m pip install -e .
```

装完即可用 `python -m deepseek_search_mcp.server` 启动，不再依赖 `PYTHONPATH`。

## 本地运行

```powershell
python -m deepseek_search_mcp.client --list
python -m deepseek_search_mcp.client --call search --args '{"query":"DeepSeek V4","count":3}'
python -m deepseek_search_mcp.client --smoke
```

## 在 Codex 中注册

在 `~/.codex/config.toml` 追加（`command` 用实际的 python 绝对路径）：

```toml
[mcp_servers.deepseek_search]
command = 'C:\Python312\python.exe'
args = ["-m", "deepseek_search_mcp.server"]
startup_timeout_sec = 30
default_tools_approval_mode = "auto"

[mcp_servers.deepseek_search.env]
DEEPSEEK_API_KEY = "sk-换成自己的Key"
```

改完需要重启 Codex，新会话里会出现 `search` 与 `fetch` 两个工具。

## 局域网共享（Streamable HTTP）

默认仍是 stdio，仅本机可用。要供局域网内其他 Agent 调用，在**持有 API Key 的机器**上启动：

```powershell
$env:DEEPSEEK_SEARCH_TOKEN = "换成一个足够长的随机串"
python -m deepseek_search_mcp.server --transport http --host 0.0.0.0 --port 8765
```

端点地址是 `http://<本机局域网 IP>:8765/mcp`。启动前记得放行防火墙端口
（仅 Private 配置文件，别开公网）：

```powershell
New-NetFirewallRule -DisplayName "deepseek-search-mcp" -Direction Inbound `
  -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

其他 Codex 机器在 `config.toml` 里配置：

```toml
[mcp_servers.deepseek_search]
url = "http://192.168.1.50:8765/mcp"
http_headers = { Authorization = "Bearer 换成一个足够长的随机串" }
```

非 Codex 的 MCP 客户端使用 Streamable HTTP 传输连接同一个 URL，并带上
`Authorization: Bearer <token>` 请求头。

本机可以先自测：

```powershell
python -m deepseek_search_mcp.client --url http://127.0.0.1:8765/mcp --token $env:DEEPSEEK_SEARCH_TOKEN --list
```

注意：服务端持有你的 DeepSeek API Key，局域网内拿到令牌的人都会消耗你的额度；
务必设置 `--token`，不要把端口映射到公网。

## 测试

```powershell
cd deepseek-search-mcp
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```
