"""
MCP server entry point.

Command-line interface for starting and managing the Hopper MCP server.
"""

import asyncio
import sys
import logging

from .server import create_server


async def main() -> None:
    """Main entry point for the MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr,  # MCP uses stderr for logs, stdout for protocol
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting Hopper MCP server...")

    try:
        server = await create_server()
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
