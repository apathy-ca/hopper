# Worker: MCP Integration

**Branch:** cz1/feat/mcp-integration
**Dependencies:** api-core
**Duration:** 2 days

## Mission

Create the MCP (Model Context Protocol) server that allows Claude and other AI assistants to interact with Hopper. This is the primary interface for human-AI collaborative workflows.

## Background

Phase 1 Week 2 includes MCP server implementation that:
- Works with Claude Desktop and other MCP clients
- Exposes Hopper functionality as MCP tools
- Handles authentication and state management
- Provides rich context for AI decision-making

The MCP server will be the main way users interact with Hopper through Claude.

## Tasks

### Task 1: MCP Server Setup

1. Create `src/hopper/mcp/server.py`:
   - MCP server initialization
   - Tool registration
   - Resource management
   - Context management
   - Error handling

2. Create `src/hopper/mcp/config.py`:
   - MCP server configuration
   - API client setup
   - Authentication configuration
   - Server metadata

3. Create `src/hopper/mcp/__init__.py`:
   - Export server factory
   - Version information

4. Add MCP dependencies to `pyproject.toml`:
   - `mcp` SDK
   - Any required transport libraries

**Checkpoint:** Commit MCP server setup

### Task 2: Core MCP Tools Implementation

Reference: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md` (MCP Integration section)

1. Create `src/hopper/mcp/tools/task_tools.py`:
   - `hopper_create_task` - Create a new task
     - Parameters: title, description, priority, tags, project
     - Returns: Created task with ID
   - `hopper_list_tasks` - List tasks with filters
     - Parameters: status, priority, project, tags, limit
     - Returns: List of tasks
   - `hopper_get_task` - Get task details
     - Parameters: task_id
     - Returns: Full task information
   - `hopper_update_task` - Update task
     - Parameters: task_id, updates
     - Returns: Updated task
   - `hopper_update_task_status` - Change task status
     - Parameters: task_id, new_status
     - Returns: Updated task

2. Create `src/hopper/mcp/tools/project_tools.py`:
   - `hopper_list_projects` - List all projects
   - `hopper_get_project` - Get project details
   - `hopper_create_project` - Create new project
   - `hopper_get_project_tasks` - Get tasks for a project

3. Create `src/hopper/mcp/tools/routing_tools.py`:
   - `hopper_route_task` - Route a task to appropriate destination
     - Parameters: task_id, context
     - Returns: Routing decision
   - `hopper_get_routing_suggestions` - Get routing suggestions
     - Parameters: task_description
     - Returns: Suggested destinations with confidence

4. Create `src/hopper/mcp/tools/__init__.py`:
   - Export all tools
   - Tool registry

**Checkpoint:** Commit core MCP tools

### Task 3: MCP Resources Implementation

1. Create `src/hopper/mcp/resources/task_resources.py`:
   - Expose tasks as resources
   - Resource URIs: `hopper://tasks/{task_id}`
   - Resource metadata and content

2. Create `src/hopper/mcp/resources/project_resources.py`:
   - Expose projects as resources
   - Resource URIs: `hopper://projects/{project_id}`

3. Create `src/hopper/mcp/resources/__init__.py`:
   - Export all resources
   - Resource registry

**Checkpoint:** Commit MCP resources

### Task 4: Context Management

1. Create `src/hopper/mcp/context.py`:
   - Server context management
   - Current user/session tracking
   - Active project context
   - Recent tasks cache
   - Conversation state

2. Add context to tool calls:
   - Inject current user
   - Inject active project
   - Provide relevant history
   - Smart defaults based on context

3. Add context persistence:
   - Save conversation context
   - Restore context on reconnect
   - Clear stale context

**Checkpoint:** Commit context management

### Task 5: MCP Server Entry Point and Configuration

1. Create `src/hopper/mcp/main.py`:
   - MCP server entry point
   - Command-line interface for server
   - Server lifecycle management

2. Create MCP configuration file `.hopper/mcp-server.json`:
   - Server metadata
   - Tool descriptions
   - Resource descriptions
   - Transport configuration

3. Add CLI command to start MCP server:
   - `hopper mcp start` - Start MCP server
   - `hopper mcp stop` - Stop MCP server
   - `hopper mcp status` - Check server status

4. Create installation instructions:
   - How to configure in Claude Desktop
   - How to test MCP connection
   - Troubleshooting guide

**Checkpoint:** Commit MCP server entry point

### Task 6: Testing and Documentation

1. Create `tests/mcp/conftest.py`:
   - MCP test client fixture
   - Mock API server fixture
   - Test context fixtures

2. Create `tests/mcp/test_task_tools.py`:
   - Test all task tools
   - Test tool parameter validation
   - Test tool responses
   - Test error handling

3. Create `tests/mcp/test_project_tools.py`:
   - Test all project tools

4. Create `tests/mcp/test_routing_tools.py`:
   - Test routing tools

5. Create `tests/mcp/test_resources.py`:
   - Test resource access
   - Test resource URIs

6. Create `tests/mcp/test_context.py`:
   - Test context management
   - Test context persistence

7. Create `docs/mcp-integration.md`:
   - MCP server overview
   - Installation and configuration
   - Available tools and usage examples
   - Available resources
   - Context management
   - Troubleshooting

8. Create usage examples:
   - Example conversations with Claude
   - Common workflows
   - Integration patterns

**Checkpoint:** Commit tests and documentation

## Deliverables

- [ ] MCP server implementation
- [ ] Task management tools (create, list, get, update, status)
- [ ] Project management tools
- [ ] Routing tools
- [ ] Task and project resources
- [ ] Context management
- [ ] MCP server CLI commands
- [ ] Claude Desktop configuration instructions
- [ ] Comprehensive test suite
- [ ] MCP integration documentation with examples

## Success Criteria

- ✅ MCP server starts successfully with `hopper mcp start`
- ✅ Server appears in Claude Desktop's MCP settings
- ✅ Can create tasks from Claude using `hopper_create_task`
- ✅ Can list tasks from Claude using `hopper_list_tasks`
- ✅ Can update tasks from Claude
- ✅ Can route tasks from Claude
- ✅ Resources are accessible via `hopper://` URIs
- ✅ Context is maintained across tool calls
- ✅ All tests pass
- ✅ End-to-end workflow: Claude → MCP → API → Database works
- ✅ Documentation is clear and complete

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md`
- Specification: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- MCP SDK documentation
- Claude Desktop MCP configuration guide

## Notes

- MCP server should be robust and handle connection issues gracefully
- Tool descriptions should be clear for Claude to understand
- Parameter validation is critical for good UX
- Error messages should be helpful and actionable
- Context management improves conversation quality
- Test with real Claude Desktop client, not just unit tests
- Consider adding logging for debugging MCP interactions
- MCP server can run as a subprocess or standalone process
- Authentication should work seamlessly (API key preferred for MCP)
- Consider rate limiting to prevent abuse
