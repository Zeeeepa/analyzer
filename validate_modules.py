#!/usr/bin/env python3
"""
Module and Adapter Validation Script

This script validates that all modules and adapters in the analyzer
work correctly after library synchronization.

Usage:
    python validate_modules.py              # Validate all
    python validate_modules.py --quick      # Quick validation
    python validate_modules.py --verbose    # Verbose output
"""

import argparse
import importlib
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add Libraries to path
REPO_ROOT = Path(__file__).parent
LIBRARIES_DIR = REPO_ROOT / "Libraries"
sys.path.insert(0, str(LIBRARIES_DIR))


class ModuleValidator:
    """Validates modules and adapters."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = {}

    def validate_import(self, module_name: str, description: str = "") -> Tuple[bool, str]:
        """Validate that a module can be imported."""
        try:
            module = importlib.import_module(module_name)
            if self.verbose:
                logger.info(f"✅ {module_name}: Successfully imported")
                if hasattr(module, '__file__'):
                    logger.info(f"   Location: {module.__file__}")
            return True, "OK"
        except ImportError as e:
            logger.error(f"❌ {module_name}: Import failed - {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"⚠️  {module_name}: Unexpected error - {e}")
            return False, str(e)

    def validate_library_modules(self) -> Dict[str, bool]:
        """Validate synced library modules."""
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATING LIBRARY MODULES")
        logger.info("=" * 60)

        modules_to_test = [
            ("autogenlib", "Autogenlib core module"),
            ("serena", "Serena semantic editing module"),
            ("graph_sitter", "Graph-sitter core from graph_sitter_lib"),
        ]

        results = {}
        for module_name, description in modules_to_test:
            logger.info(f"\nTesting: {description}")
            success, error = self.validate_import(module_name, description)
            results[module_name] = success

        return results

    def validate_adapter_modules(self) -> Dict[str, bool]:
        """Validate adapter modules."""
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATING ADAPTER MODULES")
        logger.info("=" * 60)

        adapters = [
            ("static_libs", "Static libraries and utilities"),
            ("lsp_adapter", "LSP adapter for real-time diagnostics"),
            ("autogenlib_adapter", "Autogenlib integration adapter"),
            ("graph_sitter_adapter", "Graph-sitter AST parsing adapter"),
            ("analyzer", "Core analyzer orchestrator"),
        ]

        results = {}
        for adapter_name, description in adapters:
            logger.info(f"\nTesting: {description}")
            success, error = self.validate_import(adapter_name, description)
            results[adapter_name] = success

        return results

    def validate_adapter_classes(self) -> Dict[str, bool]:
        """Validate specific classes in adapters."""
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATING ADAPTER CLASSES")
        logger.info("=" * 60)

        tests = [
            ("static_libs", "Severity", "Severity enum"),
            ("static_libs", "ErrorCategory", "ErrorCategory enum"),
            ("static_libs", "CacheManager", "Cache manager class"),
            ("static_libs", "ErrorDatabase", "Error database class"),
            ("lsp_adapter", "LSPDiagnosticsManager", "LSP diagnostics manager"),
            ("lsp_adapter", "RuntimeErrorCollector", "Runtime error collector"),
        ]

        results = {}
        for module_name, class_name, description in tests:
            test_id = f"{module_name}.{class_name}"
            logger.info(f"\nTesting: {description}")
            
            try:
                module = importlib.import_module(module_name)
                cls = getattr(module, class_name)
                
                if self.verbose:
                    logger.info(f"✅ {test_id}: Found")
                    logger.info(f"   Type: {type(cls)}")
                else:
                    logger.info(f"✅ {test_id}: Found")
                
                results[test_id] = True
            except ImportError as e:
                logger.error(f"❌ {test_id}: Module import failed - {e}")
                results[test_id] = False
            except AttributeError as e:
                logger.error(f"❌ {test_id}: Class not found - {e}")
                results[test_id] = False
            except Exception as e:
                logger.error(f"⚠️  {test_id}: Unexpected error - {e}")
                results[test_id] = False

        return results

    def validate_adapter_functions(self) -> Dict[str, bool]:
        """Validate specific functions in adapters."""
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATING ADAPTER FUNCTIONS")
        logger.info("=" * 60)

        tests = [
            ("autogenlib_adapter", "get_llm_codebase_overview", "LLM codebase overview function"),
            ("autogenlib_adapter", "get_file_context", "File context extraction function"),
            ("autogenlib_adapter", "get_comprehensive_symbol_context", "Symbol context function"),
        ]

        results = {}
        for module_name, func_name, description in tests:
            test_id = f"{module_name}.{func_name}"
            logger.info(f"\nTesting: {description}")
            
            try:
                module = importlib.import_module(module_name)
                func = getattr(module, func_name)
                
                if callable(func):
                    if self.verbose:
                        logger.info(f"✅ {test_id}: Found and callable")
                        logger.info(f"   Type: {type(func)}")
                    else:
                        logger.info(f"✅ {test_id}: Found and callable")
                    results[test_id] = True
                else:
                    logger.error(f"❌ {test_id}: Found but not callable")
                    results[test_id] = False
            except ImportError as e:
                logger.error(f"❌ {test_id}: Module import failed - {e}")
                results[test_id] = False
            except AttributeError as e:
                logger.error(f"❌ {test_id}: Function not found - {e}")
                results[test_id] = False
            except Exception as e:
                logger.error(f"⚠️  {test_id}: Unexpected error - {e}")
                results[test_id] = False

        return results

    def print_summary(self):
        """Print validation summary."""
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 60)

        all_results = {}
        for category_results in self.results.values():
            all_results.update(category_results)

        total = len(all_results)
        passed = sum(1 for v in all_results.values() if v)
        failed = total - passed

        logger.info(f"\nTotal Tests: {total}")
        logger.info(f"Passed: {passed} ✅")
        logger.info(f"Failed: {failed} ❌")
        logger.info(f"Success Rate: {(passed/total*100):.1f}%")

        if failed > 0:
            logger.info("\nFailed Tests:")
            for test_name, success in all_results.items():
                if not success:
                    logger.info(f"  ❌ {test_name}")

        return failed == 0

    def run_all(self, quick: bool = False) -> bool:
        """Run all validations."""
        self.results['library_modules'] = self.validate_library_modules()
        self.results['adapter_modules'] = self.validate_adapter_modules()
        
        if not quick:
            self.results['adapter_classes'] = self.validate_adapter_classes()
            self.results['adapter_functions'] = self.validate_adapter_functions()

        return self.print_summary()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate analyzer modules and adapters"
    )
    parser.add_argument(
        "--quick",
        "-q",
        action="store_true",
        help="Quick validation (skip detailed checks)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    validator = ModuleValidator(verbose=args.verbose)

    try:
        success = validator.run_all(quick=args.quick)
        return 0 if success else 1
    except KeyboardInterrupt:
        logger.info("\nValidation interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

