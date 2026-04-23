# /hopper - Task Management Skill

Quick task management for human-AI collaborative workflows.

## Usage

```
/hopper <command> [args]
```

## Commands

### Add a task
```
/hopper add "Task title"
/hopper add "Task title" --priority high --tag bug
```

### List tasks
```
/hopper list
/hopper list --status open
/hopper list --priority high
```

### Update task status
```
/hopper done <task-id>
/hopper claim <task-id> [--assign platform:task-name]
/hopper block <task-id>
```

### View task details
```
/hopper get <task-id>
```

### Quick shortcuts
```
/hopper ls          # List open tasks
/hopper todo        # List pending tasks
```

## Instructions

When the user invokes `/hopper`, execute the corresponding hopper CLI command in local mode.

**Parse the command:**
1. Extract the subcommand (add, list, done, claim, block, get, ls, todo)
2. Extract any arguments and flags

**Execute using the hopper CLI:**

For `add`:
```bash
hopper task add "<title>" [--priority <p>] [--tag <t>]
```

For `list`:
```bash
hopper task list [--status <s>] [--priority <p>]
```

For `done`:
```bash
hopper task status <task-id> completed -f
```

For `claim`:
```bash
hopper task status <task-id> in_progress --assign "<platform:task-name>" -f
```

For `block`:
```bash
hopper task status <task-id> blocked -f
```

For `get`:
```bash
hopper task get <task-id>
```

For `ls` (shortcut):
```bash
hopper ls
```

For `todo`:
```bash
hopper task list --status open
```

**Output:**
- Show the command output to the user
- For `add`, confirm the task was created and show the task ID
- For `list`, display tasks in a readable format
- For status changes, confirm the update

**Error handling:**
- If hopper CLI is not available, inform the user to install it
- If a task ID is not found, report the error clearly
