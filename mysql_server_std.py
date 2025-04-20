from mcp.server.lowlevel import Server
import mcp.types as types
import aiomysql
import json
import os
import anyio
from mcp.server.stdio import stdio_server

# 初始化服务器
app = Server("mysql-tools-server")

# MySQL连接配置
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "")

# MySQL连接池
pool = None

async def get_pool():
    """获取MySQL连接池"""
    global pool
    if pool is None:
        pool = await aiomysql.create_pool(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DB,
            autocommit=True
        )
    return pool

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理来自客户端的工具调用。"""
    pool = await get_pool()
    if name == "execute_query":
        return await execute_query(pool, arguments.get("sql"))
    elif name == "list_tables":
        return await list_tables(pool)
    elif name == "describe_table":
        return await describe_table(pool, arguments.get("table_name"))
    elif name == "list_databases":
        return await list_databases(pool)
    elif name == "use_database":
        return await use_database(pool, arguments.get("database"))
    elif name == "insert_data":
        return await insert_data(pool, arguments.get("table_name"), arguments.get("data"))
    elif name == "delete_data":
        return await delete_data(pool, arguments.get("table_name"), arguments.get("condition"))
    elif name == "update_data":
        return await update_data(pool, arguments.get("table_name"), arguments.get("data"), arguments.get("condition"))
    else:
        return [types.TextContent(type="text", text=f"错误：未知工具：{name}")]

async def execute_query(pool: aiomysql.Pool, sql: str) -> list[types.TextContent]:
    """执行SQL查询。"""
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                if sql.lower().startswith(("select", "show", "desc", "describe")):
                    rows = await cur.fetchall()
                    columns = [col[0] for col in cur.description]
                    result = [dict(zip(columns, row)) for row in rows]
                    return [types.TextContent(type="text", text=f"查询结果：\n{json.dumps(result, ensure_ascii=False, indent=2)}")]
                else:
                    affected = cur.rowcount
                    return [types.TextContent(type="text", text=f"执行成功，影响行数：{affected}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"执行SQL失败：{str(e)}")]

async def insert_data(pool: aiomysql.Pool, table_name: str, data: dict) -> list[types.TextContent]:
    """插入数据。
    
    Args:
        table_name: 表名
        data: 要插入的数据，格式为字典 {"column1": "value1", "column2": "value2"}
    """
    try:
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ["%s"] * len(values)
        
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, values)
                return [types.TextContent(type="text", text=f"成功插入数据到表 {table_name}，影响行数：{cur.rowcount}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"插入数据失败：{str(e)}")]

async def delete_data(pool: aiomysql.Pool, table_name: str, condition: str) -> list[types.TextContent]:
    """删除数据。
    
    Args:
        table_name: 表名
        condition: 删除条件，例如 "id = 1" 或 "name = 'test'"
    """
    try:
        sql = f"DELETE FROM {table_name} WHERE {condition}"
        
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                return [types.TextContent(type="text", text=f"成功从表 {table_name} 删除数据，影响行数：{cur.rowcount}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"删除数据失败：{str(e)}")]

async def update_data(pool: aiomysql.Pool, table_name: str, data: dict, condition: str) -> list[types.TextContent]:
    """更新数据。
    
    Args:
        table_name: 表名
        data: 要更新的数据，格式为字典 {"column1": "value1", "column2": "value2"}
        condition: 更新条件，例如 "id = 1" 或 "name = 'test'"
    """
    try:
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        values = list(data.values())
        
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {condition}"
        
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, values)
                return [types.TextContent(type="text", text=f"成功更新表 {table_name} 的数据，影响行数：{cur.rowcount}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"更新数据失败：{str(e)}")]

async def list_tables(pool: aiomysql.Pool) -> list[types.TextContent]:
    """列出当前数据库的所有表。"""
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW TABLES")
                tables = await cur.fetchall()
                if not tables:
                    return [types.TextContent(type="text", text="当前数据库没有表")]
                return [types.TextContent(type="text", text="数据库表：\n" + "\n".join([table[0] for table in tables]))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"获取表列表失败：{str(e)}")]

async def describe_table(pool: aiomysql.Pool, table_name: str) -> list[types.TextContent]:
    """描述表结构。"""
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"DESCRIBE {table_name}")
                columns = await cur.fetchall()
                if not columns:
                    return [types.TextContent(type="text", text=f"表 {table_name} 不存在")]
                result = []
                for col in columns:
                    result.append(f"字段：{col[0]}, 类型：{col[1]}, 可空：{col[2]}, 键：{col[3]}, 默认值：{col[4]}, 额外：{col[5]}")
                return [types.TextContent(type="text", text=f"表 {table_name} 结构：\n" + "\n".join(result))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"获取表结构失败：{str(e)}")]

async def list_databases(pool: aiomysql.Pool) -> list[types.TextContent]:
    """列出所有数据库。"""
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW DATABASES")
                databases = await cur.fetchall()
                if not databases:
                    return [types.TextContent(type="text", text="没有找到任何数据库")]
                return [types.TextContent(type="text", text="数据库列表：\n" + "\n".join([db[0] for db in databases]))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"获取数据库列表失败：{str(e)}")]

async def use_database(pool: aiomysql.Pool, database: str) -> list[types.TextContent]:
    """切换数据库。"""
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"USE {database}")
                return [types.TextContent(type="text", text=f"已切换到数据库：{database}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"切换数据库失败：{str(e)}")]

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """列出可用工具。"""
    return [
        types.Tool(
            name="execute_query",
            description="执行SQL查询",
            inputSchema={
                "type": "object",
                "required": ["sql"],
                "properties": {
                    "sql": {"type": "string", "description": "SQL查询语句"}
                }
            }
        ),
        types.Tool(
            name="list_tables",
            description="列出当前数据库的所有表",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="describe_table",
            description="描述表结构",
            inputSchema={
                "type": "object",
                "required": ["table_name"],
                "properties": {
                    "table_name": {"type": "string", "description": "表名"}
                }
            }
        ),
        types.Tool(
            name="list_databases",
            description="列出所有数据库",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="use_database",
            description="切换数据库",
            inputSchema={
                "type": "object",
                "required": ["database"],
                "properties": {
                    "database": {"type": "string", "description": "数据库名"}
                }
            }
        ),
        types.Tool(
            name="insert_data",
            description="插入数据到指定表",
            inputSchema={
                "type": "object",
                "required": ["table_name", "data"],
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "data": {"type": "object", "description": "要插入的数据，格式为：{\"column1\": \"value1\", \"column2\": \"value2\"}"}
                }
            }
        ),
        types.Tool(
            name="delete_data",
            description="从指定表删除数据",
            inputSchema={
                "type": "object",
                "required": ["table_name", "condition"],
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "condition": {"type": "string", "description": "删除条件，例如：id = 1"}
                }
            }
        ),
        types.Tool(
            name="update_data",
            description="更新指定表的数据",
            inputSchema={
                "type": "object",
                "required": ["table_name", "data", "condition"],
                "properties": {
                    "table_name": {"type": "string", "description": "表名"},
                    "data": {"type": "object", "description": "要更新的数据，格式为：{\"column1\": \"value1\", \"column2\": \"value2\"}"},
                    "condition": {"type": "string", "description": "更新条件，例如：id = 1"}
                }
            }
        )
    ]

async def main():
    """主函数：使用stdio模式运行服务器"""
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())

if __name__ == "__main__":
    print("使用标准输入输出传输启动MySQL MCP服务器")
    anyio.run(main) 
