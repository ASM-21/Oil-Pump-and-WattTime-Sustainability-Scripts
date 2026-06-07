"""FastMCP server. Run as `python mcp_server.py`.

Communicates over stdio with whichever client spawns it (agent_loop.py,
Claude Desktop, MCP Inspector, Cursor).
"""

from fastmcp import FastMCP
from tools import ALL_TOOLS

mcp = FastMCP("openlca")

for fn in ALL_TOOLS:
    mcp.tool(fn)


if __name__ == "__main__":
    mcp.run()
