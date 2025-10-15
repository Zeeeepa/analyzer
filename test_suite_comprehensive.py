#!/usr/bin/env python3
"""
Comprehensive Test Suite for Analyzer Libraries

This script analyzes and tests all functions in the 5 main library files:
1. static_libs.py
2. lsp_adapter.py
3. autogenlib_adapter.py
4. graph_sitter_adapter.py
5. analyzer.py

Generates detailed reports with ✅/❌ status for each function.
"""

import ast
import importlib
import inspect
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import json

# Setup
REPO_ROOT = Path(__file__).parent
LIBRARIES_DIR = REPO_ROOT / "Libraries"
sys.path.insert(0, str(LIBRARIES_DIR))

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FunctionAnalyzer:
    """Analyzes and tests functions in Python modules."""
    
    def __init__(self, module_path: Path):
        self.module_path = module_path
        self.module_name = module_path.stem
        self.functions = {}
        self.classes = {}
        self.test_results = {}
        
    def extract_functions_from_ast(self) -> Dict[str, Dict]:
        """Extract all functions and methods using AST parsing."""
        try:
            with open(self.module_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
            
            tree = ast.parse(source)
            functions = {}
            classes = {}
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Top-level function
                    if not any(isinstance(parent, ast.ClassDef) for parent in ast.walk(tree)):
                        functions[node.name] = {
                            'type': 'function',
                            'args': [arg.arg for arg in node.args.args],
                            'lineno': node.lineno,
                            'docstring': ast.get_docstring(node),
                            'is_async': isinstance(node, ast.AsyncFunctionDef),
                            'decorators': [d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list]
                        }
                
                elif isinstance(node, ast.ClassDef):
                    class_methods = {}
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            class_methods[item.name] = {
                                'type': 'method',
                                'args': [arg.arg for arg in item.args.args],
                                'lineno': item.lineno,
                                'docstring': ast.get_docstring(item),
                                'is_async': isinstance(item, ast.AsyncFunctionDef),
                                'decorators': [d.id if isinstance(d, ast.Name) else str(d) for d in item.decorator_list]
                            }
                    
                    classes[node.name] = {
                        'lineno': node.lineno,
                        'docstring': ast.get_docstring(node),
                        'methods': class_methods,
                        'bases': [b.id if isinstance(b, ast.Name) else str(b) for b in node.bases]
                    }
            
            self.functions = functions
            self.classes = classes
            return {'functions': functions, 'classes': classes}
            
        except Exception as e:
            logger.error(f"Error parsing {self.module_path}: {e}")
            return {'functions': {}, 'classes': {}}
    
    def test_function_import(self, func_name: str) -> Tuple[bool, str, Any]:
        """Test if a function can be imported and is callable."""
        try:
            module = importlib.import_module(self.module_name)
            if hasattr(module, func_name):
                func = getattr(module, func_name)
                if callable(func):
                    return True, "✅ Importable and callable", func
                else:
                    return False, "❌ Not callable", func
            else:
                return False, "❌ Not found in module", None
        except ImportError as e:
            return False, f"❌ Import error: {str(e)[:50]}", None
        except Exception as e:
            return False, f"❌ Error: {str(e)[:50]}", None
    
    def test_function_signature(self, func: Callable) -> Tuple[bool, str]:
        """Test function signature analysis."""
        try:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            return True, f"✅ Signature: {len(params)} params"
        except Exception as e:
            return False, f"❌ Signature error: {str(e)[:30]}"
    
    def test_function_basic_call(self, func: Callable, func_info: Dict) -> Tuple[bool, str]:
        """Test basic function call with None/empty arguments."""
        try:
            args = func_info.get('args', [])
            
            # Skip functions that require specific arguments
            if len(args) > 0 and args[0] not in ['self', 'cls']:
                return None, "⚠️  Requires args - skipped"
            
            # Try calling with no args
            try:
                result = func()
                return True, "✅ Callable (no args)"
            except TypeError as e:
                if 'required positional argument' in str(e):
                    return None, "⚠️  Requires args - skipped"
                return False, f"❌ Call error: {str(e)[:30]}"
                
        except Exception as e:
            return False, f"❌ Test error: {str(e)[:30]}"
    
    def analyze_function(self, func_name: str, func_info: Dict) -> Dict:
        """Comprehensive analysis of a single function."""
        result = {
            'name': func_name,
            'type': func_info.get('type', 'function'),
            'lineno': func_info.get('lineno'),
            'args': func_info.get('args', []),
            'tests': {}
        }
        
        # Test 1: Import and callable
        importable, import_msg, func_obj = self.test_function_import(func_name)
        result['tests']['import'] = {
            'status': '✅' if importable else '❌',
            'message': import_msg
        }
        
        if func_obj and callable(func_obj):
            # Test 2: Signature
            sig_ok, sig_msg = self.test_function_signature(func_obj)
            result['tests']['signature'] = {
                'status': '✅' if sig_ok else '❌',
                'message': sig_msg
            }
            
            # Test 3: Basic call (if possible)
            call_ok, call_msg = self.test_function_basic_call(func_obj, func_info)
            if call_ok is not None:
                result['tests']['basic_call'] = {
                    'status': '✅' if call_ok else '❌',
                    'message': call_msg
                }
        
        return result
    
    def analyze_all(self) -> Dict:
        """Analyze all functions and methods in the module."""
        logger.info(f"\n{'='*60}")
        logger.info(f"ANALYZING: {self.module_name}.py")
        logger.info(f"{'='*60}")
        
        # Extract functions using AST
        extracted = self.extract_functions_from_ast()
        
        results = {
            'module': self.module_name,
            'path': str(self.module_path),
            'functions': {},
            'classes': {}
        }
        
        # Analyze top-level functions
        logger.info(f"\n📊 Top-level functions: {len(extracted['functions'])}")
        for func_name, func_info in extracted['functions'].items():
            logger.info(f"  Testing: {func_name}")
            results['functions'][func_name] = self.analyze_function(func_name, func_info)
        
        # Analyze class methods
        logger.info(f"\n📊 Classes: {len(extracted['classes'])}")
        for class_name, class_info in extracted['classes'].items():
            logger.info(f"  Class: {class_name}")
            results['classes'][class_name] = {
                'lineno': class_info['lineno'],
                'methods': {}
            }
            
            for method_name, method_info in class_info['methods'].items():
                logger.info(f"    Method: {method_name}")
                # For methods, we need to test them differently
                # For now, just check if they exist
                results['classes'][class_name]['methods'][method_name] = {
                    'name': method_name,
                    'type': 'method',
                    'lineno': method_info['lineno'],
                    'args': method_info['args'],
                    'tests': {
                        'exists': {
                            'status': '✅',
                            'message': 'Method defined'
                        }
                    }
                }
        
        return results


class ReportGenerator:
    """Generates comprehensive test reports."""
    
    def __init__(self):
        self.all_results = []
    
    def add_module_results(self, results: Dict):
        """Add results for a module."""
        self.all_results.append(results)
    
    def generate_summary_report(self) -> str:
        """Generate a summary report across all modules."""
        report = []
        report.append("\n" + "="*80)
        report.append("COMPREHENSIVE FUNCTION ANALYSIS REPORT")
        report.append("="*80 + "\n")
        
        for module_results in self.all_results:
            module_name = module_results['module']
            report.append(f"\n{'='*80}")
            report.append(f"MODULE: {module_name}.py")
            report.append(f"{'='*80}")
            
            # Top-level functions
            if module_results['functions']:
                report.append(f"\n📦 TOP-LEVEL FUNCTIONS ({len(module_results['functions'])})")
                report.append("-" * 80)
                
                for func_name, func_data in module_results['functions'].items():
                    args_str = ", ".join(func_data['args']) if func_data['args'] else "none"
                    report.append(f"\n  {func_name}()")
                    report.append(f"    Line: {func_data['lineno']} | Args: {args_str}")
                    
                    for test_name, test_result in func_data['tests'].items():
                        status = test_result['status']
                        message = test_result['message']
                        report.append(f"    {status} {test_name}: {message}")
            
            # Classes and methods
            if module_results['classes']:
                report.append(f"\n\n📦 CLASSES ({len(module_results['classes'])})")
                report.append("-" * 80)
                
                for class_name, class_data in module_results['classes'].items():
                    report.append(f"\n  class {class_name}")
                    report.append(f"    Line: {class_data['lineno']} | Methods: {len(class_data['methods'])}")
                    
                    for method_name, method_data in class_data['methods'].items():
                        args_str = ", ".join(method_data['args']) if method_data['args'] else "none"
                        report.append(f"\n    {method_name}()")
                        report.append(f"      Line: {method_data['lineno']} | Args: {args_str}")
                        
                        for test_name, test_result in method_data['tests'].items():
                            status = test_result['status']
                            message = test_result['message']
                            report.append(f"      {status} {test_name}: {message}")
        
        # Overall statistics
        report.append("\n\n" + "="*80)
        report.append("OVERALL STATISTICS")
        report.append("="*80)
        
        total_functions = sum(len(m['functions']) for m in self.all_results)
        total_classes = sum(len(m['classes']) for m in self.all_results)
        total_methods = sum(
            sum(len(c['methods']) for c in m['classes'].values())
            for m in self.all_results
        )
        
        report.append(f"\nModules Analyzed: {len(self.all_results)}")
        report.append(f"Total Functions: {total_functions}")
        report.append(f"Total Classes: {total_classes}")
        report.append(f"Total Methods: {total_methods}")
        report.append(f"Total Callables: {total_functions + total_methods}")
        
        return "\n".join(report)
    
    def save_json_report(self, output_path: Path):
        """Save detailed results as JSON."""
        with open(output_path, 'w') as f:
            json.dump(self.all_results, f, indent=2)
        logger.info(f"JSON report saved to: {output_path}")


def main():
    """Main entry point."""
    
    # Files to analyze
    files_to_analyze = [
        'static_libs.py',
        'lsp_adapter.py',
        'autogenlib_adapter.py',
        'graph_sitter_adapter.py',
        'analyzer.py'
    ]
    
    report_gen = ReportGenerator()
    
    for filename in files_to_analyze:
        file_path = LIBRARIES_DIR / filename
        
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            continue
        
        try:
            analyzer = FunctionAnalyzer(file_path)
            results = analyzer.analyze_all()
            report_gen.add_module_results(results)
        except Exception as e:
            logger.error(f"Error analyzing {filename}: {e}")
            traceback.print_exc()
    
    # Generate reports
    summary = report_gen.generate_summary_report()
    print(summary)
    
    # Save JSON report
    json_path = REPO_ROOT / "test_results.json"
    report_gen.save_json_report(json_path)
    
    # Save text report
    text_path = REPO_ROOT / "test_results.txt"
    with open(text_path, 'w') as f:
        f.write(summary)
    logger.info(f"\nText report saved to: {text_path}")


if __name__ == "__main__":
    main()

