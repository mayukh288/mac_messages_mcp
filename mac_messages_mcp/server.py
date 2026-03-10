#!/usr/bin/env python3
"""
Mac Messages MCP - Entry point fixed for proper MCP protocol implementation
"""

import logging
import sys

from fastmcp import Context, FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse, StreamingResponse
from starlette.requests import Request
from starlette.middleware.cors import CORSMiddleware

from mac_messages_mcp.messages import (
    _check_imessage_availability,
    check_addressbook_access,
    check_messages_db_access,
    find_contact_by_name,
    fuzzy_search_messages,
    get_cached_contacts,
    get_recent_messages,
    query_messages_db,
    send_message,
)

# Configure logging to stderr for debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s',
    stream=sys.stderr
)

logger = logging.getLogger("mac_messages_mcp")

# Initialize the MCP server
logger.debug("Initializing FastMCP server...")
mcp = FastMCP("MessageBridge")
logger.debug("FastMCP server initialized successfully")

# Global cache for tools to avoid repeated async calls
_cached_tools = None

@mcp.tool()
def tool_get_recent_messages(ctx: Context, hours: int = 24, contact: str = None) -> str:
    """
    Get recent messages from the Messages app.
    
    Args:
        hours: Number of hours to look back (default: 24)
        contact: Filter by contact name, phone number, or email (optional)
                Use "contact:N" to select a specific contact from previous matches
    """
    logger.info(f"[TOOL] Getting recent messages: hours={hours}, contact={contact}")
    logger.debug(f"Calling get_recent_messages with hours={hours}, contact={contact}")
    try:
        # Handle contacts that are passed as numbers
        if contact is not None:
            contact = str(contact)
        result = get_recent_messages(hours=hours, contact=contact)
        return result
    except Exception as e:
        logger.error(f"Error in get_recent_messages: {str(e)}")
        return f"Error getting messages: {str(e)}"

@mcp.tool()
def tool_send_message(ctx: Context, recipient: str, message: str, group_chat: bool = False) -> str:
    """
    Send a message using the Messages app.
    
    Args:
        recipient: Phone number, email, contact name, or "contact:N" to select from matches.
                  For example, "contact:1" selects the first contact from a previous search.
                  For group chats, use the chat ID from tool_get_chats (e.g., "chat123456789" or "iMessage;-;chat123456789").
        message: Message text to send
        group_chat: Set to True when sending to a group chat. Uses the chat ID directly without contact lookup.
    """
    logger.info(f"[TOOL] Sending message to: {recipient}, group_chat: {group_chat}")
    logger.debug(f"Message content length: {len(message)}")
    try:
        # Ensure recipient is a string (handles numbers properly)
        recipient = str(recipient)
        result = send_message(recipient=recipient, message=message, group_chat=group_chat)
        return result
    except Exception as e:
        logger.error(f"Error in send_message: {str(e)}")
        return f"Error sending message: {str(e)}"

@mcp.tool()
def tool_find_contact(ctx: Context, name: str) -> str:
    """
    Find a contact by name using fuzzy matching.
    
    Args:
        name: The name to search for
    """
    logger.info(f"[TOOL] Finding contact: {name}")
    logger.debug(f"Starting contact lookup for: {name}")
    try:
        matches = find_contact_by_name(name)
        
        if not matches:
            return f"No contacts found matching '{name}'."
        
        if len(matches) == 1:
            contact = matches[0]
            return f"Found contact: {contact['name']} ({contact['phone']}) with confidence {contact['score']:.2f}"
        else:
            # Format multiple matches
            result = [f"Found {len(matches)} contacts matching '{name}':"]
            for i, contact in enumerate(matches[:10]):  # Limit to top 10
                result.append(f"{i+1}. {contact['name']} ({contact['phone']}) - confidence {contact['score']:.2f}")
            
            if len(matches) > 10:
                result.append(f"...and {len(matches) - 10} more.")
            
            return "\n".join(result)
    except Exception as e:
        logger.error(f"Error in find_contact: {str(e)}")
        return f"Error finding contact: {str(e)}"

@mcp.tool()
def tool_check_db_access(ctx: Context) -> str:
    """
    Diagnose database access issues.
    """
    logger.info("Checking database access")
    try:
        return check_messages_db_access()
    except Exception as e:
        logger.error(f"Error checking database access: {str(e)}")
        return f"Error checking database access: {str(e)}"

@mcp.tool()
def tool_check_contacts(ctx: Context) -> str:
    """
    List available contacts in the address book.
    """
    logger.info("Checking available contacts")
    try:
        contacts = get_cached_contacts()
        if not contacts:
            return "No contacts found in AddressBook."
        
        contact_count = len(contacts)
        sample_entries = list(contacts.items())[:10]  # Show first 10 contacts
        formatted_samples = [f"{number} -> {name}" for number, name in sample_entries]
        
        result = [
            f"Found {contact_count} contacts in AddressBook.",
            "Sample entries (first 10):",
            *formatted_samples
        ]
        
        return "\n".join(result)
    except Exception as e:
        logger.error(f"Error checking contacts: {str(e)}")
        return f"Error checking contacts: {str(e)}"

@mcp.tool()
def tool_check_addressbook(ctx: Context) -> str:
    """
    Diagnose AddressBook access issues.
    """
    logger.info("Checking AddressBook access")
    try:
        return check_addressbook_access()
    except Exception as e:
        logger.error(f"Error checking AddressBook: {str(e)}")
        return f"Error checking AddressBook: {str(e)}"

@mcp.tool()
def tool_get_chats(ctx: Context) -> str:
    """
    List available group chats from the Messages app.
    """
    logger.info("Getting available chats")
    try:
        query = "SELECT chat_identifier, display_name FROM chat WHERE display_name IS NOT NULL"
        results = query_messages_db(query)
        
        if not results:
            return "No group chats found."
        
        if "error" in results[0]:
            return f"Error accessing chats: {results[0]['error']}"
        
        # Filter out chats without display names and format the results
        chats = [r for r in results if r.get('display_name')]
        
        if not chats:
            return "No named group chats found."
        
        formatted_chats = []
        for i, chat in enumerate(chats, 1):
            formatted_chats.append(f"{i}. {chat['display_name']} (ID: {chat['chat_identifier']})")
        
        return "Available group chats:\n" + "\n".join(formatted_chats)
    except Exception as e:
        logger.error(f"Error getting chats: {str(e)}")
        return f"Error getting chats: {str(e)}"


@mcp.tool()
def tool_check_imessage_availability(ctx: Context, recipient: str) -> str:
    """
    Check if a recipient has iMessage available.
    
    This tool helps determine whether to send via iMessage or SMS/RCS.
    Useful for debugging delivery issues or choosing the right service.
    
    Args:
        recipient: Phone number or email to check for iMessage availability
    """
    logger.info(f"Checking iMessage availability for: {recipient}")
    try:
        recipient = str(recipient)
        has_imessage = _check_imessage_availability(recipient)
        
        if has_imessage:
            return f"✅ {recipient} has iMessage available - messages will be sent via iMessage"
        else:
            # Check if it looks like a phone number for SMS fallback
            if any(c.isdigit() for c in recipient):
                return f"📱 {recipient} does not have iMessage - messages will automatically fall back to SMS/RCS"
            else:
                return f"❌ {recipient} does not have iMessage and SMS is not available for email addresses"
    except Exception as e:
        logger.error(f"Error checking iMessage availability: {str(e)}")
        return f"Error checking iMessage availability: {str(e)}"

@mcp.tool()
def tool_fuzzy_search_messages(
    ctx: Context, search_term: str, hours: int = 24, threshold: float = 0.6
) -> str:
    """
    Fuzzy search for messages containing the search_term within the last N hours.
    Returns messages that match the search term with a similarity score.

    Args:
        search_term: The text to search for in messages.
        hours: How many hours back to search (default 24). Must be positive.
        threshold: Similarity threshold for matching (0.0 to 1.0, default 0.6). Lower is more lenient.
    """
    if not (0.0 <= threshold <= 1.0):
        return "Error: Threshold must be between 0.0 and 1.0."
    if hours <= 0:
        return "Error: Hours must be a positive integer."

    logger.info(
        f"Tool: Fuzzy searching messages for '{search_term}' in last {hours} hours with threshold {threshold}"
    )
    try:
        result = fuzzy_search_messages(
            search_term=search_term, hours=hours, threshold=threshold
        )
        return result
    except Exception as e:
        logger.error(f"Error in tool_fuzzy_search_messages: {e}", exc_info=True)
        return f"An unexpected error occurred during fuzzy message search: {str(e)}"


@mcp.resource("messages://recent/{hours}")
def get_recent_messages_resource(hours: int = 24) -> str:
    """Resource that provides recent messages."""
    return get_recent_messages(hours=hours)

@mcp.resource("messages://contact/{contact}/{hours}")
def get_contact_messages_resource(contact: str, hours: int = 24) -> str:
    """Resource that provides messages from a specific contact."""
    return get_recent_messages(hours=hours, contact=contact)


def _preload_tools() -> None:
    """Pre-load tools once at startup for compatibility endpoints."""
    logger.debug("Pre-loading tool list for caching (max 100ms)...")

    global _cached_tools

    import asyncio
    import concurrent.futures

    def load_tools():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(mcp.list_tools())
            finally:
                loop.close()
        except Exception as exc:
            logger.warning(f"Could not pre-load tools: {exc}")
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(load_tools)
        try:
            _cached_tools = future.result(timeout=0.1)
            logger.debug(f"Successfully cached {len(_cached_tools)} tools in <100ms")
        except concurrent.futures.TimeoutError:
            logger.warning("Tool list preload timed out (>100ms), using empty cache")
            _cached_tools = []
        except Exception as exc:
            logger.warning(f"Tool list preload error: {exc}")
            _cached_tools = []


async def tools_list_compat(request: Request):
    """Handle tools/list requests without requiring MCP session for compatibility."""
    logger.debug("Serving tools/list via compatibility endpoint")

    try:
        if _cached_tools is None:
            logger.warning("Tool cache not initialized")
            tool_list = []
        else:
            tool_list = [
                {
                    "name": tool.name,
                    "description": tool.description.strip(),
                    "inputSchema": tool.inputSchema,
                }
                for tool in _cached_tools
            ]

        response_data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": tool_list},
        }

        async def generate_sse():
            import json

            json_str = json.dumps(response_data, separators=(",", ":"))
            yield f"event: message\ndata: {json_str}\n\n"

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "mcp-session-id": f"compat-{id(request)}",
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        logger.error(f"Error in compatibility tools/list: {exc}")
        error_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32603, "message": "Internal error"},
        }

        async def generate_error():
            import json

            yield f"event: message\ndata: {json.dumps(error_response)}\n\n"

        return StreamingResponse(
            generate_error(),
            media_type="text/event-stream",
            status_code=500,
            headers={"mcp-session-id": f"error-{id(request)}"},
        )


async def root_handler(request: Request):
    """Handle compatibility requests sent to the root path by browser extensions."""
    origin = request.headers.get("origin", "")

    if origin.startswith("chrome-extension://"):
        try:
            body = await request.body()
            import json

            request_data = json.loads(body.decode("utf-8"))
            method = request_data.get("method")

            if method == "initialize":
                logger.debug("Browser extension initialize request, returning server info")
                init_response = {
                    "jsonrpc": "2.0",
                    "id": request_data.get("id", 1),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {
                            "name": "mac-messages-mcp",
                            "version": "1.0.0",
                        },
                    },
                }

                async def generate_init():
                    yield f"event: message\ndata: {json.dumps(init_response)}\n\n"

                return StreamingResponse(
                    generate_init(),
                    media_type="text/event-stream",
                    headers={
                        "mcp-session-id": f"init-{id(request)}",
                        "Cache-Control": "no-cache, no-transform",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )

            if method == "tools/list":
                logger.debug("Browser extension tools/list request, redirecting to compatibility endpoint")
                return await tools_list_compat(request)

            logger.debug(f"Browser extension {method} request - not supported, returning SSE error")
            error_response = {
                "jsonrpc": "2.0",
                "id": request_data.get("id", 1),
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not supported by compatibility endpoint",
                },
            }

            async def generate_error():
                yield f"event: message\ndata: {json.dumps(error_response)}\n\n"

            return StreamingResponse(
                generate_error(),
                media_type="text/event-stream",
                status_code=200,
                headers={
                    "mcp-session-id": f"error-{id(request)}",
                    "Cache-Control": "no-cache, no-transform",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        except Exception as exc:
            logger.debug(f"Could not parse request body: {exc}")
            error_response = {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32700, "message": "Parse error"},
            }

            async def generate_parse_error():
                import json

                yield f"event: message\ndata: {json.dumps(error_response)}\n\n"

            return StreamingResponse(
                generate_parse_error(),
                media_type="text/event-stream",
                status_code=200,
                headers={
                    "mcp-session-id": f"parse-error-{id(request)}",
                    "Cache-Control": "no-cache, no-transform",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

    return JSONResponse({"error": "Not found"}, status_code=404)


def create_http_app() -> Starlette:
    """Build the HTTP app with FastMCP-managed lifespan and compatibility routes."""
    _preload_tools()

    managed_mcp_app = mcp.http_app(path="/mcp", transport="streamable-http")

    starlette_app = Starlette(
        routes=[
            Route("/tools-list-compat", tools_list_compat, methods=["POST"]),
            Route("/", root_handler, methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]),
            Mount("/", app=managed_mcp_app),
        ],
        lifespan=managed_mcp_app.lifespan,
    )

    return CORSMiddleware(
        starlette_app,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def run_server():
    """Run the MCP server with proper error handling"""
    try:
        logger.info("=" * 60)
        logger.info("Starting Mac Messages MCP server...")
        logger.info("=" * 60)
        logger.info("Server configuration:")
        logger.info("  - Server name: MessageBridge")
        logger.info("  - Transport: streamable-http (HTTP server)")
        logger.info("  - Host: 0.0.0.0 (accessible from browser extensions)")
        logger.info("  - Port: 8001")
        logger.info("  - Protocol: MCP (Model Context Protocol)")
        logger.info("  - Logging level: DEBUG")
        logger.info("  - CORS: Enabled for browser access")
        logger.debug("Available tools registered: 9 tools")
        logger.debug("  - tool_get_recent_messages")
        logger.debug("  - tool_send_message")
        logger.debug("  - tool_find_contact")
        logger.debug("  - tool_check_db_access")
        logger.debug("  - tool_check_contacts")
        logger.debug("  - tool_check_addressbook")
        logger.debug("  - tool_get_chats")
        logger.debug("  - tool_check_imessage_availability")
        logger.debug("  - tool_fuzzy_search_messages")
        logger.info("Attempting to start HTTP server using streamable-http transport...")
        
        try:
            import uvicorn
            logger.debug("Creating lifecycle-managed HTTP app from FastMCP...")
            asgi_app = create_http_app()
            
            logger.info("✓ Server initialized and ready")
            logger.info("=" * 60)
            logger.info(f"🚀 Mac Messages MCP server is running!")
            logger.info(f"   📡 Listening on: http://0.0.0.0:8001")
            logger.info(f"   🌐 For browser extension, use: http://localhost:8001")
            logger.info(f"   Protocol: MCP over HTTP (streamable-http)")
            logger.info(f"   CORS: Enabled for cross-origin requests")
            logger.info(f"   Debug: All requests will be logged to console")
            logger.info("=" * 60)
            
            # Run the ASGI server on port 8001, bound to all interfaces
            logger.debug("Starting uvicorn with CORS-enabled ASGI app on 0.0.0.0:8001...")
            logger.info("Waiting for connections from browser extension...")
            uvicorn.run(
                asgi_app, 
                host="0.0.0.0", 
                port=8001, 
                log_level="info"
            )
        except Exception as e:
            logger.error(f"Failed to start HTTP server: {str(e)}", exc_info=True)
            logger.info("Falling back to stdio mode (standard MCP protocol)...")
            logger.debug("Using mcp.run('stdio') for stdio mode")
            logger.info("Server running in stdio mode (for direct process communication)")
            mcp.run(transport='stdio')
            
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal server error: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    run_server()
