from fastmcp import FastMCP
mcp = FastMCP("TestMessages")
@mcp.tool()
def get_recent_messages(hours: int = 24):
    from mac_messages_mcp.messages import get_recent_messages
    return get_recent_messages(hours=hours)
if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8001, host="0.0.0.0")

