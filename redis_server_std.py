from mcp.server.lowlevel import Server
import mcp.types as types
import redis.asyncio as redis
import json
import os
import anyio
from mcp.server.stdio import stdio_server

# 初始化服务器
app = Server("redis-tools-server")

# Redis连接配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# 创建Redis连接池
redis_pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True
)

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理来自客户端的工具调用。"""
    async with redis.Redis(connection_pool=redis_pool) as client:
        if name == "set_value":
            return await set_value(client, arguments.get("key"), arguments.get("value"), arguments.get("expiry"))
        elif name == "get_value":
            return await get_value(client, arguments.get("key"))
        elif name == "delete_key":
            return await delete_key(client, arguments.get("key"))
        elif name == "list_keys":
            return await list_keys(client, arguments.get("pattern", "*"))
        elif name == "list_push":
            return await list_push(client, arguments.get("key"), arguments.get("value"))
        elif name == "list_range":
            return await list_range(client, arguments.get("key"), arguments.get("start", 0), arguments.get("end", -1))
        elif name == "batch_list_push":
            return await batch_list_push(client, arguments.get("items", {}))
        else:
            return [types.TextContent(type="text", text=f"错误：未知工具：{name}")]

async def set_value(client: redis.Redis, key: str, value: str, expiry: int = None) -> list[types.TextContent]:
    """设置Redis键值对。"""
    try:
        await client.set(key, value, ex=expiry)
        return [types.TextContent(type="text", text=f"成功设置键'{key}'的值")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"设置键'{key}'失败：{str(e)}")]

async def get_value(client: redis.Redis, key: str) -> list[types.TextContent]:
    """获取Redis键的值。"""
    try:
        value = await client.get(key)
        if value is None:
            return [types.TextContent(type="text", text=f"键'{key}'不存在")]
        return [types.TextContent(type="text", text=f"键'{key}'的值为：{value}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"获取键'{key}'失败：{str(e)}")]

async def delete_key(client: redis.Redis, key: str) -> list[types.TextContent]:
    """删除Redis键。"""
    try:
        result = await client.delete(key)
        if result:
            return [types.TextContent(type="text", text=f"成功删除键'{key}'")]
        return [types.TextContent(type="text", text=f"键'{key}'不存在")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"删除键'{key}'失败：{str(e)}")]

async def list_keys(client: redis.Redis, pattern: str) -> list[types.TextContent]:
    """列出匹配模式的所有键。"""
    try:
        keys = await client.keys(pattern)
        if not keys:
            return [types.TextContent(type="text", text=f"没有找到匹配'{pattern}'的键")]
        return [types.TextContent(type="text", text="找到的键：\n" + "\n".join(keys))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"列出键失败：{str(e)}")]

async def list_push(client: redis.Redis, key: str, value: str) -> list[types.TextContent]:
    """向列表尾部添加元素。"""
    try:
        length = await client.rpush(key, value)
        return [types.TextContent(type="text", text=f"成功添加值到列表'{key}'，当前列表长度：{length}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"添加值到列表'{key}'失败：{str(e)}")]

async def list_range(client: redis.Redis, key: str, start: int, end: int) -> list[types.TextContent]:
    """获取列表指定范围的元素。"""
    try:
        values = await client.lrange(key, start, end)
        if not values:
            return [types.TextContent(type="text", text=f"列表'{key}'为空或不存在")]
        return [types.TextContent(type="text", text=f"列表'{key}'的元素：\n" + "\n".join(values))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"获取列表'{key}'的元素失败：{str(e)}")]

async def batch_list_push(client: redis.Redis, items: dict) -> list[types.TextContent]:
    """批量设置多个列表。
    
    Args:
        items: 字典格式，key为列表名，value为要添加的值列表
        例如: {"2024": ["20240101", "20240102"], "2025": ["20250101"]}
    """
    try:
        results = []
        for key, values in items.items():
            # 先删除已存在的列表
            await client.delete(key)
            if values:
                # 批量添加新值
                length = await client.rpush(key, *values)
                results.append(f"成功添加{len(values)}个值到列表'{key}'，当前列表长度：{length}")
        
        return [types.TextContent(type="text", text="批量设置结果：\n" + "\n".join(results))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"批量设置列表失败：{str(e)}")]

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """列出可用工具。"""
    return [
        types.Tool(
            name="batch_list_push",
            description="批量设置多个列表",
            inputSchema={
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "object",
                        "description": "要设置的列表数据，格式为：{'key1': ['value1', 'value2'], 'key2': ['value3']}"
                    }
                }
            }
        ),
        types.Tool(
            name="set_value",
            description="设置Redis键值对",
            inputSchema={
                "type": "object",
                "required": ["key", "value"],
                "properties": {
                    "key": {"type": "string", "description": "键名"},
                    "value": {"type": "string", "description": "值"},
                    "expiry": {"type": "integer", "description": "过期时间（秒）"}
                }
            }
        ),
        types.Tool(
            name="get_value",
            description="获取Redis键的值",
            inputSchema={
                "type": "object",
                "required": ["key"],
                "properties": {
                    "key": {"type": "string", "description": "键名"}
                }
            }
        ),
        types.Tool(
            name="delete_key",
            description="删除Redis键",
            inputSchema={
                "type": "object",
                "required": ["key"],
                "properties": {
                    "key": {"type": "string", "description": "要删除的键名"}
                }
            }
        ),
        types.Tool(
            name="list_keys",
            description="列出匹配模式的所有键",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "匹配模式，默认为*"}
                }
            }
        ),
        types.Tool(
            name="list_push",
            description="向列表尾部添加元素",
            inputSchema={
                "type": "object",
                "required": ["key", "value"],
                "properties": {
                    "key": {"type": "string", "description": "列表键名"},
                    "value": {"type": "string", "description": "要添加的值"}
                }
            }
        ),
        types.Tool(
            name="list_range",
            description="获取列表指定范围的元素",
            inputSchema={
                "type": "object",
                "required": ["key"],
                "properties": {
                    "key": {"type": "string", "description": "列表键名"},
                    "start": {"type": "integer", "description": "起始位置（默认0）"},
                    "end": {"type": "integer", "description": "结束位置（默认-1）"}
                }
            }
        )
    ]

async def main():
    """主函数：使用stdio模式运行服务器"""
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())

if __name__ == "__main__":
    print("使用标准输入输出传输启动Redis MCP服务器")
    anyio.run(main) 
