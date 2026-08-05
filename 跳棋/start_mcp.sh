#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python mcp_server.py --transport stdio
