#!/usr/bin/env python3
"""
CLI entry point for autogenlib - Automatic code generation library using OpenAI.
"""

import argparse
import sys

from . import init, set_exception_handler, set_caching


def get_version():
    """Get the version of autogenlib."""
    try:
        import graph_sitter
        return graph_sitter.__version__
    except (ImportError, AttributeError):
        return "unknown"


def main():
    """Main CLI entry point for autogenlib."""
    parser = argparse.ArgumentParser(
        description="Autogenlib - Automatic code generation library using OpenAI",
        prog="autogenlib"
    )
    
    parser.add_argument(
        "--version", 
        action="version", 
        version=f"autogenlib {get_version()}"
    )
    
    parser.add_argument(
        "--init",
        type=str,
        help="Initialize autogenlib with a description of the functionality needed"
    )
    
    parser.add_argument(
        "--enable-exception-handler",
        action="store_true",
        help="Enable the global exception handler that sends exceptions to LLM for fix suggestions"
    )
    
    parser.add_argument(
        "--disable-exception-handler",
        action="store_true",
        help="Disable the global exception handler"
    )
    
    parser.add_argument(
        "--enable-caching",
        action="store_true",
        help="Enable caching of generated code"
    )
    
    parser.add_argument(
        "--disable-caching",
        action="store_true",
        help="Disable caching of generated code"
    )
    
    args = parser.parse_args()
    
    # Handle conflicting options
    if args.enable_exception_handler and args.disable_exception_handler:
        print("Error: Cannot both enable and disable exception handler", file=sys.stderr)
        return 1
    
    if args.enable_caching and args.disable_caching:
        print("Error: Cannot both enable and disable caching", file=sys.stderr)
        return 1
    
    # Initialize with options
    description = args.init if args.init else None
    exception_handler = None
    caching = None
    
    if args.enable_exception_handler:
        exception_handler = True
    elif args.disable_exception_handler:
        exception_handler = False
    
    if args.enable_caching:
        caching = True
    elif args.disable_caching:
        caching = False
    
    # Initialize autogenlib
    try:
        init(desc=description, enable_exception_handler=exception_handler, enable_caching=caching)
        print("✅ Autogenlib initialized successfully!")
        
        if description:
            print(f"📝 Description set to: {description}")
        if exception_handler is not None:
            print(f"🛡️ Exception handler: {'enabled' if exception_handler else 'disabled'}")
        if caching is not None:
            print(f"💾 Caching: {'enabled' if caching else 'disabled'}")
            
    except Exception as e:
        print(f"❌ Error initializing autogenlib: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())