"""Pydantic models for Jira agent structured outputs."""

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """A functional or non-functional requirement."""

    id: str = Field(description="Unique requirement ID (e.g., EX-FON-01, EX-NFON-01)")
    title: str = Field(description="Short requirement title")
    description: str = Field(description="Detailed requirement description")
    priority: Literal["Haute", "Moyenne", "Basse"] = Field(
        description="Requirement priority level"
    )


class RequirementsList(BaseModel):
    """List of requirements."""

    items: list[Requirement] = Field(description="List of requirements")


class UserStoryTitle(BaseModel):
    """A user story title for batch generation."""

    id: str = Field(description="Unique user story ID (e.g., US-01)")
    title: str = Field(
        description="Short, descriptive title for the user story (max 80 characters)"
    )
    epic_name: str = Field(description="Parent epic name for grouping related stories")
    requirement_ids: list[str] | None = Field(
        default=None,
        description="List of requirement IDs this story implements (e.g., ['EX-FON-01', 'EX-NFON-02'])",
    )
    dependencies: list[str] | None = Field(
        default=None,
        description="List of prerequisite user story IDs (e.g., ['US-01', 'US-02'])",
    )


class UserStoryTitlesList(BaseModel):
    """List of user story titles."""

    items: list[UserStoryTitle] = Field(description="List of user story titles")


class AcceptanceCriterion(BaseModel):
    """An acceptance criterion with Gherkin steps."""

    scenario: str = Field(description="Name/title of the acceptance scenario")
    steps: list[str] = Field(description="Gherkin steps (Given/When/Then)")


class UserStory(BaseModel):
    """A complete user story with acceptance criteria."""

    id: str = Field(description="Unique user story ID (e.g., US-01)")
    summary: str = Field(description="User story title/summary")
    description: str = Field(
        description="User story in format: En tant que [persona], je veux [action], afin de [bénéfice]"
    )
    issue_type: Literal["Story", "Task", "Bug"] | None = Field(
        default="Story", description="Jira issue type"
    )
    priority: Literal["Haute", "Moyenne", "Basse"] = Field(
        description="Story priority level"
    )
    epic_name: str | None = Field(
        default=None, description="Parent epic name for grouping related stories"
    )
    story_points: int | None = Field(
        default=None,
        ge=1,
        le=21,
        description="Story point estimate (Fibonacci: 1, 2, 3, 5, 8, 13, 21)",
    )
    labels: list[str] | None = Field(
        default=None, description="Labels for categorization"
    )
    requirement_ids: list[str] | None = Field(
        default=None,
        description="List of requirement IDs this story implements (e.g., ['EX-FON-01', 'EX-NFON-02'])",
    )
    dependencies: list[str] | None = Field(
        default=None,
        description="List of prerequisite user story IDs (e.g., ['US-01', 'US-02'])",
    )
    acceptance_criteria: list[AcceptanceCriterion] | None = Field(
        default=None,
        description="List of acceptance criteria with scenario name and Gherkin steps",
    )
    clarification_questions: list[str] | None = Field(
        default=None,
        description="1 to 3 clarification questions to resolve ambiguities",
    )


class UserStoriesList(BaseModel):
    """List of user stories."""

    items: list[UserStory] = Field(description="List of user stories")


class TestTitle(BaseModel):
    """A test title for batch generation."""

    id: str = Field(description="Unique test ID (e.g., SC-001)")
    title: str = Field(description="Short, descriptive title for the test case")
    user_story_id: str = Field(description="Related user story ID (e.g., US-001)")
    test_type: Literal["Nominal", "Limite", "Erreur"] = Field(
        description="Type of test case"
    )


class TestTitlesList(BaseModel):
    """List of test titles."""

    items: list[TestTitle] = Field(description="List of test titles")


class Test(BaseModel):
    """A complete test scenario."""

    id: str = Field(description="Unique test case ID (e.g., SC-001, SC-LOGIN-001)")
    name: str = Field(description="Test case name")
    user_story_id: str | None = Field(default=None, description="Related user story ID")
    description: str | None = Field(
        default=None, description="Brief explanation of what the test verifies"
    )
    preconditions: str | None = Field(
        default=None,
        description="Preconditions that must be met before test execution",
    )
    steps: list[str] = Field(description="Ordered list of test steps in Gherkin format")
    test_data: list[str] | None = Field(
        default=None, description="Test data required for the test"
    )
    priority: Literal["Haute", "Moyenne", "Basse"] | None = Field(
        default=None, description="Test priority level"
    )
    test_type: Literal["Nominal", "Limite", "Erreur"] | None = Field(
        default=None, description="Type of test case"
    )
    expected_result: str = Field(description="Expected outcome of the test")


class TestsList(BaseModel):
    """List of tests."""

    items: list[Test] = Field(description="List of tests")


# Quick models for single-item generation (used by add_* tools)


class QuickUserStory(BaseModel):
    """Minimal user story fields generated by internal LLM call.

    Used by add_user_story tool - the id, summary, epic_name, issue_type,
    and requirement_ids are provided by the tool, this model generates the rest.
    """

    description: str = Field(
        description="User story in format: En tant que [persona], je veux [action], afin de [bénéfice]"
    )
    priority: Literal["Haute", "Moyenne", "Basse"] = Field(
        default="Moyenne", description="Story priority level"
    )
    story_points: int | None = Field(
        default=None,
        ge=1,
        le=21,
        description="Story point estimate (Fibonacci: 1, 2, 3, 5, 8, 13, 21)",
    )
    acceptance_criteria: list[AcceptanceCriterion] | None = Field(
        default=None,
        description="List of acceptance criteria with scenario name and Gherkin steps",
    )
    clarification_questions: list[str] | None = Field(
        default=None,
        description="1 to 3 clarification questions to resolve ambiguities",
    )


class QuickTest(BaseModel):
    """Minimal test fields generated by internal LLM call.

    Used by add_test tool - the id, name, user_story_id, and test_type
    are provided by the tool, this model generates the rest.
    """

    description: str | None = Field(
        default=None, description="Brief explanation of what the test verifies"
    )
    preconditions: str | None = Field(
        default=None,
        description="Preconditions that must be met before test execution",
    )
    steps: list[str] = Field(
        description="Ordered list of test steps in Gherkin format (Given/When/Then)"
    )
    test_data: list[str] | None = Field(
        default=None, description="Test data required for the test"
    )
    priority: Literal["Haute", "Moyenne", "Basse"] = Field(
        default="Moyenne", description="Test priority level"
    )
    expected_result: str = Field(description="Expected outcome of the test")


class QuickRequirement(BaseModel):
    """Minimal requirement fields generated by internal LLM call.

    Used by add_requirement tool - the id, title, and priority
    are provided by the tool, this model generates the rest.
    """

    description: str = Field(description="Detailed requirement description")
