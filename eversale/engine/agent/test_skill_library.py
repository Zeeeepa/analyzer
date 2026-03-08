#!/usr/bin/env python3
"""
Test Suite for Skill Library

Comprehensive tests for the Voyager-style skill library including:
- Skill creation and validation
- Vector-based retrieval
- Skill learning and generalization
- Skill composition
- Metrics tracking
- Export/import
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest

from skill_library import (
    Skill,
    SkillCategory,
    SkillStatus,
    SkillMetrics,
    SkillLibrary,
    SkillRetriever,
    SkillValidator,
    SkillGenerator,
    SkillComposer,
    get_skill_library,
)


class TestSkillMetrics:
    """Test skill metrics tracking"""

    def test_initial_metrics(self):
        """Test initial metrics state"""
        metrics = SkillMetrics()
        assert metrics.total_uses == 0
        assert metrics.success_rate == 0.0
        assert metrics.avg_execution_time == 0.0

    def test_record_success(self):
        """Test recording successful execution"""
        metrics = SkillMetrics()
        metrics.record_use(success=True, execution_time=1.5)

        assert metrics.total_uses == 1
        assert metrics.successes == 1
        assert metrics.failures == 0
        assert metrics.success_rate == 1.0
        assert metrics.avg_execution_time == 1.5
        assert metrics.last_success is not None
        assert metrics.last_used is not None

    def test_record_failure(self):
        """Test recording failed execution"""
        metrics = SkillMetrics()
        metrics.record_use(success=False, execution_time=2.0, error="Test error")

        assert metrics.total_uses == 1
        assert metrics.successes == 0
        assert metrics.failures == 1
        assert metrics.success_rate == 0.0
        assert metrics.last_failure is not None
        assert len(metrics.failure_reasons) == 1

    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        metrics = SkillMetrics()

        # 3 successes, 1 failure = 75% success rate
        metrics.record_use(success=True, execution_time=1.0)
        metrics.record_use(success=True, execution_time=1.0)
        metrics.record_use(success=True, execution_time=1.0)
        metrics.record_use(success=False, execution_time=1.0)

        assert metrics.total_uses == 4
        assert metrics.success_rate == 0.75

    def test_moving_average_execution_time(self):
        """Test moving average of execution time"""
        metrics = SkillMetrics()

        metrics.record_use(success=True, execution_time=1.0)
        metrics.record_use(success=True, execution_time=2.0)
        metrics.record_use(success=True, execution_time=3.0)

        # Should be weighted average, not simple average
        assert metrics.avg_execution_time > 0
        assert metrics.avg_execution_time < 3.0


class TestSkill:
    """Test Skill class"""

    def test_skill_creation(self):
        """Test creating a skill"""
        skill = Skill(
            skill_id="test_skill_1",
            name="Test Skill",
            description="A test skill",
            category=SkillCategory.NAVIGATION,
            code="result = True",
        )

        assert skill.skill_id == "test_skill_1"
        assert skill.name == "Test Skill"
        assert skill.category == SkillCategory.NAVIGATION
        assert skill.status == SkillStatus.DRAFT
        assert skill.version == 1

    def test_skill_to_dict(self):
        """Test serialization to dictionary"""
        skill = Skill(
            skill_id="test_skill_1",
            name="Test Skill",
            description="A test skill",
            category=SkillCategory.NAVIGATION,
            code="result = True",
        )

        data = skill.to_dict()
        assert data["skill_id"] == "test_skill_1"
        assert data["category"] == "navigation"
        assert data["status"] == "draft"

    def test_skill_from_dict(self):
        """Test deserialization from dictionary"""
        data = {
            "skill_id": "test_skill_1",
            "name": "Test Skill",
            "description": "A test skill",
            "category": "navigation",
            "code": "result = True",
            "status": "active",
            "version": 1,
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "author": "test",
            "parameters": {},
            "returns": None,
            "required_tools": [],
            "tags": [],
            "metrics": {
                "total_uses": 0,
                "successes": 0,
                "failures": 0,
                "avg_execution_time": 0.0,
                "last_used": None,
                "last_success": None,
                "last_failure": None,
                "failure_reasons": [],
            },
            "source_task": None,
            "generalization_level": 0,
        }

        skill = Skill.from_dict(data)
        assert skill.skill_id == "test_skill_1"
        assert skill.category == SkillCategory.NAVIGATION
        assert skill.status == SkillStatus.ACTIVE

    def test_skill_hash(self):
        """Test skill hash for deduplication"""
        skill1 = Skill(
            skill_id="skill_1",
            name="Skill 1",
            description="First skill",
            category=SkillCategory.NAVIGATION,
            code="result = 'test'",
        )

        skill2 = Skill(
            skill_id="skill_2",
            name="Skill 2",
            description="Second skill",
            category=SkillCategory.NAVIGATION,
            code="result = 'test'",  # Same code
        )

        # Same code should produce same hash
        assert skill1.get_hash() == skill2.get_hash()

    def test_skill_execution(self):
        """Test executing a skill"""
        skill = Skill(
            skill_id="test_exec",
            name="Test Execution",
            description="Test skill execution",
            category=SkillCategory.NAVIGATION,
            code="""
x = context.get('x', 0)
y = context.get('y', 0)
result = x + y
""",
        )

        context = {"x": 5, "y": 3}
        result = skill.execute(context)
        assert result == 8


class TestSkillValidator:
    """Test skill validation"""

    def test_valid_skill(self):
        """Test validating a valid skill"""
        skill = Skill(
            skill_id="valid_skill",
            name="Valid Skill",
            description="A valid test skill",
            category=SkillCategory.NAVIGATION,
            code="""
async def test_func(context):
    result = True
    return result
""",
            required_tools=["playwright_navigate"],
        )

        validator = SkillValidator()
        is_valid, errors = validator.validate_skill(skill)

        assert is_valid
        assert len(errors) == 0

    def test_missing_name(self):
        """Test validation fails for missing name"""
        skill = Skill(
            skill_id="no_name",
            name="",  # Missing name
            description="Test",
            category=SkillCategory.NAVIGATION,
            code="result = True",
        )

        validator = SkillValidator()
        is_valid, errors = validator.validate_skill(skill)

        assert not is_valid
        assert any("name" in e.lower() for e in errors)

    def test_syntax_error(self):
        """Test validation fails for syntax errors"""
        skill = Skill(
            skill_id="syntax_error",
            name="Syntax Error",
            description="Test",
            category=SkillCategory.NAVIGATION,
            code="result = ",  # Syntax error
        )

        validator = SkillValidator()
        is_valid, errors = validator.validate_skill(skill)

        assert not is_valid
        assert any("syntax" in e.lower() for e in errors)

    def test_dangerous_code(self):
        """Test validation fails for dangerous code"""
        skill = Skill(
            skill_id="dangerous",
            name="Dangerous Skill",
            description="Test",
            category=SkillCategory.NAVIGATION,
            code="import os; result = True",  # Dangerous import
        )

        validator = SkillValidator()
        is_valid, errors = validator.validate_skill(skill)

        assert not is_valid
        assert any("dangerous" in e.lower() for e in errors)


class TestSkillGenerator:
    """Test skill generation from executions"""

    def test_extract_from_execution(self):
        """Test extracting skill from action sequence"""
        task_desc = "Login to example.com"
        actions = [
            {"tool": "playwright_navigate", "arguments": {"url": "https://example.com/login"}},
            {"tool": "playwright_fill", "arguments": {"selector": "#email", "value": "test@example.com"}},
            {"tool": "playwright_fill", "arguments": {"selector": "#password", "value": "password123"}},
            {"tool": "playwright_click", "arguments": {"selector": "button.submit"}},
        ]

        generator = SkillGenerator()
        skill = generator.extract_from_execution(
            task_description=task_desc,
            actions=actions,
            result={"success": True},
            category=SkillCategory.NAVIGATION,
        )

        assert skill is not None
        assert skill.name
        assert skill.code
        assert len(skill.required_tools) > 0
        assert "playwright_navigate" in skill.required_tools

    def test_generate_skill_name(self):
        """Test skill name generation"""
        generator = SkillGenerator()

        name1 = generator._generate_skill_name("Login to example.com")
        assert len(name1) > 0
        assert "login" in name1.lower()

        name2 = generator._generate_skill_name("Please help me extract contacts from page")
        assert "please" not in name2.lower()  # Should remove prefix

    def test_extract_parameters(self):
        """Test parameter extraction"""
        actions = [
            {"tool": "playwright_navigate", "arguments": {"url": "https://example.com"}},
            {"tool": "playwright_fill", "arguments": {"selector": "#email", "value": "test@example.com"}},
        ]

        generator = SkillGenerator()
        params = generator._extract_parameters(actions)

        assert "url" in params or "selector" in params  # Should extract configurable params

    def test_generalize_skill(self):
        """Test skill generalization"""
        original = Skill(
            skill_id="specific_skill",
            name="Specific Login",
            description="Login to example.com",
            category=SkillCategory.NAVIGATION,
            code="""
await playwright_navigate(url='https://example.com')
await playwright_fill(selector='#email', value='test@example.com')
result = True
""",
        )

        generator = SkillGenerator()
        generalized = generator.generalize_skill(original)

        assert generalized.skill_id != original.skill_id
        assert generalized.generalization_level > original.generalization_level
        assert "context.get" in generalized.code  # Should have parameterized values


class TestSkillComposer:
    """Test skill composition"""

    def test_compose_skills(self):
        """Test composing multiple skills"""
        skill1 = Skill(
            skill_id="skill_1",
            name="Navigate",
            description="Navigate to page",
            category=SkillCategory.NAVIGATION,
            code="result = 'navigated'",
            required_tools=["playwright_navigate"]
        )

        skill2 = Skill(
            skill_id="skill_2",
            name="Extract",
            description="Extract data",
            category=SkillCategory.EXTRACTION,
            code="result = 'extracted'",
            required_tools=["playwright_extract"]
        )

        composer = SkillComposer()
        composite = composer.compose_skills(
            skills=[skill1, skill2],
            workflow_name="Navigate and Extract",
            workflow_description="Navigate to page and extract data",
        )

        assert composite is not None
        assert composite.category == SkillCategory.COMPOSITE
        # The composite skill now contains both skills' code and tools combined
        assert len(composite.required_tools) == 2
        assert "playwright_navigate" in composite.required_tools
        assert "playwright_extract" in composite.required_tools
        # Verify both skill codes are in the composite
        assert "navigated" in composite.code
        assert "extracted" in composite.code


class TestSkillLibrary:
    """Test skill library management"""

    def test_library_initialization(self):
        """Test library initialization"""
        library = SkillLibrary()

        assert library is not None
        assert len(library.skills) > 0  # Should have pre-built skills

    def test_add_skill(self):
        """Test adding a skill to library"""
        library = SkillLibrary()

        skill = Skill(
            skill_id="new_skill_test",
            name="New Test Skill",
            description="A new test skill",
            category=SkillCategory.NAVIGATION,
            code="result = True",
            status=SkillStatus.ACTIVE,
        )

        success = library.add_skill(skill, validate=True)
        assert success

        retrieved = library.get_skill("new_skill_test")
        assert retrieved is not None
        assert retrieved.name == "New Test Skill"

    def test_duplicate_detection(self):
        """Test duplicate skill detection"""
        library = SkillLibrary()

        skill1 = Skill(
            skill_id="dup_test_1",
            name="Duplicate Test 1",
            description="First duplicate",
            category=SkillCategory.NAVIGATION,
            code="result = 'duplicate'",
            status=SkillStatus.ACTIVE,
        )

        skill2 = Skill(
            skill_id="dup_test_2",
            name="Duplicate Test 2",
            description="Second duplicate",
            category=SkillCategory.NAVIGATION,
            code="result = 'duplicate'",  # Same code
            status=SkillStatus.ACTIVE,
        )

        success1 = library.add_skill(skill1, validate=True)
        assert success1

        success2 = library.add_skill(skill2, validate=True)
        assert not success2  # Should detect duplicate

    def test_search_skills(self):
        """Test searching for skills"""
        library = SkillLibrary()

        # Search for navigation skills
        results = library.search_skills(
            query="login to website",
            category=SkillCategory.NAVIGATION,
            limit=5,
        )

        assert len(results) > 0
        assert all(s.category == SkillCategory.NAVIGATION for s in results)

    def test_learn_skill_from_execution(self):
        """Test learning a skill from execution"""
        library = SkillLibrary()

        actions = [
            {"tool": "playwright_navigate", "arguments": {"url": "https://test.com"}},
            {"tool": "playwright_click", "arguments": {"selector": "button"}},
        ]

        learned = library.learn_skill_from_execution(
            task_description="Click button on test.com",
            actions=actions,
            result={"success": True},
            category=SkillCategory.INTERACTION,
            auto_add=True,
        )

        assert learned is not None
        assert learned.status == SkillStatus.ACTIVE

        # Should be in library now
        retrieved = library.get_skill(learned.skill_id)
        assert retrieved is not None

    def test_compose_workflow(self):
        """Test composing workflow from existing skills"""
        library = SkillLibrary()

        # Get some existing skills
        skills = list(library.skills.values())[:2]
        skill_ids = [s.skill_id for s in skills]

        workflow = library.compose_workflow(
            skill_ids=skill_ids,
            workflow_name="Test Workflow",
            workflow_description="Test workflow composition",
        )

        assert workflow is not None
        assert workflow.category == SkillCategory.COMPOSITE

    def test_record_skill_usage(self):
        """Test recording skill usage"""
        library = SkillLibrary()

        # Use an existing skill from the library
        existing_skills = list(library.skills.values())
        if not existing_skills:
            # Add a test skill if none exist
            skill = Skill(
                skill_id="usage_test_unique",
                name="Usage Test",
                description="Test usage recording",
                category=SkillCategory.NAVIGATION,
                code="result = True",
                status=SkillStatus.ACTIVE,
            )
            library.add_skill(skill, validate=True)
            skill_id = "usage_test_unique"
        else:
            skill = existing_skills[0]
            skill_id = skill.skill_id

        # Get initial metrics
        initial_uses = skill.metrics.total_uses
        initial_successes = skill.metrics.successes

        # Record usage
        library.record_skill_usage(
            skill_id=skill_id,
            success=True,
            execution_time=1.5,
        )

        # Check metrics updated
        updated = library.get_skill(skill_id)
        assert updated is not None
        assert updated.metrics.total_uses == initial_uses + 1
        assert updated.metrics.successes == initial_successes + 1

    def test_deprecate_skill(self):
        """Test deprecating a skill"""
        library = SkillLibrary()

        # Use unique ID and code to avoid conflicts
        unique_id = id(self)
        skill_id = f"deprecate_test_{unique_id}"
        skill = Skill(
            skill_id=skill_id,
            name="Deprecate Test",
            description="Test deprecation",
            category=SkillCategory.NAVIGATION,
            code=f"result = {unique_id}",  # Unique code
            status=SkillStatus.ACTIVE,
        )

        success = library.add_skill(skill, validate=True)
        assert success, "Skill should be added successfully"

        # Verify it was added
        added_skill = library.get_skill(skill_id)
        assert added_skill is not None, "Skill should be in library"
        assert added_skill.status == SkillStatus.ACTIVE

        # Deprecate it
        library.deprecate_skill(skill_id)

        # Check it's deprecated
        deprecated = library.get_skill(skill_id)
        assert deprecated is not None, "Deprecated skill should still be in library"
        assert deprecated.status == SkillStatus.DEPRECATED

    def test_export_import(self):
        """Test exporting and importing skills"""
        library1 = SkillLibrary()

        # Export skills
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            export_path = Path(f.name)

        library1.export_skills(export_path)

        # Create new library and import
        library2 = SkillLibrary()
        library2.skills.clear()  # Clear pre-built skills
        library2.import_skills(export_path)

        assert len(library2.skills) > 0

        # Clean up
        export_path.unlink()

    def test_get_statistics(self):
        """Test getting library statistics"""
        library = SkillLibrary()

        stats = library.get_statistics()

        assert "total_skills" in stats
        assert "by_category" in stats
        assert "by_status" in stats
        assert stats["total_skills"] > 0


class TestSkillRetriever:
    """Test vector-based skill retrieval"""

    def test_retriever_initialization(self):
        """Test retriever initialization"""
        retriever = SkillRetriever(collection_name="test_skills")
        assert retriever is not None

    def test_add_and_search(self):
        """Test adding and searching skills"""
        retriever = SkillRetriever(collection_name="test_search")

        skill = Skill(
            skill_id="search_test",
            name="Search Test Skill",
            description="Test skill for searching with login and navigation",
            category=SkillCategory.NAVIGATION,
            code="result = True",
            status=SkillStatus.ACTIVE,
            tags=["login", "navigation"],
        )

        retriever.add_skill(skill)

        # Search for it
        results = retriever.search(query="login to website", limit=5)

        # Should find the skill (if ChromaDB available)
        if results:
            assert any(skill_id == "search_test" for skill_id, score in results)


# Run tests
def run_tests():
    """Run all tests"""
    import sys

    print("Running Skill Library Tests...\n")

    # Test Metrics
    print("Testing SkillMetrics...")
    test_metrics = TestSkillMetrics()
    test_metrics.test_initial_metrics()
    test_metrics.test_record_success()
    test_metrics.test_record_failure()
    test_metrics.test_success_rate_calculation()
    test_metrics.test_moving_average_execution_time()
    print("  ✓ All metrics tests passed\n")

    # Test Skill
    print("Testing Skill...")
    test_skill = TestSkill()
    test_skill.test_skill_creation()
    test_skill.test_skill_to_dict()
    test_skill.test_skill_from_dict()
    test_skill.test_skill_hash()
    test_skill.test_skill_execution()
    print("  ✓ All skill tests passed\n")

    # Test Validator
    print("Testing SkillValidator...")
    test_validator = TestSkillValidator()
    test_validator.test_valid_skill()
    test_validator.test_missing_name()
    test_validator.test_syntax_error()
    test_validator.test_dangerous_code()
    print("  ✓ All validator tests passed\n")

    # Test Generator
    print("Testing SkillGenerator...")
    test_generator = TestSkillGenerator()
    test_generator.test_extract_from_execution()
    test_generator.test_generate_skill_name()
    test_generator.test_extract_parameters()
    test_generator.test_generalize_skill()
    print("  ✓ All generator tests passed\n")

    # Test Composer
    print("Testing SkillComposer...")
    test_composer = TestSkillComposer()
    test_composer.test_compose_skills()
    print("  ✓ All composer tests passed\n")

    # Test Library
    print("Testing SkillLibrary...")
    test_library = TestSkillLibrary()
    test_library.test_library_initialization()
    test_library.test_add_skill()
    test_library.test_duplicate_detection()
    test_library.test_search_skills()
    test_library.test_learn_skill_from_execution()
    test_library.test_compose_workflow()
    test_library.test_record_skill_usage()
    test_library.test_deprecate_skill()
    test_library.test_export_import()
    test_library.test_get_statistics()
    print("  ✓ All library tests passed\n")

    # Test Retriever
    print("Testing SkillRetriever...")
    test_retriever = TestSkillRetriever()
    test_retriever.test_retriever_initialization()
    test_retriever.test_add_and_search()
    print("  ✓ All retriever tests passed\n")

    print("=" * 50)
    print("All tests passed!")
    print("=" * 50)


if __name__ == "__main__":
    run_tests()
