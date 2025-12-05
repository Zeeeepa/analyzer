# 🗺️ Analyzer Repository Feature Mapping

**Purpose:** Comprehensive map of all features, functions, and their integration points

---


## 📄 analyzer.py

**Lines:** 2,112 | **Size:** 80.2 KB

### Classes (10)

- `AnalysisError`
- `ToolConfig`
- `GraphSitterAnalysis`
- `RuffIntegration`
- `LSPDiagnosticsCollector`
- `ErrorDatabase`
- `AutoGenLibFixerLegacy`
- `ComprehensiveAnalyzer`
- `InteractiveAnalyzer`
- `ReportGenerator`

### Functions (1)

- `main()`


## 📄 autogenlib_adapter.py

**Lines:** 1,167 | **Size:** 47.7 KB

### Functions (1)

- `get_ai_client()`


## 📄 graph_sitter_adapter.py

**Lines:** 5,590 | **Size:** 227.4 KB

### Classes (12)

- `AnalyzeRequest`
- `ErrorAnalysisResponse`
- `EntrypointAnalysisResponse`
- `TransformationRequest`
- `VisualizationRequest`
- `DeadCodeAnalysisResponse`
- `CodeQualityMetrics`
- `GraphSitterAnalyzer`
- `AnalysisEngine`
- `EnhancedVisualizationEngine`
- `TransformationEngine`
- `EnhancedTransformationEngine`

### Functions (23)

- `calculate_doi(cls: Class)`
- `get_operators_and_operands(function: Function)`
- `calculate_halstead_volume(operators: List[str], operands: List[str])`
- `cc_rank(complexity: int)`
- `analyze_codebase(request: AnalyzeRequest, background_tasks: Backgro...)`
- `get_error_analysis(analysis_id: str)`
- `fix_errors_with_ai(analysis_id: str, max_fixes: int = 1)`
- `get_entrypoint_analysis(analysis_id: str)`
- `get_dead_code_analysis(analysis_id: str)`
- `get_code_quality_metrics(analysis_id: str)`
- `create_visualization(analysis_id: str, request: VisualizationRequest)`
- `apply_transformation(analysis_id: str, request: TransformationRequest)`
- `generate_documentation(
    analysis_id: str, target_type: str = "codebas...)`
- `get_tree_structure(analysis_id: str)`
- `get_dependency_graph(analysis_id: str)`
- `get_architectural_insights(analysis_id: str)`
- `get_analysis_summary(analysis_id: str)`
- `delete_analysis(analysis_id: str)`
- `list_analyses()`
- `health_check()`
- `get_capabilities()`
- `cleanup_temp_directory(repo_path: str)`
- `convert_all_calls_to_kwargs(codebase: Codebase)`


## 📄 lsp_adapter.py

**Lines:** 564 | **Size:** 25.8 KB

### Classes (3)

- `EnhancedDiagnostic`
- `RuntimeErrorCollector`
- `LSPDiagnosticsManager`


## 📄 static_libs.py

**Lines:** 2,076 | **Size:** 81.6 KB

### Classes (23)

- `LibraryManager`
- `StandardToolIntegration`
- `ErrorCategory`
- `Severity`
- `AnalysisError`
- `AdvancedASTAnalyzer`
- `SymbolTableAnalyzer`
- `DeadCodeDetector`
- `TypeInferenceAnalyzer`
- `ImportResolver`
- `ComprehensiveErrorAnalyzer`
- `ResultAggregator`
- `ReportGenerator`
- `AdvancedErrorDetector`
- `ErrorCategory`
- `Severity`
- `AnalysisError`
- `AdvancedASTAnalyzer`
- `SymbolTableAnalyzer`
- `DeadCodeDetector`
- `TypeInferenceAnalyzer`
- `ImportResolver`
- `ComprehensiveErrorAnalyzer`

### Functions (1)

- `main()`


---

## 📊 Summary Statistics

- **Total Functions:** 26
- **Total Classes:** 48
- **Total Lines:** 11,509
- **Total Files:** 5
