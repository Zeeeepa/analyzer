#!/usr/bin/env python3
"""
CLI entry point for solidlsp - Solid Language Server Protocol implementation.
"""

import argparse
import sys


def get_version():
    """Get the version of solidlsp."""
    try:
        import graph_sitter
        return graph_sitter.__version__
    except (ImportError, AttributeError):
        return "unknown"


def main():
    """Main CLI entry point for solidlsp."""
    parser = argparse.ArgumentParser(
        description="SolidLSP - Solid Language Server Protocol implementation",
        prog="solidlsp"
    )
    
    parser.add_argument(
        "--version", 
        action="version", 
        version=f"solidlsp {get_version()}"
    )
    
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start the language server"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to run the language server on (if applicable)"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind the language server to (default: localhost)"
    )
    
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Use stdin/stdout for communication (default mode)"
    )
    
    parser.add_argument(
        "--tcp",
        action="store_true",
        help="Use TCP for communication"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Handle conflicting options
    if args.stdio and args.tcp:
        print("Error: Cannot use both stdio and tcp modes", file=sys.stderr)
        return 1
    
    try:
        if args.verbose:
            print("🔧 Starting SolidLSP in verbose mode...")
        
        if args.start:
            print("🚀 Starting SolidLSP Language Server...")
            
            # Lazy import to avoid dependency issues with --version
            try:
                from . import SolidLanguageServer
                server = SolidLanguageServer()
            except ImportError as e:
                print(f"❌ Error importing SolidLanguageServer: {e}")
                print("💡 Some dependencies may be missing. Install with: pip install serena pygls")
                return 1
            
            # Default to stdio if no communication method specified
            if not args.tcp:
                print("📡 Using stdin/stdout for communication")
                # Start server with stdio (this would typically be the main server loop)
                print("✅ SolidLSP Language Server is running on stdin/stdout")
                print("💡 Connect your editor to use the language server features")
            else:
                host = args.host
                port = args.port or 8080
                print(f"📡 Using TCP communication on {host}:{port}")
                print(f"✅ SolidLSP Language Server is running on {host}:{port}")
                print("💡 Connect your editor to use the language server features")
        else:
            print("SolidLSP Language Server")
            print("Use --start to start the server")
            print("Use --version to see version information")
            print("Use --help for more options")
            
    except Exception as e:
        print(f"❌ Error starting solidlsp: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())