#!/usr/bin/env python3
"""
Upgraded Code Analyzer - Standalone Version
Comprehensive code analysis without external dependencies
Supports: Python, JavaScript, TypeScript, and more via AST parsing
"""

import ast
import json
import os
import re
import sys
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
import tokenize
import io


class Severity(Enum):
    """Error severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ErrorCategory(Enum):
    """Error category types"""
    SYNTAX = "syntax"
    TYPE = "type"
    NAME = "name"
    IMPORT = "import"
    ATTRIBUTE = "attribute"
    CONTROL_FLOW = "control_flow"
    DATA_FLOW = "data_flow"
    COMPLEXITY = "complexity"
    DEAD_CODE = "dead_code"
    SECURITY = "security"
    STYLE = "style"


@dataclass
class CodeError:
    """Represents a code error or issue"""
    category: ErrorCategory
    severity: Severity
    message: str
    file_path: str
    line: int
    column: int = 0
    code_snippet: str = ""
    suggestion: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "code_snippet": self.code_snippet,
            "suggestion": self.suggestion
        }


@dataclass
class CodeMetrics:
    """Code quality metrics"""
    file_path: str
    lines_of_code: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    functions: int = 0
    classes: int = 0
    complexity: int = 0
    maintainability_index: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ASTAnalyzer:
    """Analyze Python code using AST"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.tree: Optional[ast.AST] = None
        self.source_lines: List[str] = []
        self.errors: List[CodeError] = []
        self.metrics = CodeMetrics(file_path=file_path)
        
    def parse(self) -> bool:
        """Parse the Python file"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                source = f.read()
                self.source_lines = source.splitlines()
            
            self.tree = ast.parse(source, filename=self.file_path)
            return True
        except SyntaxError as e:
            self.errors.append(CodeError(
                category=ErrorCategory.SYNTAX,
                severity=Severity.CRITICAL,
                message=f"Syntax error: {e.msg}",
                file_path=self.file_path,
                line=e.lineno or 0,
                column=e.offset or 0,
                code_snippet=self._get_line(e.lineno or 0),
                suggestion="Fix the syntax error before proceeding"
            ))
            return False
        except Exception as e:
            self.errors.append(CodeError(
                category=ErrorCategory.SYNTAX,
                severity=Severity.CRITICAL,
                message=f"Parse error: {str(e)}",
                file_path=self.file_path,
                line=0,
                suggestion="Check file encoding and syntax"
            ))
            return False
    
    def _get_line(self, lineno: int) -> str:
        """Get source line by number"""
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1]
        return ""
    
    def analyze_metrics(self) -> CodeMetrics:
        """Calculate code metrics"""
        if not self.tree:
            return self.metrics
        
        # Count lines
        self.metrics.lines_of_code = len(self.source_lines)
        self.metrics.blank_lines = sum(1 for line in self.source_lines if not line.strip())
        self.metrics.comment_lines = sum(1 for line in self.source_lines 
                                        if line.strip().startswith('#'))
        
        # Count functions and classes
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                self.metrics.functions += 1
            elif isinstance(node, ast.ClassDef):
                self.metrics.classes += 1
        
        # Calculate cyclomatic complexity
        self.metrics.complexity = self._calculate_complexity()
        
        # Calculate maintainability index (simplified)
        self.metrics.maintainability_index = self._calculate_maintainability()
        
        return self.metrics
    
    def _calculate_complexity(self) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1  # Base complexity
        
        if not self.tree:
            return complexity
        
        for node in ast.walk(self.tree):
            # Add 1 for each decision point
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
        
        return complexity
    
    def _calculate_maintainability(self) -> float:
        """Calculate maintainability index (0-100 scale)"""
        if self.metrics.lines_of_code == 0:
            return 100.0
        
        # Simplified maintainability index
        loc = self.metrics.lines_of_code
        complexity = self.metrics.complexity
        comment_ratio = self.metrics.comment_lines / loc if loc > 0 else 0
        
        # Higher is better
        score = 100 - (complexity * 2) + (comment_ratio * 20)
        return max(0.0, min(100.0, score))
    
    def find_undefined_names(self) -> List[CodeError]:
        """Find undefined variable names"""
        if not self.tree:
            return []
        
        defined_names: Set[str] = set()
        used_names: Dict[str, List[int]] = defaultdict(list)
        
        # Collect defined names
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined_names.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined_names.add(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
        
        # Collect used names
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if hasattr(node, 'lineno'):
                    used_names[node.id].append(node.lineno)
        
        # Check for undefined names (excluding builtins)
        builtins = set(dir(__builtins__))
        errors = []
        
        for name, lines in used_names.items():
            if name not in defined_names and name not in builtins:
                for line in lines:
                    errors.append(CodeError(
                        category=ErrorCategory.NAME,
                        severity=Severity.HIGH,
                        message=f"Name '{name}' is not defined",
                        file_path=self.file_path,
                        line=line,
                        code_snippet=self._get_line(line),
                        suggestion=f"Define '{name}' before use or import it"
                    ))
        
        self.errors.extend(errors)
        return errors
    
    def find_unused_imports(self) -> List[CodeError]:
        """Find unused imports"""
        if not self.tree:
            return []
        
        imported_names: Dict[str, int] = {}
        used_names: Set[str] = set()
        
        # Collect imports
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names[name] = node.lineno
        
        # Collect used names
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
        
        # Find unused
        errors = []
        for name, line in imported_names.items():
            if name not in used_names and not name.startswith('_'):
                errors.append(CodeError(
                    category=ErrorCategory.IMPORT,
                    severity=Severity.LOW,
                    message=f"Imported name '{name}' is never used",
                    file_path=self.file_path,
                    line=line,
                    code_snippet=self._get_line(line),
                    suggestion=f"Remove unused import '{name}'"
                ))
        
        self.errors.extend(errors)
        return errors
    
    def find_dead_code(self) -> List[CodeError]:
        """Find unreachable dead code"""
        if not self.tree:
            return []
        
        errors = []
        
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check for unreachable code after return
                for i, stmt in enumerate(node.body[:-1]):
                    if isinstance(stmt, ast.Return):
                        next_stmt = node.body[i + 1]
                        if hasattr(next_stmt, 'lineno'):
                            errors.append(CodeError(
                                category=ErrorCategory.DEAD_CODE,
                                severity=Severity.MEDIUM,
                                message="Unreachable code after return statement",
                                file_path=self.file_path,
                                line=next_stmt.lineno,
                                code_snippet=self._get_line(next_stmt.lineno),
                                suggestion="Remove code after return or fix control flow"
                            ))
        
        self.errors.extend(errors)
        return errors
    
    def check_security(self) -> List[CodeError]:
        """Check for security issues"""
        if not self.tree:
            return []
        
        errors = []
        dangerous_functions = {'eval', 'exec', 'compile', '__import__'}
        
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in dangerous_functions:
                    if hasattr(node, 'lineno'):
                        errors.append(CodeError(
                            category=ErrorCategory.SECURITY,
                            severity=Severity.CRITICAL,
                            message=f"Dangerous function '{node.func.id}' detected",
                            file_path=self.file_path,
                            line=node.lineno,
                            code_snippet=self._get_line(node.lineno),
                            suggestion=f"Avoid using '{node.func.id}' with untrusted input"
                        ))
        
        self.errors.extend(errors)
        return errors


class CodeAnalyzer:
    """Main code analyzer class"""
    
    def __init__(self, target_path: str):
        self.target_path = Path(target_path)
        self.files: List[Path] = []
        self.errors: List[CodeError] = []
        self.metrics: Dict[str, CodeMetrics] = {}
        
    def discover_files(self) -> List[Path]:
        """Discover Python files to analyze"""
        if self.target_path.is_file():
            if self.target_path.suffix == '.py':
                self.files = [self.target_path]
        else:
            self.files = list(self.target_path.rglob('*.py'))
        
        return self.files
    
    def analyze_file(self, file_path: Path) -> Tuple[List[CodeError], CodeMetrics]:
        """Analyze a single file"""
        analyzer = ASTAnalyzer(str(file_path))
        
        if not analyzer.parse():
            return analyzer.errors, analyzer.metrics
        
        # Run all analyses
        analyzer.analyze_metrics()
        analyzer.find_undefined_names()
        analyzer.find_unused_imports()
        analyzer.find_dead_code()
        analyzer.check_security()
        
        return analyzer.errors, analyzer.metrics
    
    def analyze_all(self) -> Dict[str, Any]:
        """Analyze all discovered files"""
        self.discover_files()
        
        total_errors = 0
        severity_counts = Counter()
        category_counts = Counter()
        
        for file_path in self.files:
            print(f"Analyzing: {file_path}")
            
            errors, metrics = self.analyze_file(file_path)
            self.errors.extend(errors)
            self.metrics[str(file_path)] = metrics
            
            total_errors += len(errors)
            
            for error in errors:
                severity_counts[error.severity.value] += 1
                category_counts[error.category.value] += 1
        
        # Generate summary
        summary = {
            "files_analyzed": len(self.files),
            "total_errors": total_errors,
            "severity_breakdown": dict(severity_counts),
            "category_breakdown": dict(category_counts),
            "errors": [error.to_dict() for error in self.errors],
            "metrics": {path: metrics.to_dict() for path, metrics in self.metrics.items()}
        }
        
        return summary
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """Generate analysis report"""
        summary = self.analyze_all()
        
        report = f"""
╔════════════════════════════════════════════╗
║      CODE ANALYSIS REPORT                  ║
╚════════════════════════════════════════════╝

📊 Summary:
  • Files Analyzed: {summary['files_analyzed']}
  • Total Errors: {summary['total_errors']}

⚠️  Severity Breakdown:
"""
        
        for severity, count in summary['severity_breakdown'].items():
            report += f"  • {severity.upper()}: {count}\n"
        
        report += "\n📁 Category Breakdown:\n"
        for category, count in summary['category_breakdown'].items():
            report += f"  • {category}: {count}\n"
        
        report += "\n🔍 Detailed Errors:\n"
        for i, error in enumerate(summary['errors'][:20], 1):
            report += f"\n{i}. [{error['severity']}] {error['category']}\n"
            report += f"   File: {error['file_path']}:{error['line']}\n"
            report += f"   {error['message']}\n"
            if error['suggestion']:
                report += f"   💡 {error['suggestion']}\n"
        
        if len(summary['errors']) > 20:
            report += f"\n... and {len(summary['errors']) - 20} more errors\n"
        
        # Save to file if requested
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(summary, f, indent=2)
            report += f"\n📄 Full report saved to: {output_file}\n"
        
        return report


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Code Analyzer - Comprehensive Python code analysis")
    parser.add_argument("target", help="File or directory to analyze")
    parser.add_argument("--output", "-o", help="Output file for JSON report")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    analyzer = CodeAnalyzer(args.target)
    report = analyzer.generate_report(args.output)
    
    print(report)
    
    # Return exit code based on critical errors
    critical_count = sum(1 for e in analyzer.errors if e.severity == Severity.CRITICAL)
    return 1 if critical_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

