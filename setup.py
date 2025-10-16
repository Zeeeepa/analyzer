#!/usr/bin/env python3
"""Setup script for Analyzer - AI-Powered Code Analysis System"""

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
    packages=find_packages(where="Libraries"),
    package_dir={"": "Libraries"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        # Core dependencies
        "openai>=1.0.0",  # AI integration
        "requests>=2.28.0",  # HTTP requests
        
        # Code analysis
        "ruff>=0.1.0",  # Linting and formatting
        "mypy>=1.0.0",  # Type checking
        "pylint>=2.15.0",  # Additional linting
        
        # LSP and parsing
        "pygls>=1.0.0",  # Language Server Protocol
        "tree-sitter>=0.20.0",  # Code parsing
        
        # Utilities
        "pyyaml>=6.0",  # Configuration
        "rich>=13.0.0",  # Terminal formatting
        "click>=8.1.0",  # CLI framework
        "tqdm>=4.64.0",  # Progress bars
        
        # Database
        "sqlalchemy>=2.0.0",  # ORM
        
        # Testing (optional but recommended)
        "pytest>=7.0.0",
        "pytest-asyncio>=0.21.0",
        "pytest-cov>=4.0.0",
    ],
    extras_require={
        "dev": [
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "pre-commit>=3.0.0",
        ],
        "docs": [
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
        ],
        "all": [
            "black>=23.0.0",
            "isort>=5.12.0",
            "flake8>=6.0.0",
            "pre-commit>=3.0.0",
            "sphinx>=6.0.0",
            "sphinx-rtd-theme>=1.2.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "analyzer=analyzer:main",
            "analyzer-cli=analyzer:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.yml", "*.yaml", "*.json", "*.md"],
    },
    zip_safe=False,
    project_urls={
        "Bug Reports": "https://github.com/Zeeeepa/analyzer/issues",
        "Source": "https://github.com/Zeeeepa/analyzer",
        "Documentation": "https://github.com/Zeeeepa/analyzer/blob/main/DOCUMENTATION.md",
    },
)

