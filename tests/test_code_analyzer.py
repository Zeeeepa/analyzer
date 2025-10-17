#!/usr/bin/env python3
"""
Comprehensive test suite for code_analyzer.py
Tests all functionality with real code examples
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "upgraded_adapters"))

from code_analyzer import (
    CodeAnalyzer, ASTAnalyzer, CodeError, CodeMetrics,
    Severity, ErrorCategory
)


class TestCodeAnalyzer:
    """Test suite for code analyzer"""
    
    def __init__(self):
        self.test_dir = None
        self.passed = 0
        self.failed = 0
        self.tests_run = 0
    
    def setup(self):
        """Create temporary test directory"""
        self.test_dir = Path(tempfile.mkdtemp(prefix="code_analyzer_test_"))
        print(f"✓ Test directory created: {self.test_dir}")
    
    def teardown(self):
        """Clean up test directory"""
        if self.test_dir and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            print(f"✓ Test directory cleaned up")
    
    def assert_equal(self, actual, expected, message=""):
        """Assert equality"""
        self.tests_run += 1
        if actual == expected:
            self.passed += 1
            print(f"  ✅ PASS: {message or f'{actual} == {expected}'}")
            return True
        else:
            self.failed += 1
            print(f"  ❌ FAIL: {message or f'{actual} != {expected}'}")
            print(f"     Expected: {expected}")
            print(f"     Got: {actual}")
            return False
    
    def assert_true(self, condition, message=""):
        """Assert condition is true"""
        return self.assert_equal(condition, True, message)
    
    def assert_greater(self, actual, minimum, message=""):
        """Assert actual > minimum"""
        self.tests_run += 1
        if actual > minimum:
            self.passed += 1
            print(f"  ✅ PASS: {message or f'{actual} > {minimum}'}")
            return True
        else:
            self.failed += 1
            print(f"  ❌ FAIL: {message or f'{actual} <= {minimum}'}")
            return False
    
    def create_test_file(self, filename: str, content: str) -> Path:
        """Create a test Python file"""
        file_path = self.test_dir / filename
        file_path.write_text(content)
        return file_path
    
    def test_syntax_error_detection(self):
        """Test 1: Detect syntax errors"""
        print("\n🧪 Test 1: Syntax Error Detection")
        
        code = """
def broken_function(
    print("Missing closing parenthesis")
"""
        
        file_path = self.create_test_file("syntax_error.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        result = analyzer.parse()
        
        self.assert_false(result, "Should fail to parse")
        self.assert_greater(len(analyzer.errors), 0, "Should have errors")
        self.assert_equal(
            analyzer.errors[0].category, 
            ErrorCategory.SYNTAX,
            "Should be syntax error"
        )
    
    def test_undefined_name_detection(self):
        """Test 2: Detect undefined variables"""
        print("\n🧪 Test 2: Undefined Name Detection")
        
        code = """
def process_data():
    result = undefined_variable * 2
    return result
"""
        
        file_path = self.create_test_file("undefined_var.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        analyzer.parse()
        errors = analyzer.find_undefined_names()
        
        self.assert_greater(len(errors), 0, "Should find undefined variable")
        self.assert_equal(
            errors[0].category,
            ErrorCategory.NAME,
            "Should be name error"
        )
    
    def test_unused_import_detection(self):
        """Test 3: Detect unused imports"""
        print("\n🧪 Test 3: Unused Import Detection")
        
        code = """
import os
import sys
import json  # This is unused

def main():
    print(sys.version)
    return os.path.exists("test")
"""
        
        file_path = self.create_test_file("unused_import.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        analyzer.parse()
        errors = analyzer.find_unused_imports()
        
        # Should find 'json' as unused
        unused_names = [e.message for e in errors if 'json' in e.message]
        self.assert_greater(len(unused_names), 0, "Should find unused import 'json'")
    
    def test_dead_code_detection(self):
        """Test 4: Detect dead code"""
        print("\n🧪 Test 4: Dead Code Detection")
        
        code = """
def function_with_dead_code():
    x = 10
    return x
    print("This is unreachable!")  # Dead code
    y = 20  # Dead code
"""
        
        file_path = self.create_test_file("dead_code.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        analyzer.parse()
        errors = analyzer.find_dead_code()
        
        self.assert_greater(len(errors), 0, "Should find dead code")
        self.assert_equal(
            errors[0].category,
            ErrorCategory.DEAD_CODE,
            "Should be dead code error"
        )
    
    def test_security_check(self):
        """Test 5: Detect security issues"""
        print("\n🧪 Test 5: Security Issue Detection")
        
        code = """
def dangerous_function(user_input):
    # This is dangerous!
    result = eval(user_input)
    return result
"""
        
        file_path = self.create_test_file("security_issue.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        analyzer.parse()
        errors = analyzer.check_security()
        
        self.assert_greater(len(errors), 0, "Should find security issue")
        self.assert_equal(
            errors[0].category,
            ErrorCategory.SECURITY,
            "Should be security error"
        )
        self.assert_equal(
            errors[0].severity,
            Severity.CRITICAL,
            "Should be critical severity"
        )
    
    def test_metrics_calculation(self):
        """Test 6: Calculate code metrics"""
        print("\n🧪 Test 6: Code Metrics Calculation")
        
        code = """# Comment line
def function1():
    '''Docstring'''
    return 42

class MyClass:
    def method1(self):
        pass
    
    def method2(self):
        pass

def function2():
    x = 10
    if x > 5:
        return True
    return False
"""
        
        file_path = self.create_test_file("metrics_test.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        analyzer.parse()
        metrics = analyzer.analyze_metrics()
        
        self.assert_greater(metrics.lines_of_code, 0, "Should count lines")
        self.assert_greater(metrics.functions, 0, "Should count functions")
        self.assert_greater(metrics.classes, 0, "Should count classes")
        self.assert_greater(metrics.complexity, 0, "Should calculate complexity")
        print(f"    Metrics: {metrics.lines_of_code} LOC, "
              f"{metrics.functions} functions, "
              f"{metrics.classes} classes, "
              f"complexity={metrics.complexity}")
    
    def test_valid_code(self):
        """Test 7: Analyze valid code with no errors"""
        print("\n🧪 Test 7: Valid Code Analysis")
        
        code = """
import sys

def greet(name: str) -> str:
    '''Greet a person by name'''
    return f"Hello, {name}!"

def main():
    print(greet("World"))
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""
        
        file_path = self.create_test_file("valid_code.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        result = analyzer.parse()
        
        self.assert_true(result, "Should parse successfully")
        
        analyzer.find_undefined_names()
        analyzer.find_unused_imports()
        analyzer.check_security()
        
        # Should have no critical errors
        critical_errors = [e for e in analyzer.errors if e.severity == Severity.CRITICAL]
        self.assert_equal(len(critical_errors), 0, "Should have no critical errors")
    
    def test_multiple_files(self):
        """Test 8: Analyze multiple files"""
        print("\n🧪 Test 8: Multiple File Analysis")
        
        # Create multiple test files
        files = {
            "file1.py": "def func1():\n    pass\n",
            "file2.py": "def func2():\n    pass\n",
            "file3.py": "class MyClass:\n    pass\n"
        }
        
        for filename, content in files.items():
            self.create_test_file(filename, content)
        
        analyzer = CodeAnalyzer(str(self.test_dir))
        discovered = analyzer.discover_files()
        
        self.assert_equal(
            len(discovered),
            len(files),
            f"Should discover {len(files)} files"
        )
    
    def test_report_generation(self):
        """Test 9: Generate analysis report"""
        print("\n🧪 Test 9: Report Generation")
        
        code = """
import unused_module

def test_function():
    undefined_var = x + 1
    return eval("dangerous")
"""
        
        self.create_test_file("report_test.py", code)
        
        analyzer = CodeAnalyzer(str(self.test_dir))
        summary = analyzer.analyze_all()
        
        self.assert_greater(summary['total_errors'], 0, "Should have errors")
        self.assert_true('severity_breakdown' in summary, "Should have severity breakdown")
        self.assert_true('category_breakdown' in summary, "Should have category breakdown")
        
        print(f"    Found {summary['total_errors']} errors")
        print(f"    Severity: {summary['severity_breakdown']}")
        print(f"    Categories: {summary['category_breakdown']}")
    
    def test_error_suggestions(self):
        """Test 10: Check error suggestions are provided"""
        print("\n🧪 Test 10: Error Suggestions")
        
        code = """
def broken():
    return undefined_variable
"""
        
        file_path = self.create_test_file("suggestions_test.py", code)
        analyzer = ASTAnalyzer(str(file_path))
        analyzer.parse()
        analyzer.find_undefined_names()
        
        if analyzer.errors:
            error = analyzer.errors[0]
            self.assert_true(
                len(error.suggestion) > 0,
                "Should provide a suggestion"
            )
            print(f"    Suggestion: {error.suggestion}")
    
    def assert_false(self, condition, message=""):
        """Assert condition is false"""
        return self.assert_equal(condition, False, message)
    
    def run_all_tests(self):
        """Run all tests"""
        print("=" * 60)
        print("🚀 Starting Code Analyzer Test Suite")
        print("=" * 60)
        
        self.setup()
        
        try:
            # Run all test methods
            self.test_syntax_error_detection()
            self.test_undefined_name_detection()
            self.test_unused_import_detection()
            self.test_dead_code_detection()
            self.test_security_check()
            self.test_metrics_calculation()
            self.test_valid_code()
            self.test_multiple_files()
            self.test_report_generation()
            self.test_error_suggestions()
            
        finally:
            self.teardown()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Tests Run:    {self.tests_run}")
        print(f"✅ Passed:    {self.passed}")
        print(f"❌ Failed:    {self.failed}")
        print(f"Success Rate: {(self.passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "N/A")
        print("=" * 60)
        
        return self.failed == 0


def main():
    """Run tests"""
    tester = TestCodeAnalyzer()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n💥 {tester.failed} test(s) failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())

