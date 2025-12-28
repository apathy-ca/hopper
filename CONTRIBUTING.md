# Contributing to Hopper

Thank you for your interest in contributing to Hopper! This document provides guidelines and instructions for contributing to the project.

## Development Workflow

### Getting Started

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd hopper
   ```

2. **Set up the development environment**
   ```bash
   ./scripts/dev-setup.sh
   ```

3. **Activate the virtual environment**
   ```bash
   source venv/bin/activate
   ```

4. **Start the development services**
   ```bash
   docker-compose up -d
   ```

### Making Changes

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write code following our style guidelines
   - Add tests for new functionality
   - Update documentation as needed

3. **Run tests**
   ```bash
   ./scripts/run-tests.sh
   ```

4. **Format and lint your code**
   ```bash
   black src/ tests/
   ruff check src/ tests/
   mypy src/
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: Add your feature description"
   ```

6. **Push and create a pull request**
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Style Guidelines

### Python Style

- Follow PEP 8 style guidelines
- Use Black for code formatting (line length: 100)
- Use Ruff for linting
- All public APIs must have type hints
- Use descriptive variable and function names

### Type Hints

Type hints are **mandatory** for all public APIs:

```python
def create_task(
    title: str,
    description: str | None = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
) -> Task:
    """Create a new task."""
    ...
```

### Docstrings

Use Google-style docstrings for all public functions and classes:

```python
def route_task(task: Task, strategy: str) -> RoutingDecision:
    """
    Route a task to the appropriate project.

    Args:
        task: The task to route
        strategy: Routing strategy to use (rules, llm, sage)

    Returns:
        RoutingDecision with project assignment and confidence

    Raises:
        ValueError: If strategy is invalid
    """
    ...
```

### Database Models

- Use SQLAlchemy 2.0 syntax
- Add type hints to all mapped columns
- Include relationships with `back_populates`
- Add indexes for frequently queried fields
- Use `TimestampMixin` for created_at/updated_at

### Imports

Organize imports in the following order:
1. Standard library imports
2. Third-party imports
3. Local application imports

Use absolute imports:
```python
from hopper.models import Task
from hopper.config import get_settings
```

## Testing Requirements

### Test Coverage

- All new features must include tests
- Maintain >80% test coverage for models and core logic
- Use pytest for all tests

### Writing Tests

```python
def test_feature_description(clean_db: Session) -> None:
    """Test that feature works correctly."""
    # Arrange
    setup_data()

    # Act
    result = perform_action()

    # Assert
    assert result.is_valid()
```

### Test Fixtures

Use fixtures from `tests/conftest.py`:
- `engine`: Test database engine
- `db_session`: Database session
- `clean_db`: Clean database session

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=hopper --cov-report=html

# Run specific test file
pytest tests/models/test_task.py

# Run specific test
pytest tests/models/test_task.py::test_task_creation
```

## Commit Message Guidelines

Follow the Conventional Commits specification:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Examples:
```
feat: Add LLM-based routing strategy
fix: Handle missing task feedback gracefully
docs: Update API documentation for routing endpoints
test: Add tests for task delegation
```

## Code Review Process

### Before Requesting Review

- [ ] All tests pass
- [ ] Code is formatted with Black
- [ ] Linting passes (Ruff)
- [ ] Type checking passes (mypy)
- [ ] Documentation is updated
- [ ] Test coverage is maintained

### Review Guidelines

- Reviews should be constructive and respectful
- Focus on code quality, correctness, and maintainability
- Ask questions if something is unclear
- Suggest improvements with explanations

## Database Migrations

When changing database models:

1. **Create a migration**
   ```bash
   alembic revision --autogenerate -m "Add new field to Task"
   ```

2. **Review the migration**
   Check `alembic/versions/` for the generated migration

3. **Test the migration**
   ```bash
   alembic upgrade head
   alembic downgrade -1
   alembic upgrade head
   ```

4. **Commit the migration**
   Include migrations in your pull request

## Documentation

### API Documentation

- FastAPI automatically generates OpenAPI docs
- Add docstrings to all endpoints
- Use Pydantic models for request/response validation

### Code Documentation

- Document complex logic with inline comments
- Keep comments up-to-date with code changes
- Explain "why" not "what" in comments

### README Updates

Update README.md when:
- Adding new features
- Changing installation process
- Updating configuration options

## Getting Help

- **Questions**: Open a GitHub Discussion
- **Bugs**: Open a GitHub Issue with reproduction steps
- **Features**: Open a GitHub Issue with use case description

## License

By contributing to Hopper, you agree that your contributions will be licensed under the same license as the project (MIT License).

---

Thank you for contributing to Hopper! 🎉
