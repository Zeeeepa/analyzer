"""
Simple syntax check for date_picker_handler module (no runtime dependencies)
"""

import sys
import ast


def check_syntax(filepath):
    """Check if a Python file has valid syntax"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        ast.parse(code)
        return True, "Syntax valid"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def check_imports(filepath):
    """Check what imports are used"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        tree = ast.parse(code)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                imports.append(module)

        return imports
    except:
        return []


def check_classes(filepath):
    """Check what classes are defined"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        tree = ast.parse(code)

        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)

        return classes
    except:
        return []


def check_functions(filepath):
    """Check what top-level functions are defined"""
    try:
        with open(filepath, 'r') as f:
            code = f.read()
        tree = ast.parse(code)

        functions = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.AsyncFunctionDef):
                functions.append(f"{node.name} (async)")

        return functions
    except:
        return []


def main():
    filepath = "date_picker_handler.py"

    print("="*70)
    print("Date Picker Handler - Static Analysis")
    print("="*70)

    # Check syntax
    print("\n1. Syntax Check")
    print("-"*70)
    valid, message = check_syntax(filepath)
    if valid:
        print(f"✓ {message}")
    else:
        print(f"✗ {message}")
        return False

    # Check imports
    print("\n2. Import Analysis")
    print("-"*70)
    imports = check_imports(filepath)
    print(f"Found {len(imports)} imports:")
    for imp in sorted(set(imports)):
        print(f"  - {imp}")

    # Check classes
    print("\n3. Class Definitions")
    print("-"*70)
    classes = check_classes(filepath)
    print(f"Found {len(classes)} classes:")
    for cls in classes:
        print(f"  - {cls}")

    expected_classes = ["DatePickerSignature", "DatePickerResult", "DatePickerHandler"]
    missing_classes = [c for c in expected_classes if c not in classes]
    if missing_classes:
        print(f"✗ Missing expected classes: {missing_classes}")
        return False
    else:
        print("✓ All expected classes present")

    # Check functions
    print("\n4. Function Definitions")
    print("-"*70)
    functions = check_functions(filepath)
    print(f"Found {len(functions)} top-level functions:")
    for func in functions:
        print(f"  - {func}")

    expected_functions = ["fill_date_simple (async)", "fill_date_range_simple (async)"]
    missing_functions = [f for f in expected_functions if f not in functions]
    if missing_functions:
        print(f"✗ Missing expected functions: {missing_functions}")
        return False
    else:
        print("✓ All expected functions present")

    # Summary
    print("\n" + "="*70)
    print("Summary")
    print("="*70)
    print("✓ Module structure is valid")
    print(f"✓ {len(classes)} classes defined")
    print(f"✓ {len(functions)} helper functions defined")
    print("\n🎉 Static analysis passed!")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
