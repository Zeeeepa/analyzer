"""Smoke tests for Libraries/ modules.
Tests:
1. AST parsing (syntax validation)
2. Module importability  
3. Basic positive/negative function tests (where safe)
4. Interface validation for key adapters
"""

import ast
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add Libraries to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "Libraries"))


def test_ast_parsing() -> Dict[str, Any]:
    """Test that all Python files in Libraries/ can be parsed as valid AST."""
    results = {
        "name": "AST Parsing Test",
        "passed": 0,
        "failed": 0,
        "errors": [],
        "details": {}
    }
    
    libraries_path = Path(__file__).parent.parent / "Libraries"
    
    for py_file in libraries_path.glob("*.py"):
        if py_file.name.startswith("."):
            continue
            
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse AST
            tree = ast.parse(content)
            
            # Count basic metrics
            functions = len([n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)])
            classes = len([n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)])
            imports = len([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))])
            
            results["details"][py_file.name] = {
                "status": "PASS",
                "functions": functions,
                "classes": classes,
                "imports": imports,
                "lines": len(content.splitlines())
            }
            results["passed"] += 1
            
        except SyntaxError as e:
            results["failed"] += 1
            error_msg = f"Syntax error in {py_file.name}: {e}"
            results["errors"].append(error_msg)
            results["details"][py_file.name] = {"status": "FAIL", "error": str(e)}
        except Exception as e:
            results["failed"] += 1
            error_msg = f"Error parsing {py_file.name}: {e}"
            results["errors"].append(error_msg)
            results["details"][py_file.name] = {"status": "ERROR", "error": str(e)}
    
    return results


def test_module_importability() -> Dict[str, Any]:
    """Test that Libraries modules can be imported without errors."""
    results = {
        "name": "Module Importability Test",
        "passed": 0,
        "failed": 0,
        "errors": [],
        "details": {}
    }
    
    # Test main adapter modules
    modules_to_test = [
        "analyzer",
        "autogenlib_adapter", 
        "graph_sitter_adapter",
        "serena_adapter",
        "static_libs",
        "lsp_adapter"
    ]
    
    for module_name in modules_to_test:
        try:
            # Try importing the module
            __import__(module_name)
            results["details"][module_name] = {"status": "PASS", "error": None}
            results["passed"] += 1
            
        except ImportError as e:
            results["failed"] += 1
            error_msg = f"Import error in {module_name}: {e}"
            results["errors"].append(error_msg)
            results["details"][module_name] = {"status": "FAIL", "error": str(e)}
        except Exception as e:
            results["failed"] += 1
            error_msg = f"Unexpected error importing {module_name}: {e}"
            results["errors"].append(error_msg)
            results["details"][module_name] = {"status": "ERROR", "error": str(e)}
    
    return results


def test_static_libs_functions() -> Dict[str, Any]:
    """Test key functions from static_libs.py with positive/negative cases."""
    results = {
        "name": "Static Library Functions Test",
        "passed": 0,
        "failed": 0,
        "errors": [],
        "details": {}
    }
    
    try:
        import static_libs
        
        # Test LibraryManager (if it exists)
        if hasattr(static_libs, 'LibraryManager'):
            try:
                # Test with a temporary directory
                with tempfile.TemporaryDirectory() as temp_dir:
                    manager = static_libs.LibraryManager(temp_dir, "test_source")
                    results["details"]["LibraryManager_init"] = {"status": "PASS", "error": None}
                    results["passed"] += 1
                    
                    # Test basic methods if they exist
                    if hasattr(manager, 'list_libraries'):
                        try:
                            libs = manager.list_libraries()
                            results["details"]["LibraryManager_list_libraries"] = {"status": "PASS", "result": str(libs)}
                            results["passed"] += 1
                        except Exception as e:
                            results["failed"] += 1
                            results["details"]["LibraryManager_list_libraries"] = {"status": "FAIL", "error": str(e)}
                            
            except Exception as e:
                results["failed"] += 1
                results["details"]["LibraryManager_init"] = {"status": "FAIL", "error": str(e)}
        
        # Test utility functions if they exist
        utility_functions = [
            'validate_library_path',
            'get_library_metadata', 
            'check_library_compatibility'
        ]
        
        for func_name in utility_functions:
            if hasattr(static_libs, func_name):
                try:
                    func = getattr(static_libs, func_name)
                    # Test with safe parameters
                    if func_name == 'validate_library_path':
                        result = func("/nonexistent/path")  # Should handle gracefully
                    else:
                        # For functions that might need valid paths, test with None first
                        try:
                            result = func(None)
                        except TypeError:
                            # Try with empty string if None fails
                            result = func("")
                    
                    results["details"][func_name] = {"status": "PASS", "result": str(result)[:100]}
                    results["passed"] += 1
                    
                except Exception as e:
                    results["failed"] += 1
                    results["details"][func_name] = {"status": "FAIL", "error": str(e)}
            else:
                results["details"][func_name] = {"status": "SKIP", "reason": "Function not found"}
        
    except ImportError as e:
        results["failed"] += 1
        results["errors"].append(f"Could not import static_libs: {e}")
    
    return results


def test_adapter_interfaces() -> Dict[str, Any]:
    """Test that adapter classes have expected interfaces."""
    results = {
        "name": "Adapter Interface Test", 
        "passed": 0,
        "failed": 0,
        "errors": [],
        "details": {}
    }
    
    adapters_to_test = [
        ("autogenlib_adapter", "AutogenlibAdapter"),
        ("graph_sitter_adapter", "GraphSitterAdapter"), 
        ("serena_adapter", "SerenaAdapter")
    ]
    
    for module_name, class_name in adapters_to_test:
        try:
            module = __import__(module_name)
            adapter_class = getattr(module, class_name, None)
            
            if adapter_class is None:
                results["details"][f"{module_name}.{class_name}"] = {
                    "status": "SKIP", "reason": "Class not found"
                }
                continue
            
            # Check for expected methods
            expected_methods = ["__init__", "analyze", "get_results"]
            found_methods = []
            missing_methods = []
            
            for method in expected_methods:
                if hasattr(adapter_class, method):
                    found_methods.append(method)
                else:
                    missing_methods.append(method)
            
            if not missing_methods:
                results["details"][f"{module_name}.{class_name}"] = {
                    "status": "PASS",
                    "found_methods": found_methods,
                    "missing_methods": []
                }
                results["passed"] += 1
            else:
                results["failed"] += 1
                results["details"][f"{module_name}.{class_name}"] = {
                    "status": "PARTIAL",
                    "found_methods": found_methods,
                    "missing_methods": missing_methods
                }
                
        except ImportError as e:
            results["failed"] += 1
            results["errors"].append(f"Could not import {module_name}: {e}")
            results["details"][module_name] = {"status": "FAIL", "error": str(e)}
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Error testing {module_name}: {e}")
            results["details"][module_name] = {"status": "ERROR", "error": str(e)}
    
    return results


def test_libraries_analyzer() -> Dict[str, Any]:
    """Test the main analyzer.py functionality."""
    results = {
        "name": "Libraries Analyzer Test",
        "passed": 0, 
        "failed": 0,
        "errors": [],
        "details": {}
    }
    
    try:
        import analyzer
        
        # Test basic functionality if available
        if hasattr(analyzer, 'analyze'):
            try:
                # Test with a simple Python file
                test_code = '''
def test_function():
    """Test function."""
    return "hello"

class TestClass:
    """Test class."""
    def method(self):
        return 42
'''
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                    f.write(test_code)
                    temp_file = f.name
                
                try:
                    result = analyzer.analyze(temp_file)
                    results["details"]["analyze_function"] = {
                        "status": "PASS", 
                        "result_type": type(result).__name__,
                        "result_preview": str(result)[:200]
                    }
                    results["passed"] += 1
                finally:
                    Path(temp_file).unlink(missing_ok=True)
                    
            except Exception as e:
                results["failed"] += 1
                results["details"]["analyze_function"] = {"status": "FAIL", "error": str(e)}
        
        # Test other key functions
        key_functions = ['get_metrics', 'validate_syntax', 'extract_functions']
        for func_name in key_functions:
            if hasattr(analyzer, func_name):
                try:
                    func = getattr(analyzer, func_name)
                    # Test with simple parameters
                    if func_name == 'validate_syntax':
                        result = func("def test(): pass")
                    else:
                        result = func("")  # Empty input should be handled gracefully
                    
                    results["details"][func_name] = {
                        "status": "PASS",
                        "result_type": type(result).__name__
                    }
                    results["passed"] += 1
                    
                except Exception as e:
                    results["failed"] += 1
                    results["details"][func_name] = {"status": "FAIL", "error": str(e)}
            else:
                results["details"][func_name] = {"status": "SKIP", "reason": "Function not found"}
                
    except ImportError as e:
        results["failed"] += 1
        results["errors"].append(f"Could not import analyzer: {e}")
    
    return results


def test_error_handling() -> Dict[str, Any]:
    """Test error handling with negative test cases."""
    results = {
        "name": "Error Handling Test",
        "passed": 0,
        "failed": 0,
        "errors": [],
        "details": {}
    }
    
    # Test that modules handle invalid inputs gracefully
    test_cases = [
        ("static_libs", "LibraryManager", ["/nonexistent/path", "invalid_source"]),
        ("analyzer", "analyze", ["/nonexistent/file.py"]),
        ("analyzer", "validate_syntax", ["def invalid syntax :("]),
    ]
    
    for module_name, func_or_class_name, args in test_cases:
        try:
            module = __import__(module_name)
            target = getattr(module, func_or_class_name)
            
            try:
                result = target(*args)
                # If it doesn't crash, that's good
                results["details"][f"{module_name}.{func_or_class_name}"] = {
                    "status": "PASS",
                    "handled_invalid_input": True,
                    "result_type": type(result).__name__
                }
                results["passed"] += 1
                
            except Exception as e:
                # Some exceptions are expected for invalid inputs
                error_type = type(e).__name__
                if error_type in ["FileNotFoundError", "SyntaxError", "ValueError", "TypeError"]:
                    results["details"][f"{module_name}.{func_or_class_name}"] = {
                        "status": "PASS",
                        "expected_error": error_type,
                        "error_message": str(e)[:100]
                    }
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    results["details"][f"{module_name}.{func_or_class_name}"] = {
                        "status": "FAIL", 
                        "unexpected_error": error_type,
                        "error_message": str(e)
                    }
                    
        except ImportError:
            results["details"][module_name] = {"status": "SKIP", "reason": "Module not available"}
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Error setting up test for {module_name}: {e}")
    
    return results


def run_all_smoke_tests() -> List[Dict[str, Any]]:
    """Run all smoke tests and return results."""
    print("🧪 Running Libraries Smoke Tests...")
    print("=" * 50)
    
    tests = [
        test_ast_parsing,
        test_module_importability,
        test_static_libs_functions,
        test_adapter_interfaces,
        test_libraries_analyzer,
        test_error_handling
    ]
    
    results = []
    
    for test_func in tests:
        print(f"\n🔍 Running {test_func.__name__}...")
        try:
            result = test_func()
            results.append(result)
            
            status = "✅ PASSED" if result["failed"] == 0 else "❌ FAILED"
            print(f"   {status} - {result['passed']} passed, {result['failed']} failed")
            
            if result["errors"]:
                for error in result["errors"][:3]:  # Show first 3 errors
                    print(f"   ⚠️ {error}")
                    
        except Exception as e:
            print(f"❌ Test {test_func.__name__} crashed: {e}")
            traceback.print_exc()
            results.append({
                "name": test_func.__name__,
                "passed": 0,
                "failed": 1,
                "errors": [str(e)],
                "details": {"crash": True}
            })
    
    return results


def print_summary(results: List[Dict[str, Any]]) -> None:
    """Print test summary."""
    print("\n" + "=" * 50)
    print("📊 SMOKE TEST SUMMARY")
    print("=" * 50)
    
    total_passed = sum(r["passed"] for r in results)
    total_failed = sum(r["failed"] for r in results)
    total_tests = total_passed + total_failed
    
    for result in results:
        status = "✅" if result["failed"] == 0 else "❌"
        print(f"{status} {result['name']}: {result['passed']}/{result['passed'] + result['failed']}")
    
    print("-" * 50)
    print(f"Total: {total_passed}/{total_tests} tests passed")
    
    if total_failed == 0:
        print("🎉 All smoke tests passed! Libraries look healthy.")
    else:
        print(f"⚠️ {total_failed} tests failed. Review the details above.")
    
    # Recommendations
    print("\n💡 Recommendations:")
    if total_failed == 0:
        print("  - All modules are syntactically valid")
        print("  - Core interfaces are functional") 
        print("  - Error handling is working")
    else:
        print("  - Fix syntax errors in failing modules")
        print("  - Check import dependencies")
        print("  - Improve error handling for edge cases")


if __name__ == "__main__":
    results = run_all_smoke_tests()
    print_summary(results)
    
    # Exit with appropriate code
    total_failed = sum(r["failed"] for r in results)
    sys.exit(0 if total_failed == 0 else 1)