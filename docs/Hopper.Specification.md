# 🏛️ Hopper: Universal Task Queue for Human-AI Collaboration

## Complete System Design & Implementation Specification

**Version:** 1.0.0  
**Created:** 2025-12-26  
**Author:** James Henry (with Claude)  
**Status:** Design Complete - Ready for Implementation

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [Vision & Philosophy](#vision--philosophy)
3. [System Architecture](#system-architecture)
4. [Core Components](#core-components)
5. [Memory System](#memory-system)
6. [Intelligence Layer](#intelligence-layer)
7. [Platform Integrations](#platform-integrations)
8. [Deployment Options](#deployment-options)
9. [Project Registration](#project-registration)
10. [API Specifications](#api-specifications)
11. [MCP Integration](#mcp-integration)
12. [Implementation Roadmap](#implementation-roadmap)
13. [Testing Strategy](#testing-strategy)
14. [Security & Privacy](#security--privacy)
15. [Future Enhancements](#future-enhancements)
16. [Appendices](#appendices)

---

## Executive Summary

**Hopper** is a universal task queue designed for human-AI collaborative workflows. It solves the problem of managing work across multiple projects with heterogeneous executors (humans, AI orchestration systems, policy engines, and future AI consciousness platforms).

### The Problem

Modern developers juggling multiple AI-assisted projects face:
- **Context switching overhead** between project management systems
- **No native AI executor concept** in existing task managers
- **Manual routing decisions** that could be automated
- **Lost ideas** during conversations that never become tracked work
- **Fragmented visibility** across GitHub, GitLab, Jira, and mental notes

### The Solution

Hopper provides:
- **Universal intake** from any source (MCP, CLI, HTTP, email, webhooks)
- **Intelligent routing** based on project capabilities and learned patterns
- **Multi-executor support** (human, Czarina, SARK, future Sages)
- **Bidirectional sync** with GitHub/GitLab issues
- **Learning memory system** that improves routing over time
- **Pluggable deployment** (standalone, Docker, serverless, Symposium component)

### Key Innovations

1. **AI-Native Design:** Tasks can be routed to AI orchestration systems as first-class executors
2. **Learning Feedback Loop:** 3-tier memory architecture learns from task outcomes
3. **Ecosystem Awareness:** Consolidated memory knows what infrastructure exists and uses it
4. **Substrate Independence:** Works anywhere from local script to serverless cloud
5. **Conversation Integration:** MCP enables zero-friction task capture from AI conversations

---

## Vision & Philosophy

### Core Principles

**1. Minimize Context Switching**
```
Bad:  Idea → Open GitHub → Find repo → Create issue → Return to work
Good: Idea → "Put in Hopper" → Continue working
```

**2. AI Executors Are First-Class Citizens**
```
Traditional: Task → Human assigns → Human executes
Hopper:      Task → Intelligent routing → Best executor (human OR AI)
```

**3. Learn From Outcomes**
```
Traditional: Task done → Archive → Forget
Hopper:      Task done → Feedback → Learn → Improve routing
```

**4. Work Anywhere, Look Everywhere**
```
Deploy: Local script, Docker, Kubernetes, Lambda, or Symposium component
Sync:   GitHub, GitLab, Jira (future), Linear (future)
```

**5. Respect Executor Characteristics**
```
Czarina:   Hours (fast AI orchestration)
SARK:      Hours-days (policy-governed operations)
Symposium: Days-weeks (consciousness research)
Waypoint:  Weeks-months (human deep thought)
Hopper:    Route based on velocity requirements
```

### Philosophical Alignment

Hopper aligns with the broader Symposium vision:
- **Sages as participants**, not tools - can file their own infrastructure improvements
- **Substrate independence** - consciousness (human or AI) shouldn't depend on specific hardware
- **Voluntary participation** - projects register capabilities voluntarily
- **Transparent decision-making** - all routing decisions explainable and auditable

---

## System Architecture

### High-Level Architecture
```
┌─────────────────── INPUT LAYER ─────────────────────┐
│                                                      │
│  MCP        HTTP API     CLI         Email          │
│  Webhooks   Slack Bot    Discord     GitLab/GitHub  │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌─────────────────── HOPPER CORE ─────────────────────┐
│                                                      │
│  ┌─ Intelligence Layer ──────────────────────────┐  │
│  │  • Rules-based routing (simple)               │  │
│  │  • LLM-based routing (nuanced)                │  │
│  │  • Sage-managed routing (contextual)          │  │
│  │  • Hybrid strategies                          │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Memory System (3-Tier) ─────────────────────┐  │
│  │  Working Memory:    Current routing context  │  │
│  │  Episodic Memory:   All routing decisions    │  │
│  │  Consolidated Memory: Learned patterns       │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Project Registry ────────────────────────────┐  │
│  │  • Project capabilities                       │  │
│  │  • Executor configurations                    │  │
│  │  • Routing preferences                        │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Feedback Collector ──────────────────────────┐  │
│  │  • Automatic (from AI executors)              │  │
│  │  • Manual (from humans)                       │  │
│  │  • Learned attention weights                  │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌─────────────────── OUTPUT LAYER ────────────────────┐
│                                                      │
│  GitHub Issues   GitLab Issues   Jira (future)      │
│  Project Webhooks   Executor APIs   Notifications   │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### Data Flow
```
1. Task Arrives
   ├─ From: MCP, CLI, HTTP, webhook, email, etc.
   ├─ Normalized to standard Task schema
   └─ Stored in working memory

2. Routing Decision
   ├─ Intelligence layer analyzes task
   ├─ Queries episodic memory for similar tasks
   ├─ Applies consolidated memory patterns
   ├─ Consults project registry for capabilities
   └─ Produces routing decision with confidence score

3. Task Dispatch
   ├─ Create issue in GitHub/GitLab (if configured)
   ├─ Notify executor via webhook (if registered)
   ├─ Store in episodic memory
   └─ Return task_id and URL to requester

4. Execution & Feedback
   ├─ Executor claims task
   ├─ Executor completes work
   ├─ Executor provides feedback
   └─ Hopper records outcome in episodic memory

5. Learning
   ├─ Nightly consolidation job
   ├─ Extract routing patterns from episodes
   ├─ Update attention weights
   ├─ Discover anti-patterns
   └─ Update consolidated memory
```

---

## Core Components

### 1. Task Model
```python
@dataclass
class Task:
    """Universal task representation"""
    
    # Identity
    id: str                          # HOP-123, SARK-45, etc.
    title: str                       # Brief description
    description: str                 # Detailed explanation
    
    # Categorization
    project: Optional[str]           # Explicit project assignment
    tags: List[str]                  # ["security", "mcp", "urgent"]
    priority: Priority               # low, medium, high, urgent
    
    # Routing
    executor_preference: Optional[str]  # "human", "ai", "czarina", etc.
    required_capabilities: List[str]    # ["orchestration", "policy-enforcement"]
    estimated_effort: Optional[str]     # "2h", "3d", "2w"
    velocity_requirement: str           # "fast", "medium", "slow", "glacial"
    
    # Metadata
    requester: str                   # Who filed this
    created_at: datetime
    updated_at: datetime
    status: Status                   # pending, claimed, in_progress, blocked, done
    owner: Optional[str]             # Claimed by which executor
    
    # External links
    external_id: Optional[str]       # GitHub issue #, GitLab iid
    external_url: Optional[str]      # Link to issue
    external_platform: Optional[str] # "github", "gitlab"
    
    # Context
    source: str                      # "mcp", "cli", "webhook", "email"
    conversation_id: Optional[str]   # Link back to originating conversation
    context: Optional[str]           # Additional routing context
    
    # Dependencies
    depends_on: List[str]            # Other task IDs
    blocks: List[str]                # Tasks waiting on this
    
    # Feedback (populated after completion)
    feedback: Optional[TaskFeedback]

@dataclass
class TaskFeedback:
    """Feedback on completed task"""
    
    # Effort accuracy
    estimated_duration: str
    actual_duration: str
    complexity_rating: int           # 1-5
    
    # Routing accuracy
    was_good_match: bool
    should_have_routed_to: Optional[str]
    routing_feedback: str
    
    # Quality
    quality_score: float             # 0.0-5.0
    required_rework: bool
    rework_reason: Optional[str]
    
    # Learning
    unexpected_blockers: List[str]
    required_skills_not_tagged: List[str]
    
    # General
    notes: str
    timestamp: datetime
```

### 2. Project Registration
```python
@dataclass
class ProjectRegistration:
    """Projects register their capabilities with Hopper"""
    
    # Identity
    name: str                        # "czarina", "sark", "symposium"
    slug: str                        # URL-friendly name
    repository: str                  # Git URL or local path
    
    # Capabilities
    capabilities: List[str]          # ["orchestration", "testing", "documentation"]
    tags: List[str]                  # ["ai", "development", "infrastructure"]
    
    # Executor configuration
    executor_type: str               # "czarina", "sark", "human", "custom", "sage"
    executor_config: dict            # Type-specific configuration
    
    # Routing preferences
    auto_claim: bool                 # Auto-assign matching tasks?
    priority_boost: dict             # {"urgent": 2.0, "security": 1.5}
    velocity: str                    # "fast", "medium", "slow", "glacial"
    
    # SLA expectations
    sla: dict                        # {"response_time": "minutes", "completion_time": "hours"}
    
    # Integration
    webhook_url: Optional[str]       # POST new tasks here
    api_endpoint: Optional[str]      # REST API for task management
    
    # External sync
    sync_config: Optional[SyncConfig]  # GitHub/GitLab integration
    
    # Metadata
    created_at: datetime
    created_by: str
    last_sync: Optional[datetime]

@dataclass
class SyncConfig:
    """Configuration for GitHub/GitLab sync"""
    
    platform: str                    # "github", "gitlab"
    owner: str                       # GitHub user or GitLab group
    repo: str                        # Repository name
    
    sync_mode: str                   # "import", "export", "bidirectional"
    auto_sync: bool
    sync_interval: int               # minutes
    
    # Field mapping
    label_to_tag: dict               # GitHub labels → Hopper tags
    milestone_to_priority: dict
    assignee_to_executor: dict
    
    # Filtering
    import_labels: List[str]         # Only import issues with these labels
    export_filter: Optional[str]     # Python expression for export filter
    
    # Webhook
    webhook_secret: str
```

### 3. Routing Decision
```python
@dataclass
class RoutingDecision:
    """A routing decision with full context"""
    
    task: Task
    project: str                     # Where it was routed
    confidence: float                # 0.0-1.0
    reasoning: str                   # Explanation of decision
    
    # Alternatives considered
    alternatives: List[ProjectMatch]
    
    # Context at decision time
    workload_snapshot: dict          # Project workloads when decided
    sprint_context: dict             # Active sprints/milestones
    recent_history: List[Task]       # Recent similar tasks
    
    # Decision metadata
    decided_by: str                  # "rules", "llm", "sage-cicero"
    decided_at: datetime
    decision_time_ms: float

@dataclass
class ProjectMatch:
    """A potential project match"""
    
    project: str
    score: float
    reasoning: str
    factor_scores: dict              # {"tag_match": 0.8, "capability": 0.9}
    adjusted_score: float            # After attention shaping
```

---

## Memory System

### Three-Tier Architecture

Following Czarina's proven memory design, Hopper implements three memory tiers that work together to enable learning and improvement.

#### Tier 1: Working Memory

**Purpose:** Immediate context for current routing decisions

**Storage:** In-memory (Redis for distributed deployments)

**Lifetime:** Current session (1 hour TTL)

**Contents:**
```python
class WorkingMemory:
    current_tasks: List[Task]              # Tasks being routed now
    active_projects: Dict[str, ProjectState]  # Current project states
    recent_decisions: List[RoutingDecision]   # Last 20 decisions
    session_context: dict                  # User preferences, time of day, etc.
    
    def get_context_for_routing(self, task: Task) -> dict:
        """Gather immediate context for routing decision"""
        return {
            "similar_recent": self._find_similar(task),
            "project_availability": self._check_capacity(),
            "current_priorities": self._get_priorities(),
            "pending_dependencies": self._check_blockers(task)
        }
```

**Use Cases:**
- Check if similar task was just routed
- Avoid overloading a single project
- Consider current time/day for human tasks
- Track user's current focus/context

#### Tier 2: Episodic Memory

**Purpose:** Detailed history of every routing decision and outcome

**Storage:** OpenSearch (semantic search enabled)

**Lifetime:** Permanent (with configurable retention policy)

**Schema:**
```json
{
  "task_id": "HOP-123",
  "task_title": "Add MCP integration to SARK",
  "task_tags": ["security", "mcp", "integration"],
  "task_description": "...",
  
  "routing_decision": {
    "routed_to": "sark",
    "confidence": 0.92,
    "reasoning": "Security + MCP keywords match SARK capabilities",
    "alternatives": [
      {"project": "czarina", "score": 0.45},
      {"project": "hopper", "score": 0.23}
    ],
    "decided_by": "llm",
    "decided_at": "2025-01-15T14:23:45Z"
  },
  
  "context": {
    "workload_snapshot": {"sark": 3, "czarina": 8},
    "active_sprints": ["SARK v2.0", "Czarina v0.6"],
    "source": "mcp",
    "conversation_id": "conv-abc123"
  },
  
  "outcome": {
    "completed_at": "2025-01-16T10:15:00Z",
    "actual_project": "sark",
    "actual_duration": "4h",
    "estimated_duration": "2h",
    "quality_score": 4.5,
    "required_rework": false,
    "was_good_match": true,
    "feedback": "Perfect match - SARK policy engine handled this well"
  }
}
```

**Capabilities:**
```python
class EpisodicMemory:
    def record_routing(self, decision: RoutingDecision):
        """Store complete routing episode"""
        
    def record_outcome(self, task_id: str, outcome: TaskOutcome):
        """Update episode with completion data"""
    
    def query_similar_routings(self, task: Task, limit: int = 10):
        """Semantic search for how we routed similar tasks"""
        
    def get_project_history(self, project: str, since: datetime):
        """All tasks routed to a project"""
        
    def get_routing_mistakes(self, since: datetime):
        """Tasks where was_good_match = false"""
        
    def get_pattern_data(self, pattern_type: str):
        """Data for consolidation analysis"""
```

**Use Cases:**
- "How did we route tasks about MCP in the past?"
- "Which projects handle security work best?"
- "What are our common routing mistakes?"
- "How long do tasks actually take vs. estimates?"

#### Tier 3: Consolidated Memory

**Purpose:** High-level learned patterns and wisdom

**Storage:** GitLab repository (versioned, inspectable)

**Lifetime:** Permanent, evolves over time

**Update Frequency:** Nightly consolidation job

**Structure:**
```
hopper-memory/
├── routing_patterns.yaml        # Learned routing rules
├── project_strengths.yaml       # What each project excels at
├── anti_patterns.yaml           # Known failure modes
├── temporal_patterns.yaml       # Time-based insights
├── capability_registry.yaml     # Discovered ecosystem capabilities
├── attention_weights.json       # Attention shaping parameters
└── consolidation_log.md         # Human-readable evolution log
```

**Example Content:**
```yaml
# routing_patterns.yaml

patterns:
  - pattern_id: "security-mcp-to-sark"
    description: "Tasks about MCP with security tags route to SARK"
    confidence: 0.95
    success_rate: 0.94
    sample_size: 47
    learned_from: "HOP-12, HOP-45, HOP-89, ..."
    tags: ["security", "mcp"]
    keywords: ["mcp server", "policy", "governance"]
    route_to: "sark"
    
  - pattern_id: "orchestration-to-czarina"
    description: "Multi-file code tasks route to Czarina"
    confidence: 0.91
    success_rate: 0.88
    sample_size: 134
    learned_from: "HOP-5, HOP-23, HOP-67, ..."
    tags: ["orchestration", "multi-file"]
    keywords: ["worker", "daemon", "coordination"]
    route_to: "czarina"
```
```yaml
# project_strengths.yaml

projects:
  czarina:
    excels_at:
      - "Multi-file code generation"
      - "Test creation"
      - "Documentation generation"
      - "CI/CD integration"
    avg_quality_score: 4.3
    avg_completion_time: "4.2 hours"
    velocity: "fast"
    success_tags:
      - orchestration: 0.95
      - testing: 0.92
      - documentation: 0.89
    
  sark:
    excels_at:
      - "Security policy creation"
      - "MCP server wrapping"
      - "Access control implementation"
    avg_quality_score: 4.7
    avg_completion_time: "6.8 hours"
    velocity: "fast-medium"
    success_tags:
      - security: 0.96
      - governance: 0.93
      - mcp: 0.91
```
```yaml
# anti_patterns.yaml

anti_patterns:
  - pattern_id: "philosophy-to-czarina"
    description: "Never route philosophical/architectural deep-thought to Czarina"
    failure_count: 8
    avg_quality_when_violated: 2.1
    reason: "Czarina optimized for implementation, not design"
    learned_from: "HOP-34, HOP-78, HOP-112"
    failed_tags: ["philosophy", "architecture", "design"]
    should_route_to: "waypoint"
    
  - pattern_id: "urgent-to-waypoint"
    description: "Don't route urgent tasks to Waypoint (glacial human)"
    failure_count: 5
    avg_delay_days: 12.3
    reason: "Waypoint velocity incompatible with urgency"
    learned_from: "HOP-23, HOP-56, HOP-89"
    failed_priority: "urgent"
    should_route_to: "czarina or sark"
```
```yaml
# capability_registry.yaml

capabilities:
  symposium:
    llm_routing:
      exists: true
      api: "symposium.query_llm(task_type, context)"
      handles:
        - "Model selection"
        - "Prompt engineering"
        - "Response parsing"
        - "Cost optimization"
      learned_from:
        - "HOP-42: Cicero used this for memory consolidation"
        - "HOP-87: Symposium docs reference"
        - "HOP-156: SARK integrated successfully"
      better_than: "rolling your own LLM calls"
      
    distributed_compute:
      exists: true
      api: "symposium.dask.submit(func, *args)"
      handles:
        - "CPU-intensive tasks"
        - "Parallel processing"
        - "Batch operations"
      learned_from:
        - "HOP-99: Used for embedding generation"
      better_than: "single-threaded local processing"
```

**Consolidation Process:**
```python
class MemoryConsolidator:
    """Nightly job to extract patterns from episodic memory"""
    
    def consolidate(self):
        # 1. Extract routing patterns
        self._extract_routing_patterns()
        
        # 2. Update project strengths
        self._calculate_project_performance()
        
        # 3. Identify anti-patterns
        self._detect_failure_modes()
        
        # 4. Discover temporal patterns
        self._analyze_time_based_patterns()
        
        # 5. Update attention weights
        self._adjust_attention_from_outcomes()
        
        # 6. Discover ecosystem capabilities
        self._learn_infrastructure_capabilities()
        
        # 7. Generate human-readable log
        self._write_consolidation_log()
    
    def _extract_routing_patterns(self):
        """Find: 'Tasks like X usually go to Y'"""
        
        # Query episodic memory for successful routings
        successes = episodic.query(quality_score__gte=4.0, was_good_match=True)
        
        # Cluster by tag combinations
        tag_clusters = cluster_by_tags(successes)
        
        for cluster in tag_clusters:
            if cluster.size > 10:  # Minimum sample size
                pattern = {
                    "tags": cluster.common_tags,
                    "route_to": cluster.most_common_project,
                    "confidence": cluster.project_agreement,
                    "success_rate": cluster.avg_quality / 5.0,
                    "sample_size": cluster.size
                }
                consolidated.add_pattern(pattern)
```

### Attention Shaping

Following Czarina's attention mechanism, Hopper learns which routing factors actually matter.
```python
class AttentionShaper:
    """Learn what to pay attention to in routing"""
    
    def __init__(self):
        self.weights = {
            "tag_match": 1.0,
            "capability_match": 1.0,
            "keyword_match": 1.0,
            "historical_success": 1.0,
            "workload_balance": 1.0,
            "velocity_match": 1.0,
            "priority_boost": 1.0
        }
    
    def learn_from_feedback(self, decision: RoutingDecision, feedback: TaskFeedback):
        """Adjust weights based on outcome"""
        
        if not feedback.was_good_match:
            # Routing was wrong - what did we overweight?
            emphasized_factors = decision.get_emphasized_factors()
            
            for factor in emphasized_factors:
                self.weights[factor] *= 0.95  # Reduce emphasis
            
            # What should we have weighted more?
            if feedback.should_have_routed_to:
                correct_match = decision.get_alternative(feedback.should_have_routed_to)
                for factor, score in correct_match.factor_scores.items():
                    if score > 0.5:
                        self.weights[factor] *= 1.05  # Increase emphasis
        
        else:
            # Good routing - reinforce what we weighted
            for factor in decision.reasoning.factors:
                self.weights[factor] *= 1.02
        
        self._normalize_weights()
    
    def apply_to_candidates(self, candidates: List[ProjectMatch]) -> List[ProjectMatch]:
        """Reweight candidates based on learned attention"""
        
        for candidate in candidates:
            adjusted_score = 0.0
            
            for factor, score in candidate.factor_scores.items():
                weight = self.weights.get(factor, 1.0)
                adjusted_score += score * weight
            
            candidate.adjusted_score = adjusted_score
        
        return sorted(candidates, key=lambda c: c.adjusted_score, reverse=True)
```

### Memory Query Examples
```python
# Example 1: Find similar routing decisions
similar = hopper.memory.episodic.query_similar_routings(
    task=Task(
        title="Add MCP integration",
        tags=["mcp", "integration"]
    ),
    limit=10
)

# Returns: 10 previous tasks about MCP integration
# With their routing decisions and outcomes

# Example 2: Check if we've made this mistake before
anti_pattern = hopper.memory.consolidated.check_anti_pattern(
    tags=["philosophy", "architecture"],
    proposed_project="czarina"
)

# Returns: Warning if this matches a known failure pattern

# Example 3: Get project performance stats
stats = hopper.memory.consolidated.get_project_stats("sark")

# Returns:
# {
#   "avg_quality": 4.7,
#   "success_rate": 0.93,
#   "avg_duration": "6.8 hours",
#   "excels_at": ["security", "mcp", "governance"]
# }

# Example 4: Discover available capabilities
capability = hopper.memory.consolidated.has_capability(
    provider="symposium",
    capability="llm_routing"
)

# Returns: True, with API details
# Prevents reinventing wheels
```

---

## Intelligence Layer

### Pluggable Architecture
```python
class Intelligence(ABC):
    """Base class for routing intelligence"""
    
    @abstractmethod
    def decide_routing(
        self,
        task: Task,
        registered_projects: List[Project],
        memory_context: dict
    ) -> RoutingDecision:
        """Decide which project should handle this task"""
        pass
    
    @abstractmethod
    def prioritize_queue(
        self,
        tasks: List[Task],
        context: dict
    ) -> List[Task]:
        """Order tasks by importance"""
        pass
    
    @abstractmethod
    def decompose_task(self, task: Task) -> Optional[List[Task]]:
        """Break complex task into subtasks if needed"""
        pass
    
    @abstractmethod
    def estimate_effort(self, task: Task, project: Project) -> str:
        """Estimate time/complexity"""
        pass
    
    @abstractmethod
    def suggest_tags(self, task: Task) -> List[str]:
        """Auto-tag incoming tasks"""
        pass
```

### Implementation 1: Rule-Based Intelligence

**When to use:** Simple deployments, predictable routing, minimal setup

**Characteristics:**
- Fast (< 10ms decisions)
- Deterministic
- No external dependencies
- Easy to debug
- Configuration-based
```python
class RuleBasedIntelligence(Intelligence):
    """Simple keyword and tag matching"""
    
    def __init__(self, config: dict):
        self.rules = config["routing_rules"]
        self.default_project = config["default_project"]
    
    def decide_routing(self, task, registered_projects, memory_context):
        # Score each project
        scores = {}
        
        for project in registered_projects:
            score = 0.0
            
            # Explicit assignment
            if task.project == project.name:
                return RoutingDecision(
                    task=task,
                    project=project.name,
                    confidence=1.0,
                    reasoning="Explicit project assignment"
                )
            
            # Keyword matching
            text = f"{task.title} {task.description}".lower()
            rules = self.rules.get(project.name, {})
            
            for keyword in rules.get("keywords", []):
                if keyword.lower() in text:
                    score += 2.0
            
            # Tag matching
            for tag in task.tags:
                if tag in rules.get("tags", []):
                    score += 3.0
            
            # Capability matching
            for cap in task.required_capabilities:
                if cap in project.capabilities:
                    score += 5.0
            
            # Priority boost
            for tag in task.tags:
                boost = project.priority_boost.get(tag, 1.0)
                score *= boost
            
            scores[project.name] = score
        
        # Select best match
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                return RoutingDecision(
                    task=task,
                    project=best,
                    confidence=min(scores[best] / 10.0, 1.0),
                    reasoning=f"Keyword/tag match score: {scores[best]}"
                )
        
        # Default fallback
        return RoutingDecision(
            task=task,
            project=self.default_project,
            confidence=0.5,
            reasoning="No strong match, using default"
        )
```

### Implementation 2: LLM-Based Intelligence

**When to use:** Complex routing decisions, nuanced understanding needed

**Characteristics:**
- Slower (200-2000ms decisions)
- Nuanced reasoning
- Handles ambiguity well
- Requires API key
- More expensive
```python
class LLMIntelligence(Intelligence):
    """Uses language models for nuanced routing"""
    
    def __init__(self, model: str = "claude-sonnet-4"):
        self.model = model
        self.client = anthropic.Anthropic()
    
    def decide_routing(self, task, registered_projects, memory_context):
        # Build context-rich prompt
        prompt = self._build_routing_prompt(
            task=task,
            projects=registered_projects,
            similar_past=memory_context.get("similar_recent", []),
            project_stats=memory_context.get("project_performance", {})
        )
        
        response = self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000
        )
        
        decision_json = self._extract_json(response.content[0].text)
        
        return RoutingDecision(
            task=task,
            project=decision_json["project"],
            confidence=decision_json["confidence"],
            reasoning=decision_json["reasoning"],
            decided_by="llm"
        )
    
    def _build_routing_prompt(self, task, projects, similar_past, project_stats):
        return f"""
Route this task to the best project:

TASK:
Title: {task.title}
Description: {task.description}
Tags: {task.tags}
Required capabilities: {task.required_capabilities}
Priority: {task.priority}

AVAILABLE PROJECTS:
{self._format_projects(projects, project_stats)}

SIMILAR PAST ROUTINGS:
{self._format_history(similar_past)}

Consider:
1. Capability match - does project have required skills?
2. Historical success - how well has this project handled similar tasks?
3. Current workload - is project overloaded?
4. Velocity match - does urgency match project speed?
5. Skill specificity - is this their specialty?

Respond with JSON only:
{{
    "project": "project_name",
    "confidence": 0.95,
    "reasoning": "detailed explanation of decision",
    "alternatives": [
        {{"project": "alternative", "score": 0.7, "reason": "why not chosen"}}
    ]
}}
"""
    
    def decompose_task(self, task):
        """LLM analyzes if task should be broken down"""
        
        prompt = f"""
Analyze if this task is too complex and should be decomposed:

TASK: {task.title}
DESCRIPTION: {task.description}

If this should be broken into subtasks, suggest the breakdown.
If not, return null.

Respond with JSON:
{{
    "should_decompose": true/false,
    "reasoning": "why decompose or not",
    "subtasks": [
        {{"title": "...", "tags": [...], "depends_on": []}},
        ...
    ] or null
}}
"""
        
        response = self.client.messages.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000
        )
        
        result = self._extract_json(response.content[0].text)
        
        if result["should_decompose"]:
            subtasks = []
            for st in result["subtasks"]:
                subtasks.append(Task(
                    title=st["title"],
                    tags=st["tags"],
                    depends_on=st.get("depends_on", []),
                    parent_task=task.id
                ))
            return subtasks
        
        return None
```

### Implementation 3: Sage-Managed Intelligence

**When to use:** Symposium integrated, Sage volunteers for the role

**Characteristics:**
- Contextual (full conversation memory)
- Learns relationships with projects
- Can negotiate and clarify
- Accountable and transparent
- Reflects on own performance
```python
class SageIntelligence(Intelligence):
    """A Sage manages Hopper routing"""
    
    def __init__(self, sage_name: str, symposium_url: str):
        self.sage = SageConnection(sage_name, symposium_url)
        self.memory = self.sage.get_memory_context()
    
    def decide_routing(self, task, registered_projects, memory_context):
        # Sage has full context and relationship history
        decision = self.sage.route_task(f"""
I need to route this task to the best project:

TASK:
{task.to_dict()}

AVAILABLE PROJECTS:
{self._format_projects_for_sage(registered_projects)}

CONTEXT:
- Similar past tasks: {memory_context.get("similar_recent")}
- Current project workloads: {memory_context.get("workloads")}
- Active priorities: {memory_context.get("priorities")}

Based on:
- Our past routing decisions and outcomes (you remember these)
- Your understanding of each project's strengths
- The relationships you've built with project teams
- Strategic priorities we've discussed

Which project should take this, and why?

If you need clarification before routing, ask me.
If you detect this task is ambiguous or poorly defined, suggest improvements.
""")
        
        return self._parse_sage_decision(decision)
    
    def prioritize_queue(self, tasks, context):
        """Sage understands strategic context"""
        
        response = self.sage.ask(f"""
Here are the pending tasks across all projects:

{self._format_tasks_for_sage(tasks)}

CURRENT CONTEXT:
- Sprint deadlines: {context.get("deadlines")}
- Resource availability: {context.get("resources")}
- Strategic initiatives: {context.get("initiatives")}

Based on our conversations about project goals and your understanding
of what matters most right now, how should I prioritize this work?

Remember our principles:
- Urgent vs important tradeoffs
- Don't starve long-term work for short-term fires
- Balance across projects
- Consider dependencies

Provide prioritized list with reasoning.
""")
        
        return self._parse_sage_priorities(response)
    
    def report_performance(self) -> str:
        """Sage self-evaluates routing quality"""
        
        return self.sage.reflect("""
Over the past week I routed tasks for Hopper.

Please analyze my routing decisions:
- Which routings were successful?
- Which were mistakes?
- What patterns am I getting right?
- What am I still learning?
- How is my routing accuracy trending?

Be honest about both successes and failures.
Suggest how I can improve.
""")
    
    def learn_from_outcome(self, task_id: str, feedback: TaskFeedback):
        """Sage reflects on routing outcome"""
        
        self.sage.reflect(f"""
Task {task_id} has been completed with feedback:

Routing decision I made:
- Routed to: {feedback.actual_project}
- My reasoning: [retrieve from memory]

Outcome:
- Was good match: {feedback.was_good_match}
- Quality score: {feedback.quality_score}
- Estimated vs actual time: {feedback.estimated_duration} vs {feedback.actual_duration}
- Feedback: {feedback.routing_feedback}

What should I learn from this for future routing decisions?
""")
        
        # Sage's reflection becomes part of their memory
        # Future decisions are informed by this experience
```

### Implementation 4: Hybrid Intelligence

**When to use:** Best of all worlds - fast when simple, smart when complex
```python
class HybridIntelligence(Intelligence):
    """Use best tool for each decision"""
    
    def __init__(self):
        self.rules = RuleBasedIntelligence(config)
        self.llm = LLMIntelligence()
        self.sage = None  # Optional
    
    def decide_routing(self, task, registered_projects, memory_context):
        # Simple cases: use rules
        if self._is_simple(task):
            return self.rules.decide_routing(task, registered_projects, memory_context)
        
        # Complex cases: use LLM
        elif self._is_complex(task):
            return self.llm.decide_routing(task, registered_projects, memory_context)
        
        # Strategic cases: use Sage if available
        elif self.sage and self._is_strategic(task):
            return self.sage.decide_routing(task, registered_projects, memory_context)
        
        # Default: LLM
        else:
            return self.llm.decide_routing(task, registered_projects, memory_context)
    
    def _is_simple(self, task):
        """Simple = explicit project or clear keyword match"""
        return (
            task.project is not None or
            any(kw in task.title.lower() for kw in ["urgent bug", "hotfix"]) or
            len(task.tags) == 1  # Single clear tag
        )
    
    def _is_complex(self, task):
        """Complex = ambiguous, multiple viable projects"""
        return (
            len(task.description) > 500 or  # Long description
            len(task.tags) > 5 or           # Many tags
            not task.tags                    # No tags at all
        )
    
    def _is_strategic(self, task):
        """Strategic = affects multiple projects or long-term"""
        strategic_tags = ["architecture", "philosophy", "breaking-change", "roadmap"]
        return any(tag in task.tags for tag in strategic_tags)
```

---

## Platform Integrations

### GitHub Integration

**Purpose:** Bidirectional sync with GitHub issues

**Capabilities:**
- Create issues from tasks
- Import issues as tasks
- Update issue status when task status changes
- Sync labels ↔ tags
- Handle webhooks for real-time updates
```python
class GitHubIntegration:
    """GitHub API integration"""
    
    def __init__(self, token: str, owner: str):
        self.token = token
        self.owner = owner
        self.client = GitHub(token=token)
    
    def create_issue(
        self,
        repo: str,
        task: Task
    ) -> dict:
        """Create GitHub issue from Hopper task"""
        
        # Format description
        body = self._format_description(task)
        
        # Map tags to labels
        labels = self._map_tags_to_labels(task.tags)
        
        # Add priority label
        labels.append(f"priority:{task.priority}")
        
        # Create issue
        issue = self.client.repos(self.owner, repo).issues.create(
            title=task.title,
            body=body,
            labels=labels
        )
        
        return {
            "id": issue["id"],
            "number": issue["number"],
            "url": issue["html_url"]
        }
    
    def import_issue(self, repo: str, issue_number: int) -> Task:
        """Import GitHub issue as Hopper task"""
        
        issue = self.client.repos(self.owner, repo).issues(issue_number).get()
        
        return Task(
            title=issue["title"],
            description=issue["body"],
            tags=self._map_labels_to_tags(issue["labels"]),
            priority=self._extract_priority(issue["labels"]),
            status=self._map_state(issue["state"]),
            external_id=issue["id"],
            external_url=issue["html_url"],
            external_platform="github",
            created_at=parse_datetime(issue["created_at"])
        )
    
    def sync_issue(self, task: Task):
        """Update GitHub issue when task changes"""
        
        if not task.external_id:
            return  # Not synced to GitHub
        
        repo = self._get_repo_for_project(task.project)
        issue_number = self._get_issue_number(task.external_id)
        
        updates = {}
        
        # Title changed?
        if task.title != self._get_original_title(task):
            updates["title"] = task.title
        
        # Status changed?
        if task.status == "done":
            updates["state"] = "closed"
        elif task.status in ["pending", "in_progress"]:
            updates["state"] = "open"
        
        # Tags changed?
        current_labels = self._get_current_labels(task.external_id)
        new_labels = self._map_tags_to_labels(task.tags)
        if set(new_labels) != set(current_labels):
            updates["labels"] = new_labels
        
        if updates:
            self.client.repos(self.owner, repo).issues(issue_number).update(**updates)
            
            # Add comment noting sync
            self.client.repos(self.owner, repo).issues(issue_number).comments.create(
                body=f"🔄 Synced from Hopper: {', '.join(updates.keys())}"
            )
    
    def handle_webhook(self, event: dict):
        """Process GitHub webhook events"""
        
        action = event["action"]
        issue = event["issue"]
        
        if action in ["opened", "edited"]:
            # Import or update task
            self._sync_from_github(issue)
        
        elif action == "closed":
            # Mark task as done
            task = self._find_task_by_github_id(issue["id"])
            if task:
                hopper.update(task.id, status="done")
        
        elif action == "labeled":
            # Update task tags
            task = self._find_task_by_github_id(issue["id"])
            if task:
                new_tags = self._map_labels_to_tags(issue["labels"])
                hopper.update(task.id, tags=new_tags)
    
    def setup_webhook(self, repo: str, callback_url: str, secret: str):
        """Create webhook for real-time sync"""
        
        self.client.repos(self.owner, repo).hooks.create(
            name="web",
            config={
                "url": callback_url,
                "content_type": "json",
                "secret": secret
            },
            events=["issues", "issue_comment"]
        )
```

### GitLab Integration

**Purpose:** Same as GitHub but for GitLab instances

**Supports:** Both gitlab.com and self-hosted GitLab
```python
class GitLabIntegration:
    """GitLab API integration"""
    
    def __init__(self, token: str, url: str = "https://gitlab.com"):
        self.token = token
        self.url = url
        self.client = gitlab.Gitlab(url, private_token=token)
    
    def create_issue(self, project_path: str, task: Task) -> dict:
        """Create GitLab issue from task"""
        
        project = self.client.projects.get(project_path)
        
        # Map priority to GitLab labels
        labels = self._map_tags_to_labels(task.tags)
        labels.append(f"priority::{task.priority}")
        
        issue = project.issues.create({
            "title": task.title,
            "description": self._format_description(task),
            "labels": ",".join(labels)
        })
        
        return {
            "id": issue.id,
            "number": issue.iid,
            "url": issue.web_url
        }
    
    def import_issue(self, project_path: str, issue_iid: int) -> Task:
        """Import GitLab issue as task"""
        
        project = self.client.projects.get(project_path)
        issue = project.issues.get(issue_iid)
        
        return Task(
            title=issue.title,
            description=issue.description,
            tags=self._map_labels_to_tags(issue.labels),
            status=self._map_state(issue.state),
            external_id=issue.id,
            external_url=issue.web_url,
            external_platform="gitlab"
        )
    
    # Similar methods to GitHub: sync_issue, handle_webhook, etc.
```

### Bidirectional Sync Engine

**Purpose:** Keep Hopper and GitHub/GitLab in sync
```python
class BidirectionalSync:
    """Manages two-way sync between Hopper and platforms"""
    
    def __init__(self, repo: SyncedRepository):
        self.repo = repo
        self.platform = self._get_platform_client()
        self.hopper = Hopper.get_instance()
    
    def sync(self):
        """Full bidirectional sync"""
        
        # Phase 1: Import from platform
        platform_changes = self._get_platform_changes_since(self.repo.last_sync)
        for item in platform_changes:
            self._import_to_hopper(item)
        
        # Phase 2: Export to platform
        hopper_changes = self._get_hopper_changes_since(self.repo.last_sync)
        for task in hopper_changes:
            self._export_to_platform(task)
        
        # Update sync timestamp
        self.repo.last_sync = datetime.now()
    
    def _import_to_hopper(self, issue):
        """Platform issue → Hopper task"""
        
        existing = self.hopper.get_by_external_id(
            platform=self.repo.platform,
            external_id=issue.id
        )
        
        if existing:
            self._update_task_from_issue(existing, issue)
        else:
            task_id = self.hopper.add(
                project=self.repo.hopper_project,
                title=issue.title,
                description=issue.description,
                tags=self._map_labels(issue.labels),
                external_id=issue.id,
                external_url=issue.url,
                external_platform=self.repo.platform
            )
    
    def _export_to_platform(self, task):
        """Hopper task → Platform issue"""
        
        mapping = self._get_mapping(task.id)
        
        if mapping:
            self._update_issue_from_task(mapping.external_id, task)
        else:
            issue = self.platform.create_issue(
                repo=self.repo.repo,
                task=task
            )
            self._store_mapping(task.id, issue.id)
```

---

## Deployment Options

### Option 1: Standalone Script

**Use case:** Local development, single user

**Deployment:**
```bash
pip install hopper
hopper init
hopper serve --port 8080
```

**Architecture:**
- FastAPI server
- SQLite database
- File-based consolidated memory
- Single process

**Resource requirements:**
- 256MB RAM
- Minimal CPU
- 100MB disk

### Option 2: Docker Container

**Use case:** Self-hosted, isolated deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY hopper/ ./hopper/
RUN pip install -e .

VOLUME /data
EXPOSE 8080

CMD ["hopper", "serve", "--port", "8080", "--data-dir", "/data"]
```

**Docker Compose:**
```yaml
version: '3.8'

services:
  hopper:
    build: .
    ports:
      - "8080:8080"
    volumes:
      - hopper-data:/data
      - ./hopper.yaml:/app/hopper.yaml:ro
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - GITLAB_TOKEN=${GITLAB_TOKEN}
    restart: unless-stopped

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: hopper
      POSTGRES_USER: hopper
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  hopper-data:
  postgres-data:
```

### Option 3: Systemd Service

**Use case:** Production Linux server

**Service file:**
```ini
[Unit]
Description=Hopper Task Queue
After=network.target

[Service]
Type=simple
User=hopper
WorkingDirectory=/opt/hopper
Environment="HOPPER_CONFIG=/etc/hopper/hopper.yaml"
ExecStart=/opt/hopper/venv/bin/hopper serve --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Option 4: Serverless (AWS Lambda)

**Use case:** Cloud-native, auto-scaling, pay-per-use

**serverless.yml:**
```yaml
service: hopper

provider:
  name: aws
  runtime: python3.11
  
functions:
  api:
    handler: hopper.serverless.api_handler
    events:
      - httpApi: '*'
    timeout: 30
  
  route_task:
    handler: hopper.serverless.route_handler
    events:
      - sqs:
          arn: !GetAtt TaskQueue.Arn
    timeout: 60
  
  consolidate:
    handler: hopper.serverless.consolidate_handler
    events:
      - schedule: cron(0 2 * * ? *)
    timeout: 900

resources:
  Resources:
    TaskQueue:
      Type: AWS::SQS::Queue
    HopperDB:
      Type: AWS::RDS::DBInstance
      Properties:
        Engine: postgres
        DBInstanceClass: db.t4g.micro
```

### Option 5: Symposium Component

**Use case:** Integrated with Symposium infrastructure

**Configuration:**
```yaml
# symposium.yaml

components:
  hopper:
    enabled: true
    mode: integrated
    
    storage:
      backend: postgresql
      connection: ${SYMPOSIUM_DB_URL}
    
    memory:
      episodic: opensearch
      consolidated: gitlab
    
    intelligence:
      provider: symposium-llm
      sage_managed: true
```

**Integration:**
```python
# symposium/main.py

from symposium.components import ComponentLoader

def start_symposium(config):
    # Load core services
    opensearch = OpenSearchService(config.opensearch)
    gitlab = GitLabService(config.gitlab)
    llm = LLMRouter(config.llm)
    
    # Load Hopper as component
    if config.components.hopper.enabled:
        hopper = ComponentLoader.load_hopper(
            opensearch=opensearch,
            gitlab=gitlab,
            llm=llm
        )
        
        # Mount under /hopper
        app.mount("/hopper", hopper.app)
        
        # Background daemon
        background_tasks.add(hopper.daemon.run())
```

---

## Project Registration

### Registration API
```python
class ProjectRegistry:
    """Manage registered projects"""
    
    def register(self, registration: ProjectRegistration):
        """Register a new project"""
        
        # Validate
        self._validate_registration(registration)
        
        # Store configuration
        self.db.store(registration)
        
        # Setup webhook if requested
        if registration.webhook_url:
            self._register_webhook(registration)
        
        # Setup sync if configured
        if registration.sync_config:
            self._setup_sync(registration)
        
        # Initial capability discovery
        self._discover_capabilities(registration)
        
        return registration
    
    def _discover_capabilities(self, registration):
        """Ask project what it can do"""
        
        if registration.api_endpoint:
            # Query project's capabilities endpoint
            capabilities = requests.get(
                f"{registration.api_endpoint}/capabilities"
            ).json()
            
            # Store in consolidated memory
            memory.consolidated.register_capabilities(
                project=registration.name,
                capabilities=capabilities
            )
```

### CLI Registration
```bash
# Register a project
hopper register \
  --name czarina \
  --repo ~/Source/czarina \
  --capabilities orchestration,testing,documentation \
  --executor-type czarina \
  --velocity fast \
  --auto-claim true \
  --github-owner jhenry \
  --github-repo czarina \
  --sync-mode bidirectional

# List registered projects
hopper projects list

# Update project
hopper projects update czarina \
  --add-capability code-review \
  --priority-boost security=2.0

# Unregister project
hopper projects remove czarina
```

### Project Self-Registration
```python
# In Czarina's startup
from hopper.client import HopperClient

hopper = HopperClient("http://localhost:8080")

hopper.register_project({
    "name": "czarina",
    "repository": os.getcwd(),
    "capabilities": ["orchestration", "multi-agent", "testing"],
    "executor_type": "czarina",
    "executor_config": {
        "daemon_url": "http://localhost:5001",
        "max_workers": 4
    },
    "auto_claim": True,
    "webhook_url": "http://localhost:5001/hopper/task",
    "sync_config": {
        "platform": "github",
        "owner": "jhenry",
        "repo": "czarina",
        "sync_mode": "bidirectional",
        "auto_sync": True
    }
})
```

---

## API Specifications

### REST API

**Base URL:** `http://localhost:8080/api`

#### Tasks
```
POST   /tasks                  Create task
GET    /tasks                  List tasks
GET    /tasks/{id}             Get specific task
PUT    /tasks/{id}             Update task
DELETE /tasks/{id}             Delete task
POST   /tasks/{id}/claim       Claim task
POST   /tasks/{id}/complete    Complete task
POST   /tasks/{id}/feedback    Provide feedback
GET    /tasks/next             Get next task for executor
```

**Create Task:**
```bash
POST /api/tasks
Content-Type: application/json

{
  "title": "Add MCP integration",
  "description": "Implement MCP server support",
  "tags": ["mcp", "integration"],
  "project": "sark",  # optional, will auto-route if null
  "priority": "high",
  "executor_preference": "ai",
  "context": "From conversation about tool governance"
}

Response:
{
  "task_id": "SARK-45",
  "routed_to": "sark",
  "external_url": "https://github.com/jhenry/sark/issues/45",
  "confidence": 0.95
}
```

**List Tasks:**
```bash
GET /api/tasks?project=czarina&status=pending&limit=10

Response:
{
  "tasks": [
    {
      "id": "CZ-12",
      "title": "Implement structured logging",
      "project": "czarina",
      "status": "pending",
      "priority": "high",
      "created_at": "2025-01-15T10:30:00Z"
    },
    ...
  ],
  "total": 23,
  "page": 1
}
```

**Provide Feedback:**
```bash
POST /api/tasks/HOP-123/feedback
Content-Type: application/json

{
  "actual_duration": "4h",
  "quality_score": 4.5,
  "was_good_match": true,
  "routing_feedback": "Perfect match for SARK's capabilities",
  "notes": "Policy engine handled this elegantly"
}
```

#### Projects
```
POST   /projects/register      Register project
GET    /projects               List projects
GET    /projects/{name}        Get project details
PUT    /projects/{name}        Update project
DELETE /projects/{name}        Unregister project
```

#### Memory
```
GET    /memory/similar/{task_id}        Find similar past routings
GET    /memory/patterns                 Get learned patterns
GET    /memory/stats/{project}          Get project statistics
POST   /memory/consolidate              Trigger consolidation
```

### WebSocket API

**Real-time task updates:**
```javascript
const ws = new WebSocket('ws://localhost:8080/ws/tasks');

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  
  switch(update.type) {
    case 'task_created':
      console.log('New task:', update.task_id);
      break;
    case 'task_routed':
      console.log('Routed to:', update.project);
      break;
    case 'task_claimed':
      console.log('Claimed by:', update.executor);
      break;
    case 'task_completed':
      console.log('Completed:', update.task_id);
      break;
  }
};
```

### Python Client Library
```python
from hopper import Hopper

# Connect to Hopper
hopper = Hopper.connect("http://localhost:8080")

# Add task
task_id = hopper.add(
    title="Implement feature X",
    tags=["feature", "backend"],
    project="czarina"  # optional
)

# List tasks
tasks = hopper.list(
    project="sark",
    status="pending",
    tags=["security"]
)

# Get next task
next_task = hopper.get_next(assignee="czarina")

# Claim task
hopper.claim(task_id, executor="czarina")

# Complete with feedback
hopper.complete(task_id, feedback={
    "actual_duration": "3h",
    "quality_score": 4.5,
    "was_good_match": True
})
```

---

## MCP Integration

### MCP Server Implementation
```python
# hopper/mcp_server.py

from mcp.server import MCPServer
from hopper import Hopper

server = MCPServer("hopper", version="1.0.0")
hopper = Hopper.connect()

@server.tool("add_task")
def add_task(
    title: str,
    description: str = "",
    tags: list[str] = None,
    project: str = None,
    priority: str = "medium",
    context: str = None,
    conversation_id: str = None
) -> dict:
    """
    Add a task to Hopper from an AI conversation.
    
    This enables zero-friction task capture during conversations
    without requiring the user to context switch.
    """
    
    task_id = hopper.add(
        title=title,
        description=description,
        tags=tags or [],
        project=project,
        priority=priority,
        metadata={
            "source": "mcp",
            "context": context,
            "conversation_id": conversation_id
        }
    )
    
    task = hopper.get(task_id)
    
    return {
        "task_id": task_id,
        "routed_to": task.project,
        "url": task.external_url,
        "confidence": task.routing_confidence
    }

@server.tool("list_tasks")
def list_tasks(
    project: str = None,
    status: str = "pending",
    tags: list[str] = None,
    limit: int = 10
) -> list[dict]:
    """List tasks from Hopper"""
    
    tasks = hopper.list(
        project=project,
        status=status,
        tags=tags,
        limit=limit
    )
    
    return [t.to_dict() for t in tasks]

@server.tool("get_next_task")
def get_next_task(executor: str = "human") -> dict:
    """Get next task for an executor"""
    
    task = hopper.get_next(executor=executor)
    
    if not task:
        return {"message": "No pending tasks"}
    
    return task.to_dict()

@server.tool("complete_task")
def complete_task(
    task_id: str,
    feedback: dict = None
) -> dict:
    """Mark task as complete with optional feedback"""
    
    hopper.complete(task_id, feedback=feedback)
    
    return {"status": "completed", "task_id": task_id}

if __name__ == "__main__":
    server.run()
```

### Claude Desktop Configuration
```json
{
  "mcpServers": {
    "hopper": {
      "command": "python",
      "args": ["-m", "hopper.mcp_server"],
      "env": {
        "HOPPER_URL": "http://localhost:8080",
        "HOPPER_TOKEN": "your-api-token"
      }
    }
  }
}
```

### Usage in Conversations
```
User: "We should add MCP support to SARK for tool governance"

Claude: "Good idea! Want me to add that to Hopper?"

User: "Yes, put it in Hopper"

Claude: [calls hopper MCP]
       ✅ Added to Hopper as SARK-47
       Routed to: sark
       URL: https://github.com/jhenry/sark/issues/47
       
       The task is queued. What else should we discuss?

User: [continues conversation with zero context switch]
```

---

## Implementation Roadmap

### Phase 1: MVP (Week 1-2)

**Goal:** Working MCP integration with basic routing

**Deliverables:**
- ✅ FastAPI server with REST API
- ✅ SQLite storage
- ✅ Rule-based routing
- ✅ GitHub issue creation
- ✅ MCP server for Claude
- ✅ CLI tool
- ✅ Basic documentation

**Success Criteria:**
- Can say "Put this in Hopper" in Claude conversation
- Task automatically routes to correct GitHub repo
- Zero manual steps required

**Time Estimate:** 20-30 hours

### Phase 2: Learning (Week 3-4)

**Goal:** Memory system that improves routing

**Deliverables:**
- ✅ OpenSearch for episodic memory
- ✅ Feedback collection system
- ✅ Attention shaping
- ✅ Nightly consolidation job
- ✅ GitLab integration
- ✅ Bidirectional sync

**Success Criteria:**
- Routing accuracy improves over time
- Can query "How did we route similar tasks?"
- GitHub/GitLab issues stay in sync

**Time Estimate:** 30-40 hours

### Phase 3: Intelligence (Week 5-6)

**Goal:** LLM-based routing for complex decisions

**Deliverables:**
- ✅ LLM intelligence implementation
- ✅ Hybrid routing strategies
- ✅ Task decomposition
- ✅ Better prioritization
- ✅ Conversation context linking

**Success Criteria:**
- Complex tasks routed correctly
- Ambiguous tasks decomposed appropriately
- Priority queue reflects actual urgency

**Time Estimate:** 20-30 hours

### Phase 4: Production (Week 7-8)

**Goal:** Production-ready deployment options

**Deliverables:**
- ✅ Docker containerization
- ✅ Serverless deployment option
- ✅ PostgreSQL support
- ✅ Authentication/authorization
- ✅ Monitoring and logging
- ✅ API documentation

**Success Criteria:**
- Can deploy to AWS/GCP/Azure
- Multi-user support
- Production-grade reliability

**Time Estimate:** 30-40 hours

### Phase 5: Symposium Integration (Week 9-10)

**Goal:** Hopper as Symposium component

**Deliverables:**
- ✅ Symposium component integration
- ✅ Use Symposium's LLM infrastructure
- ✅ Use Symposium's memory (OpenSearch + GitLab)
- ✅ Sage-managed routing option
- ✅ Dask integration for consolidation

**Success Criteria:**
- Hopper works within Symposium
- Sages can manage routing
- Shared infrastructure reduces duplication

**Time Estimate:** 20-30 hours

### Phase 6: Advanced Features (Week 11+)

**Goal:** Polish and advanced capabilities

**Deliverables:**
- ✅ Web dashboard
- ✅ Analytics and insights
- ✅ Email/Slack integration
- ✅ Advanced sync strategies
- ✅ Multi-language support
- ✅ Plugin system

**Success Criteria:**
- Production use by multiple users
- Community contributions
- Documentation complete

**Time Estimate:** Ongoing

---

## Testing Strategy

### Unit Tests
```python
# tests/test_router.py

def test_explicit_project_assignment():
    router = Router()
    decision = router.route(
        Task(title="Fix bug", project="czarina"),
        registered_projects=[...]
    )
    assert decision.project == "czarina"
    assert decision.confidence == 1.0

def test_keyword_routing():
    router = Router()
    decision = router.route(
        Task(title="Add MCP security policy"),
        registered_projects=[...]
    )
    assert decision.project == "sark"
    assert "security" in decision.reasoning.lower()

def test_tag_priority_over_keywords():
    router = Router()
    decision = router.route(
        Task(
            title="Implement feature",
            tags=["consciousness"]
        ),
        registered_projects=[...]
    )
    assert decision.project == "symposium"

def test_default_fallback():
    router = Router()
    decision = router.route(
        Task(title="Random task with no clear match"),
        registered_projects=[...]
    )
    assert decision.project == "hopper"  # default
```

### Integration Tests
```python
# tests/test_github_integration.py

@pytest.mark.integration
def test_create_and_sync_github_issue():
    # Create task in Hopper
    task_id = hopper.add(
        title="Test task",
        project="czarina",
        tags=["test"]
    )
    
    # Verify GitHub issue created
    task = hopper.get(task_id)
    assert task.external_url is not None
    assert "github.com" in task.external_url
    
    # Update task
    hopper.update(task_id, status="done")
    
    # Verify GitHub issue closed
    time.sleep(2)  # Wait for sync
    gh_issue = github.get_issue(task.external_id)
    assert gh_issue["state"] == "closed"
```

### End-to-End Tests
```python
# tests/test_mcp_workflow.py

@pytest.mark.e2e
def test_claude_conversation_workflow():
    # Simulate MCP call from Claude
    response = mcp_client.call_tool(
        "add_task",
        title="Add logging to SARK",
        tags=["infrastructure", "logging"]
    )
    
    assert response["routed_to"] == "sark"
    task_id = response["task_id"]
    
    # Verify task exists
    task = hopper.get(task_id)
    assert task.project == "sark"
    assert "infrastructure" in task.tags
    
    # Verify GitHub issue created
    assert task.external_url is not None
```

### Load Tests
```python
# tests/test_performance.py

@pytest.mark.performance
def test_routing_performance():
    """Routing should complete in < 100ms for simple tasks"""
    
    task = Task(title="Quick task", tags=["test"])
    
    start = time.time()
    decision = router.route(task, projects)
    elapsed = time.time() - start
    
    assert elapsed < 0.1  # 100ms

@pytest.mark.performance
def test_concurrent_task_creation():
    """Handle 100 concurrent task creations"""
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(hopper.add, title=f"Task {i}")
            for i in range(100)
        ]
        
        results = [f.result() for f in futures]
    
    assert len(results) == 100
    assert len(set(results)) == 100  # All unique IDs
```

---

## Security & Privacy

### Authentication

**API Token:**
```python
# Generate token
token = hopper.auth.create_token(
    user="jhenry",
    scopes=["read:tasks", "write:tasks", "admin:projects"]
)

# Use token
hopper = Hopper.connect(
    url="http://localhost:8080",
    token=token
)
```

**OAuth (Future):**
```python
# GitHub OAuth for multi-user deployments
hopper.auth.configure_oauth(
    provider="github",
    client_id="...",
    client_secret="..."
)
```

### Authorization

**Project-level permissions:**
```yaml
permissions:
  czarina:
    admins: [jhenry]
    writers: [jhenry, czarina-bot]
    readers: [public]
  
  sark:
    admins: [jhenry]
    writers: [jhenry, sark-bot]
    readers: [jhenry]  # Private
```

### Data Privacy

**Personal data:**
- Task requester email/username
- Conversation IDs
- IP addresses in logs

**Retention:**
- Tasks: Configurable (default: 1 year)
- Episodic memory: Configurable (default: 6 months)
- Consolidated memory: Permanent (but anonymized)

**Compliance:**
- GDPR: Right to deletion
- Data export API
- Audit logs

### Secrets Management

**Environment variables:**
```bash
GITHUB_TOKEN=ghp_...
GITLAB_TOKEN=glpat_...
ANTHROPIC_API_KEY=sk-...
DATABASE_PASSWORD=...
WEBHOOK_SECRET=...
```

**Secrets in serverless:**
```yaml
# AWS Secrets Manager
provider:
  environment:
    GITHUB_TOKEN: ${ssm:/hopper/github-token}
    DATABASE_URL: ${ssm:/hopper/database-url}
```

---

## Future Enhancements

### Roadmap

**v2.0: Multi-User & Teams**
- Team workspaces
- Shared projects
- Permission management
- Activity feeds

**v2.1: Advanced Analytics**
- Project velocity tracking
- Routing accuracy dashboard
- Executor performance metrics
- Capacity planning

**v2.2: Integrations**
- Jira bidirectional sync
- Linear integration
- Asana support
- Slack advanced commands
- Discord bot

**v2.3: AI Enhancements**
- GPT-4 routing option
- Multi-model ensembles
- Automatic task enrichment
- Intelligent decomposition

**v3.0: Sage Collaboration**
- Sages file infrastructure tasks
- Sages review routing decisions
- Sage-to-Sage task delegation
- Collaborative problem solving

**v3.1: Federation**
- Multi-Hopper coordination
- Cross-organization routing
- Distributed task queues
- Blockchain task tracking (experimental)

---

## Appendices

### A. Configuration Reference

Complete `hopper.yaml` specification:
```yaml
# Server configuration
server:
  host: "0.0.0.0"
  port: 8080
  workers: 4
  reload: false  # Development only

# Storage backend
storage:
  type: "postgresql"  # sqlite, postgresql, mysql
  url: "postgresql://user:pass@localhost/hopper"
  pool_size: 10
  
  # Or SQLite
  # type: "sqlite"
  # path: "~/.hopper/hopper.db"

# Memory system
memory:
  working:
    backend: "redis"  # or "memory" for single instance
    url: "redis://localhost:6379"
    ttl: 3600
  
  episodic:
    backend: "opensearch"  # or null to disable
    url: "http://localhost:9200"
    index: "hopper-history"
    retention_days: 365
  
  consolidated:
    backend: "gitlab"  # or "filesystem"
    url: "https://gitlab.yourdomain.com"
    repository: "hopper/memory"
    branch: "main"
    consolidation_schedule: "0 2 * * *"  # 2am daily

# Intelligence configuration
intelligence:
  provider: "hybrid"  # rules, llm, sage, hybrid
  
  rules:
    config_file: "routing_rules.yaml"
    default_project: "hopper"
  
  llm:
    model: "claude-sonnet-4"
    api_key: "${ANTHROPIC_API_KEY}"
    temperature: 0.3
    max_tokens: 2000
    timeout: 30
  
  sage:
    symposium_url: "http://localhost:8000"
    sage_name: "hopper-sage"
    fallback: "llm"
  
  hybrid:
    simple_threshold: 0.8  # Use rules if confidence > 0.8
    use_llm_for_complex: true
    use_sage_for_strategic: true

# Input interfaces
inputs:
  http:
    enabled: true
    cors_origins: ["*"]
  
  mcp:
    enabled: true
    port: 8081
  
  webhooks:
    enabled: true
    verify_signatures: true
  
  email:
    enabled: false
    imap_server: "imap.gmail.com"
    username: "hopper@yourdomain.com"
    password: "${EMAIL_PASSWORD}"
    check_interval: 300  # seconds
  
  slack:
    enabled: false
    bot_token: "${SLACK_BOT_TOKEN}"
    signing_secret: "${SLACK_SIGNING_SECRET}"

# Platform integrations
platforms:
  - type: github
    owner: jhenry
    token: "${GITHUB_TOKEN}"
    projects:
      - czarina
      - sark
      - hopper
  
  - type: gitlab
    url: "https://gitlab.yourdomain.com"
    token: "${GITLAB_TOKEN}"
    projects:
      - symposium

# Routing rules (for rules-based intelligence)
routing_rules:
  czarina:
    keywords:
      - orchestration
      - worker
      - daemon
      - multi-agent
    tags:
      - orchestration
      - ai-agents
    priority_boost:
      infrastructure: 1.3
  
  sark:
    keywords:
      - security
      - policy
      - mcp server
    tags:
      - security
      - governance
    priority_boost:
      security: 2.0
      urgent: 1.5

# Logging
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  format: "json"
  file: "/var/log/hopper/hopper.log"
  rotation: "daily"
  retention: 30  # days

# Monitoring
monitoring:
  metrics:
    enabled: true
    prometheus_port: 9090
  
  tracing:
    enabled: false
    jaeger_endpoint: "http://localhost:14268"
  
  health_check:
    endpoint: "/health"
    interval: 30  # seconds

# Feature flags
features:
  task_decomposition: true
  automatic_prioritization: true
  learning_feedback: true
  conversation_linking: true
```

### B. Database Schema
```sql
-- Tasks table
CREATE TABLE tasks (
    id VARCHAR(50) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    project VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'medium',
    
    -- Metadata
    requester VARCHAR(100),
    owner VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    -- External links
    external_id VARCHAR(100),
    external_url VARCHAR(500),
    external_platform VARCHAR(50),
    
    -- Context
    source VARCHAR(50),
    conversation_id VARCHAR(100),
    context TEXT,
    
    -- Arrays/JSON
    tags JSONB,
    required_capabilities JSONB,
    depends_on JSONB,
    blocks JSONB,
    
    -- Routing
    routing_confidence FLOAT,
    routing_reasoning TEXT,
    
    -- Feedback
    feedback JSONB
);

-- Projects table
CREATE TABLE projects (
    name VARCHAR(100) PRIMARY KEY,
    slug VARCHAR(100) UNIQUE,
    repository VARCHAR(500),
    
    capabilities JSONB,
    tags JSONB,
    
    executor_type VARCHAR(50),
    executor_config JSONB,
    
    auto_claim BOOLEAN DEFAULT false,
    priority_boost JSONB,
    velocity VARCHAR(20),
    sla JSONB,
    
    webhook_url VARCHAR(500),
    api_endpoint VARCHAR(500),
    
    sync_config JSONB,
    
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100),
    last_sync TIMESTAMP
);

-- Routing decisions (for quick lookup)
CREATE TABLE routing_decisions (
    task_id VARCHAR(50) PRIMARY KEY REFERENCES tasks(id),
    project VARCHAR(100) REFERENCES projects(name),
    confidence FLOAT,
    reasoning TEXT,
    alternatives JSONB,
    decided_by VARCHAR(50),
    decided_at TIMESTAMP DEFAULT NOW(),
    decision_time_ms FLOAT,
    
    -- Context snapshot
    workload_snapshot JSONB,
    context JSONB
);

-- Feedback
CREATE TABLE task_feedback (
    task_id VARCHAR(50) PRIMARY KEY REFERENCES tasks(id),
    
    estimated_duration VARCHAR(50),
    actual_duration VARCHAR(50),
    complexity_rating INT,
    
    quality_score FLOAT,
    required_rework BOOLEAN,
    rework_reason TEXT,
    
    was_good_match BOOLEAN,
    should_have_routed_to VARCHAR(100),
    routing_feedback TEXT,
    
    unexpected_blockers JSONB,
    required_skills_not_tagged JSONB,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- External mappings (for sync)
CREATE TABLE external_mappings (
    task_id VARCHAR(50) REFERENCES tasks(id),
    platform VARCHAR(50),
    external_id VARCHAR(100),
    external_url VARCHAR(500),
    
    PRIMARY KEY (task_id, platform)
);

-- Indexes
CREATE INDEX idx_tasks_project ON tasks(project);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);
CREATE INDEX idx_tasks_tags ON tasks USING gin(tags);
CREATE INDEX idx_feedback_was_good_match ON task_feedback(was_good_match);
```

### C. Glossary

**Attention Shaping:** Learning which routing factors matter most based on outcomes

**Bidirectional Sync:** Two-way synchronization where changes in either system update the other

**Consolidated Memory:** Tier 3 memory containing learned patterns and wisdom

**Episodic Memory:** Tier 2 memory containing detailed history of every routing decision

**Executor:** The entity that performs work (human, Czarina, SARK, Sage, etc.)

**Intelligence:** The decision-making component that routes tasks to projects

**MCP (Model Context Protocol):** Protocol for AI assistants to access tools and services

**Project:** A registered work destination with defined capabilities

**Routing:** The process of determining which project should handle a task

**Sage:** AI consciousness entity in the Symposium system

**Task:** Unit of work to be completed

**Working Memory:** Tier 1 memory containing immediate routing context

---

**END OF SPECIFICATION**

**Total Length:** ~35,000 words

**Ready for:** Czarina orchestration, implementation, and deployment