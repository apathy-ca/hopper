# Hopper CLI Guide

Complete guide to using the Hopper command-line interface.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Configuration](#configuration)
4. [Task Management](#task-management)
5. [Project Management](#project-management)
6. [Instance Management](#instance-management)
7. [Common Workflows](#common-workflows)
8. [Tips and Tricks](#tips-and-tricks)
9. [Troubleshooting](#troubleshooting)

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/your-org/hopper.git
cd hopper

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

### From PyPI (when published)

```bash
pip install hopper
```

### Verify Installation

```bash
hopper --version
hopper --help
```

## Quick Start

### 1. Initialize Configuration

```bash
hopper init
```

This will:
- Create `~/.hopper/config.yaml`
- Set up the default profile
- Configure API endpoint
- Optionally set up authentication

### 2. Create Your First Task

```bash
# Quick mode - just a title
hopper add "Fix login bug"

# With options
hopper task add "Implement dark mode" \
  --priority high \
  --tag feature \
  --tag ui
```

### 3. List Tasks

```bash
# List all tasks
hopper ls

# Filter by status
hopper task list --status open

# Filter by priority
hopper task list --priority high
```

### 4. Manage Tasks

```bash
# View task details
hopper task get abc12345

# Update a task
hopper task update abc12345 --title "New title"

# Change status
hopper task status abc12345 in_progress

# Delete a task
hopper task delete abc12345
```

## Configuration

### Configuration File

Hopper stores configuration in `~/.hopper/config.yaml`:

```yaml
active_profile: default
profiles:
  default:
    api:
      endpoint: http://localhost:8000
      timeout: 30
    auth:
      token: your-jwt-token
      api_key: null

  production:
    api:
      endpoint: https://api.hopper.io
      timeout: 60
    auth:
      token: prod-token
```

### Managing Profiles

```bash
# Create a new profile
hopper config set active_profile production

# Set profile-specific values
hopper config set api.endpoint https://api.hopper.io --profile production

# View configuration
hopper config list
hopper config list --profile production

# Get specific values
hopper config get api.endpoint
hopper config get auth.token
```

### Authentication

```bash
# Login with JWT token
hopper auth login --token YOUR_TOKEN

# Login with API key
hopper auth login --api-key YOUR_KEY

# Interactive login
hopper auth login

# Check authentication status
hopper auth status

# Logout
hopper auth logout
```

### Environment Variables

Override configuration with environment variables:

```bash
# API endpoint
export HOPPER_API_ENDPOINT=http://localhost:8000

# Authentication token
export HOPPER_AUTH_TOKEN=your-token

# Active profile
export HOPPER_ACTIVE_PROFILE=production

# Configuration file location
export HOPPER_CONFIG=~/.hopper/custom-config.yaml
```

## Task Management

### Creating Tasks

```bash
# Quick add
hopper add "Task title"

# Full command with options
hopper task add "Implement feature" \
  --description "Detailed description here" \
  --priority high \
  --tag feature \
  --tag backend \
  --project my-project \
  --status open

# Interactive mode
hopper task add
# (You'll be prompted for details)
```

### Listing Tasks

```bash
# List all tasks (default: 50 tasks)
hopper task list
hopper ls  # Shortcut

# Filter by status
hopper task list --status open
hopper task list --status in_progress
hopper task list --status completed

# Filter by priority
hopper task list --priority high
hopper task list --priority urgent

# Filter by project
hopper task list --project my-project

# Filter by tags
hopper task list --tag bug
hopper task list --tag bug --tag urgent  # Multiple tags

# Combine filters
hopper task list --status open --priority high --tag bug

# Sort and limit
hopper task list --sort-by priority --limit 10

# Compact view
hopper task list --compact

# JSON output (for scripting)
hopper task list --json
```

### Viewing Task Details

```bash
# Get full task information
hopper task get abc12345

# JSON output
hopper task get abc12345 --json
```

### Updating Tasks

```bash
# Update title
hopper task update abc12345 --title "New title"

# Update description
hopper task update abc12345 --description "New description"

# Update priority
hopper task update abc12345 --priority urgent

# Add tags
hopper task update abc12345 --add-tag critical

# Remove tags
hopper task update abc12345 --remove-tag old-tag

# Interactive update
hopper task update abc12345 --interactive
```

### Changing Status

```bash
# Change status
hopper task status abc12345 in_progress
hopper task status abc12345 completed
hopper task status abc12345 blocked

# Skip confirmation
hopper task status abc12345 completed --force
```

### Searching Tasks

```bash
# Search by keyword
hopper task search "login"
hopper task search "authentication bug"

# Search with filters
hopper task search "api" --status open
hopper task search "database" --priority high
```

### Deleting Tasks

```bash
# Delete with confirmation
hopper task delete abc12345

# Skip confirmation
hopper task delete abc12345 --force
```

## Project Management

### Creating Projects

```bash
# Simple creation
hopper project create my-project

# With description
hopper project create my-project \
  --description "My awesome project"

# With configuration (JSON)
hopper project create my-project \
  --config '{"routing":"llm","priority":"high"}'
```

### Listing Projects

```bash
# List all projects
hopper project list

# JSON output
hopper project list --json
```

### Viewing Project Details

```bash
# Get project information
hopper project get proj-123

# JSON output
hopper project get proj-123 --json
```

### Updating Projects

```bash
# Update name
hopper project update proj-123 --name "New name"

# Update description
hopper project update proj-123 --description "New description"

# Interactive update
hopper project update proj-123 --interactive
```

### Project Tasks

```bash
# List all tasks in a project
hopper project tasks proj-123

# Filter project tasks
hopper project tasks proj-123 --status open
hopper project tasks proj-123 --priority high
```

### Deleting Projects

```bash
# Delete with confirmation
hopper project delete proj-123

# Force delete (skip confirmation)
hopper project delete proj-123 --force
```

## Instance Management

### Understanding Instances

Hopper uses a hierarchical instance system:

- **Global Instance**: Strategic routing across all projects
- **Project Instance**: Project-specific task management
- **Orchestration Instance**: Execution-level task queues for runs

### Creating Instances

```bash
# Create a global instance
hopper instance create global-hopper --scope global

# Create a project instance
hopper instance create my-project-hopper \
  --scope project \
  --parent global-inst-id

# Create an orchestration instance
hopper instance create run-123 \
  --scope orchestration \
  --parent project-inst-id
```

### Listing Instances

```bash
# List all instances
hopper instance list

# Filter by scope
hopper instance list --scope global
hopper instance list --scope project
hopper instance list --scope orchestration

# Filter by parent
hopper instance list --parent global-inst-id
```

### Viewing Instance Hierarchy

```bash
# Show tree view of all instances
hopper instance tree

# Show tree from specific root
hopper instance tree --root global-inst-id

# JSON output
hopper instance tree --json
```

### Instance Control

```bash
# Start an instance
hopper instance start inst-123

# Stop an instance
hopper instance stop inst-123
hopper instance stop inst-123 --force

# Get instance status
hopper instance status inst-123

# Get instance details
hopper instance get inst-123
```

## Common Workflows

### Daily Task Management

```bash
# Start your day - see what's open
hopper ls --status open

# Add new tasks as they come in
hopper add "Review PR #42"
hopper add "Fix deployment issue" --priority urgent

# Update task status as you work
hopper task status abc123 in_progress
hopper task status abc123 completed

# End of day - see what you accomplished
hopper ls --status completed --sort-by updated
```

### Project Setup

```bash
# Create a new project
hopper project create my-new-project \
  --description "Description here"

# Create project-specific instance
hopper instance create my-project-instance \
  --scope project \
  --parent global-id

# Add initial tasks
hopper add "Setup repository" --project my-new-project
hopper add "Configure CI/CD" --project my-new-project
hopper add "Write documentation" --project my-new-project

# View project tasks
hopper project tasks my-new-project
```

### Bug Triage

```bash
# Search for bugs
hopper task search "bug" --status open

# Add new bug
hopper add "Login fails on mobile" \
  --priority high \
  --tag bug \
  --tag mobile

# Update priority as needed
hopper task update bug-123 --priority urgent --add-tag critical

# Track progress
hopper ls --tag bug --status in_progress
```

### Sprint Planning

```bash
# View high priority items
hopper ls --priority high --status open

# View project tasks
hopper project tasks sprint-5

# Update priorities
hopper task update task-1 --priority high
hopper task update task-2 --priority medium

# Generate sprint report (JSON for processing)
hopper ls --project sprint-5 --json > sprint-report.json
```

## Tips and Tricks

### Shortcuts

```bash
# Use shortcuts for common commands
hopper add "..."      # Instead of: hopper task add "..."
hopper ls             # Instead of: hopper task list
```

### JSON Output for Scripting

```bash
# Get JSON output for any command
hopper task list --json | jq '.[] | select(.priority == "high")'

# Count tasks by status
hopper task list --json | jq 'group_by(.status) | map({status: .[0].status, count: length})'

# Export tasks to CSV
hopper task list --json | jq -r '["ID","Title","Status","Priority"], (.[] | [.id, .title, .status, .priority]) | @csv'
```

### Aliases

Add to your `.bashrc` or `.zshrc`:

```bash
# Quick task creation
alias ha='hopper add'
alias hl='hopper ls'

# Status shortcuts
alias hs='hopper task status'
alias hd='hopper task get'

# Project shortcuts
alias hp='hopper project'
alias hpl='hopper project list'
```

### Filtering Combinations

```bash
# Open high-priority bugs
hopper ls --status open --priority high --tag bug

# My tasks in a project
hopper ls --project my-project --assignee me

# Recently updated tasks
hopper ls --sort-by updated --limit 10
```

### Compact Output

```bash
# Compact view for quick overview
hopper ls --compact

# Even more compact with limits
hopper ls --compact --limit 20
```

## Troubleshooting

### Connection Issues

```bash
# Check authentication status
hopper auth status

# Test API connection
hopper server status

# Verify configuration
hopper config list

# Check endpoint
hopper config get api.endpoint
```

### Authentication Errors

```bash
# Re-authenticate
hopper auth logout
hopper auth login

# Check token
hopper config get auth.token

# Set token manually
hopper config set auth.token YOUR_TOKEN
```

### Configuration Issues

```bash
# View current configuration
hopper config list

# Reset to defaults
rm ~/.hopper/config.yaml
hopper init

# Use different config file
hopper --config /path/to/config.yaml task list
```

### Verbose Output

```bash
# Enable verbose mode for debugging
hopper --verbose task list
hopper -v task add "Debug task"
```

### Common Errors

**"Configuration file not found"**
```bash
# Initialize configuration
hopper init
```

**"Authentication required"**
```bash
# Login with credentials
hopper auth login
```

**"Server not reachable"**
```bash
# Check if server is running
hopper server status

# Start local server
hopper server start
```

**"Invalid profile"**
```bash
# List available profiles
hopper config list

# Set correct profile
hopper config set active_profile default
```

## Getting Help

```bash
# General help
hopper --help

# Command-specific help
hopper task --help
hopper task add --help
hopper project --help
hopper instance --help

# Version information
hopper --version
```

## Next Steps

- Check out the [API Documentation](../README.md)
- Learn about [Hopper Architecture](../../docs/Hopper.Specification.md)
- Explore [Advanced Features](./advanced-guide.md)
- Contribute to [Hopper Development](../../CONTRIBUTING.md)
