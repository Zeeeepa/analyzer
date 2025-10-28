#!/usr/bin/env python3
"""Setup script for Analyzer - AI-Powered Code Analysis System

This setup.py installs all necessary dependencies including:
- serena (git+https://github.com/Zeeeepa/serena)
- autogenlib (git+https://github.com/Zeeeepa/autogenlib)
- graph-sitter (git+https://github.com/Zeeeepa/graph-sitter)

Installation:
    pip install -e .                    # Install analyzer + all dependencies
    pip install -e ".[dev]"            # Include dev tools
    pip install -e ".[all]"            # Include everything
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
if requirements_file.exists():
    requirements = requirements_file.read_text().splitlines()
    requirements = [r.strip() for r in requirements if r.strip() and not r.startswith('#')]
else:
    requirements = []

setup(
    name="analyzer",
    version="1.0.0",
    author="Zeeeepa",
    author_email="zeeeepa@gmail.com",
    description="AI-Powered Code Analysis and Automated Error Resolution System",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Zeeeepa/analyzer",
    
    # Package configuration
    packages=find_packages(where="Libraries"),
    package_dir={"": "Libraries"},
    
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    
    python_requires=">=3.8",
    
    install_requires=[
        # ============================================================
        # CORE AI & ANALYSIS LIBRARIES (from submodules/repos)
        # ============================================================
        
        # Serena - Powerful semantic code analysis and symbol navigation
        # Install from: https://github.com/Zeeeepa/serena
        "serena @ git+https://github.com/Zeeeepa/serena.git@main",
        
        # AutoGenLib - AI-powered code generation and fixing
        # Install from: https://github.com/Zeeeepa/autogenlib  
        "autogenlib @ git+https://github.com/Zeeeepa/autogenlib.git@main",
        
        # Graph-Sitter - Advanced code parsing with tree-sitter
        # Install from: https://github.com/Zeeeepa/graph-sitter
        "graph-sitter @ git+https://github.com/Zeeeepa/graph-sitter.git@main",
        
        # ============================================================
        # AI & LLM INTEGRATION
        # ============================================================
        "openai>=1.0.0",              # OpenAI API integration
        "anthropic>=0.18.0",          # Claude API (Anthropic)
        "cohere>=4.0.0",              # Cohere embeddings
        "tiktoken>=0.5.0",            # Token counting for LLMs
        
        # ============================================================
        # CODE ANALYSIS & LINTING
        # ============================================================
        "ruff>=0.1.0",                # Fast Python linter & formatter
        "mypy>=1.0.0",                # Static type checking
        "pylint>=2.15.0",             # Comprehensive linting
        "bandit>=1.7.0",              # Security issue detection
        "radon>=6.0.0",               # Code complexity metrics
        "vulture>=2.7",               # Dead code detection
        
        # ============================================================
        # LSP & LANGUAGE SERVERS
        # ============================================================
        "pygls>=1.0.0",               # Language Server Protocol implementation
        "python-lsp-server>=1.7.0",  # Python LSP server
        "jedi>=0.19.0",               # Python completion/analysis
        "rope>=1.7.0",                # Python refactoring library
        
        # ============================================================
        # CODE PARSING & AST
        # ============================================================
        "tree-sitter>=0.20.0",        # Universal code parser
        "libcst>=1.0.0",              # Concrete Syntax Tree for Python
        "astroid>=3.0.0",             # Python AST enhancement
        
        # ============================================================
        # UTILITIES & CLI
        # ============================================================
        "click>=8.1.0",               # CLI framework
        "rich>=13.0.0",               # Terminal formatting & progress
        "tqdm>=4.64.0",               # Progress bars
        "colorama>=0.4.6",            # Cross-platform colored terminal
        "questionary>=2.0.0",         # Interactive prompts
        
        # ============================================================
        # CONFIGURATION & DATA
        # ============================================================
        "pyyaml>=6.0",                # YAML parsing
        "toml>=0.10.2",               # TOML parsing
        "python-dotenv>=1.0.0",       # Environment variable management
        "pydantic>=2.0.0",            # Data validation
        "attrs>=23.0.0",              # Class decoration
        
        # ============================================================
        # HTTP & NETWORKING
        # ============================================================
        "requests>=2.28.0",           # HTTP library
        "httpx>=0.24.0",              # Async HTTP client
        "aiohttp>=3.8.0",             # Async HTTP framework
        "websockets>=11.0",           # WebSocket client/server
        
        # ============================================================
        # DATABASE & STORAGE
        # ============================================================
        "sqlalchemy>=2.0.0",          # SQL ORM
        "alembic>=1.11.0",            # Database migrations
        "redis>=4.6.0",               # Redis client (caching)
        "diskcache>=5.6.0",           # Disk-based caching
        
        # ============================================================
        # ASYNC & CONCURRENCY
        # ============================================================
        "asyncio>=3.4.3",             # Async I/O
        "aiofiles>=23.0.0",           # Async file operations
        "aiocache>=0.12.0",           # Async caching
        
        # ============================================================
        # TESTING & QUALITY ASSURANCE
        # ============================================================
        "pytest>=7.0.0",              # Testing framework
        "pytest-asyncio>=0.21.0",     # Async pytest support
        "pytest-cov>=4.0.0",          # Coverage plugin
        "pytest-xdist>=3.3.0",        # Parallel test execution
        "pytest-mock>=3.11.0",        # Mocking fixtures
        "hypothesis>=6.82.0",         # Property-based testing
        
        # ============================================================
        # MONITORING & LOGGING
        # ============================================================
        "structlog>=23.1.0",          # Structured logging
        "loguru>=0.7.0",              # Advanced logging
        "sentry-sdk>=1.28.0",         # Error tracking
        
        # ============================================================
        # SERIALIZATION & FORMAT HANDLING
        # ============================================================
        "msgpack>=1.0.5",             # Binary serialization
        "orjson>=3.9.0",              # Fast JSON library
        "ujson>=5.8.0",               # Ultra-fast JSON
        
        # ============================================================
        # SECURITY & ENCRYPTION
        # ============================================================
        "cryptography>=41.0.0",       # Cryptographic recipes
        "pycryptodome>=3.18.0",       # Crypto library
        "python-jose>=3.3.0",         # JWT handling
        
        # ============================================================
        # DATE & TIME
        # ============================================================
        "python-dateutil>=2.8.2",     # Date utilities
        "arrow>=1.2.3",               # Better dates/times
        "pendulum>=2.1.2",            # DateTime library
        
        # ============================================================
        # FILE & PATH UTILITIES
        # ============================================================
        "pathspec>=0.11.0",           # Path pattern matching
        "watchdog>=3.0.0",            # Filesystem monitoring
        "send2trash>=1.8.0",          # Safe file deletion
        
        # ============================================================
        # TEXT PROCESSING
        # ============================================================
        "jinja2>=3.1.0",              # Template engine
        "markdown>=3.4.0",            # Markdown processing
        "beautifulsoup4>=4.12.0",     # HTML/XML parsing
        "lxml>=4.9.0",                # XML processing
        "chardet>=5.0.0",             # Character encoding detection
        
        # ============================================================
        # PROCESS & SYSTEM
        # ============================================================
        "psutil>=5.9.0",              # System and process utilities
        "setproctitle>=1.3.0",        # Process title setting
        
        # ============================================================
        # VERSION CONTROL
        # ============================================================
        "gitpython>=3.1.30",          # Git interface
        "pygit2>=1.12.0",             # Git bindings
        
        # ============================================================
        # DATA SCIENCE (for metrics/analysis)
        # ============================================================
        "numpy>=1.24.0",              # Numerical computing
        "pandas>=2.0.0",              # Data analysis
        "scipy>=1.10.0",              # Scientific computing
        "scikit-learn>=1.3.0",        # Machine learning metrics
        
        # ============================================================
        # GRAPHING & VISUALIZATION (for analysis reports)
        # ============================================================
        "matplotlib>=3.7.0",          # Plotting library
        "plotly>=5.14.0",             # Interactive plots
        "graphviz>=0.20.0",           # Graph visualization
        "networkx>=3.1.0",            # Graph/network analysis
    ],
    
    extras_require={
        # Development tools
        "dev": [
            "black>=23.0.0",              # Code formatter
            "isort>=5.12.0",              # Import sorting
            "flake8>=6.0.0",              # Style checker
            "pre-commit>=3.0.0",          # Pre-commit hooks
            "pyupgrade>=3.3.0",           # Syntax upgrader
            "autoflake>=2.1.0",           # Remove unused imports
            "pydocstyle>=6.3.0",          # Docstring checker
        ],
        
        # Documentation
        "docs": [
            "sphinx>=6.0.0",              # Documentation generator
            "sphinx-rtd-theme>=1.2.0",    # ReadTheDocs theme
            "sphinx-autodoc-typehints>=1.23.0",  # Type hint docs
            "myst-parser>=2.0.0",         # Markdown support
        ],
        
        # Performance profiling
        "profiling": [
            "py-spy>=0.3.0",              # Sampling profiler
            "memory-profiler>=0.61.0",    # Memory profiling
            "line-profiler>=4.0.0",       # Line-by-line profiling
            "scalene>=1.5.0",             # CPU/GPU/memory profiler
        ],
        
        # Complete installation
        "all": [
            # Dev tools
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "pre-commit>=3.0.0",
            "pyupgrade>=3.3.0",
            "autoflake>=2.1.0",
            "pydocstyle>=6.3.0",
            
            # Docs
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
            "sphinx-autodoc-typehints>=1.23.0",
            "myst-parser>=2.0.0",
            
            # Profiling
            "py-spy>=0.3.0",
            "memory-profiler>=0.61.0",
            "line-profiler>=4.0.0",
            "scalene>=1.5.0",
        ],
    },
    
    entry_points={
        "console_scripts": [
            "analyzer=analyzer:main",
            "analyzer-cli=analyzer:main",
            "rr-analyze=analyzer:main",  # RR_analysis alias
        ],
    },
    
    include_package_data=True,
    package_data={
        "": [
            "*.yml",
            "*.yaml", 
            "*.json",
            "*.md",
            "*.txt",
            "*.toml",
        ],
    },
    
    zip_safe=False,
    
    project_urls={
        "Bug Reports": "https://github.com/Zeeeepa/analyzer/issues",
        "Source": "https://github.com/Zeeeepa/analyzer",
        "Documentation": "https://github.com/Zeeeepa/analyzer/blob/main/DOCUMENTATION.md",
        "Serena Library": "https://github.com/Zeeeepa/serena",
        "AutoGenLib": "https://github.com/Zeeeepa/autogenlib",
        "Graph-Sitter": "https://github.com/Zeeeepa/graph-sitter",
    },
)

