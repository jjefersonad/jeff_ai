import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

async def load_context7_tools():
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@upstash/context7-mcp@latest"],
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            return tools

# Carrega as tools de forma síncrona para passar ao create_deep_agent
context7_tools = asyncio.run(load_context7_tools())
