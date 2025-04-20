from mcp.server.lowlevel import Server
import mcp.types as types
import httpx
import os
import json
import glob

# 初始化服务器
app = Server("dev-tools-server")

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理来自客户端的工具调用。"""
    if name == "search_code":
        return await search_code(arguments.get("query", ""), arguments.get("directory", ""))
    elif name == "analyze_dependencies":
        return await analyze_dependencies(arguments.get("directory", "."))
    elif name == "fetch_documentation":
        return await fetch_documentation(arguments.get("package", ""))
    else:
        return [types.TextContent(type="text", text=f"错误：未知工具：{name}")]

async def search_code(query: str, directory: str) -> list[types.TextContent]:
    """在代码文件中搜索特定查询内容。"""
    results = []
    for ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css']:
        for filepath in glob.glob(f"{directory}/**/*{ext}", recursive=True):
            try:
                with open(filepath, 'r', encoding='utf-8') as file:
                    content = file.read()
                if query.lower() in content.lower():
                    match_context = get_context(content, query)
                    results.append(f"文件：{filepath}\n{match_context}\n--")
            except Exception as e:
                continue
    if results:
        return [types.TextContent(type="text", text="搜索结果：\n\n" + "\n".join(results))]
    else:
        return [types.TextContent(type="text", text=f"在目录'{directory}'中未找到与'{query}'匹配的结果。")]

def get_context(content: str, query: str, context_lines: int = 3) -> str:
    """获取匹配项周围的上下文。"""
    lines = content.split('\n')
    matches = []
    for i, line in enumerate(lines):
        if query.lower() in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            context = "\n".join(lines[start:end])
            matches.append(f"行{start+1}-{end}:\n{context}")
    return "\n\n".join(matches)

async def analyze_dependencies(directory: str) -> list[types.TextContent]:
    """分析项目依赖项。"""
    dependency_files = {
        'python': ['requirements.txt', 'setup.py', 'pyproject.toml'],
        'node': ['package.json'],
        'dotnet': ['*.csproj', '*.fsproj', '*.vbproj'],
    }
    results = []
    for lang, files in dependency_files.items():
        for file_pattern in files:
            for filepath in glob.glob(f"{directory}/**/{file_pattern}", recursive=True):
                try:
                    with open(filepath, 'r', encoding='utf-8') as file:
                        content = file.read()
                    results.append(f"在{filepath}中发现{lang}依赖项")
                except Exception:
                    continue
    if results:
        return [types.TextContent(type="text", text="依赖项分析：\n\n" + "\n".join(results))]
    else:
        return [types.TextContent(type="text", text=f"在目录'{directory}'中未找到依赖项文件。")]

async def fetch_documentation(package: str) -> list[types.TextContent]:
    """获取包的文档。"""
    try:
        # 对于Python包
        url = f"https://pypi.org/pypi/{package}/json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                summary = data.get("info", {}).get("summary", "无摘要可用")
                description = data.get("info", {}).get("description", "无描述可用")
                return [types.TextContent(type="text", text=f"{package}的文档：\n\n摘要：{summary}\n描述：{description}")]
    except Exception:
        pass
    # 如果PyPI失败，尝试npm包
    try:
        url = f"https://registry.npmjs.org/{package}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                description = data.get("description", "无描述可用")
                return [types.TextContent(type="text", text=f"{package}的文档：\n\n描述：{description}")]
    except Exception:
        pass
    return [types.TextContent(type="text", text=f"无法获取'{package}'的文档。")]

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """列出可用工具。"""
    return [
        types.Tool(
            name="search_code",
            description="在代码文件中搜索特定查询内容",
            inputSchema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "要在代码文件中搜索的查询内容"},
                    "directory": {"type": "string", "description": "搜索目录（默认：当前目录）"}
                }
            }
        ),
        types.Tool(
            name="analyze_dependencies",
            description="分析项目依赖项",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "分析目录（默认：当前目录）"}
                }
            }
        ),
        types.Tool(
            name="fetch_documentation",
            description="获取包的文档",
            inputSchema={
                "type": "object",
                "required": ["package"],
                "properties": {
                    "package": {"type": "string", "description": "要获取文档的包名"}
                }
            }
        )
    ]

if __name__ == "__main__":
    import sys
    # 默认使用标准输入输出传输
    transport = "stdio"
    port = 8000
    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == "sse":
            transport = "sse"
        if len(sys.argv) > 2:
            try:
                port = int(sys.argv[2])
            except ValueError:
                pass
    if transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        import uvicorn
        sse = SseServerTransport("/messages/")
        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await app.run(streams[0], streams[1], app.create_initialization_options())
        starlette_app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse),
                Mount("/messages/", app=sse.handle_post_message),
            ]
        )
        print(f"在端口{port}上启动MCP服务器，使用SSE传输")
        uvicorn.run(starlette_app, host="0.0.0.0", port=port)
    else:
        from mcp.server.stdio import stdio_server
        import anyio
        async def run_stdio():
            async with stdio_server() as streams:
                await app.run(streams[0], streams[1], app.create_initialization_options())
        print("使用标准输入输出传输启动MCP服务器")
        anyio.run(run_stdio)
