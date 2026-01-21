"""JSON Schema definitions for Jira agent structured data."""

requirementsSchema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique requirement ID (e.g., EX-FON-001, EX-NFON-001)",
            },
            "title": {
                "type": "string",
                "description": "Short requirement title",
            },
            "description": {
                "type": "string",
                "description": "Detailed requirement description",
            },
            "priority": {
                "type": "string",
                "enum": ["Haute", "Moyenne", "Basse"],
                "description": "Requirement priority level",
            },
        },
        "required": ["id", "title", "description", "priority"],
        "additionalProperties": False,
    },
}

userStoriesSchema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique user story ID (e.g., US-001)",
            },
            "summary": {
                "type": "string",
                "description": "User story title/summary",
            },
            "description": {
                "type": "string",
                "description": "User story in format: As a [role], I want [feature], so that [benefit]",
            },
            "issue_type": {
                "type": "string",
                "enum": ["Story", "Task", "Bug"],
                "description": "Jira issue type",
            },
            "priority": {
                "type": "string",
                "enum": ["High", "Medium", "Low"],
                "description": "Story priority level",
            },
            "epic_name": {
                "type": "string",
                "description": "Parent epic name for grouping related stories",
            },
            "story_points": {
                "type": "integer",
                "minimum": 1,
                "maximum": 21,
                "description": "Story point estimate (Fibonacci: 1, 2, 3, 5, 8, 13, 21)",
            },
            "labels": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Labels for categorization",
            },
            "acceptance_criteria": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of acceptance criteria (Gherkin format preferred)",
            },
        },
        "required": ["id", "summary", "description", "priority"],
        "additionalProperties": False,
    },
}

testsSchema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique test case ID (e.g., SC-001, SC-LOGIN-001)",
            },
            "name": {
                "type": "string",
                "description": "Test case name",
            },
            "user_story_id": {
                "type": "string",
                "description": "Related user story ID",
            },
            "description": {
                "type": "string",
                "description": "Brief explanation of what the test verifies",
            },
            "preconditions": {
                "type": "string",
                "description": "Preconditions that must be met before test execution",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of test steps in Gherkin format",
            },
            "test_data": {
                "type": "string",
                "description": "Test data required for the test",
            },
            "priority": {
                "type": "string",
                "enum": ["Haute", "Moyenne", "Basse"],
                "description": "Test priority level",
            },
            "test_type": {
                "type": "string",
                "enum": ["Nominal", "Limite", "Erreur"],
                "description": "Type of test case",
            },
            "expected_result": {
                "type": "string",
                "description": "Expected outcome of the test",
            },
        },
        "required": ["id", "name", "steps", "expected_result"],
        "additionalProperties": False,
    },
}
