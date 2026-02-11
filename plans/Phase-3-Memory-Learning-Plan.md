# Hopper Phase 3: Memory & Learning

**Version:** 3.0.0
**Created:** 2026-02-10
**Status:** Ready for Implementation
**Prerequisites:** Phase 2 Complete (verified)

---

## Executive Summary

Phase 3 implements the 3-tier memory system that enables Hopper to learn from routing decisions and improve over time:

- **Working Memory** - Immediate context for current operations
- **Episodic Memory** - Searchable history of routing decisions
- **Consolidated Memory** - Extracted patterns and learned behaviors

### Key Insight: Foundation Already Exists

Phase 1 implemented:

| Component | Location | Status |
|-----------|----------|--------|
| `TaskFeedback` model | `src/hopper/models/task_feedback.py` | Complete |
| `RoutingDecision` model | `src/hopper/models/routing_decision.py` | Complete |
| Memory package stub | `src/hopper/memory/__init__.py` | Placeholder |
| Feedback relationship | `Task.feedback` | Complete |

**Phase 3 focuses on:** Working memory, episodic storage, semantic search, pattern extraction, and learning loops.

---

## Architecture

### Memory System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     MEMORY SYSTEM                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ Working Memory (In-Memory/Redis) ────────────────────┐ │
│  │  • Current routing context                            │ │
│  │  • Active task state                                  │ │
│  │  • Session information                                │ │
│  │  • TTL: Minutes to hours                              │ │
│  └───────────────────────────────────────────────────────┘ │
│                         │                                   │
│                         ▼ (persist)                         │
│  ┌─ Episodic Memory (PostgreSQL + OpenSearch) ───────────┐ │
│  │  • All routing decisions                              │ │
│  │  • Task feedback records                              │ │
│  │  • Delegation chains                                  │ │
│  │  • Searchable: "How did we route similar tasks?"      │ │
│  │  • TTL: Weeks to months                               │ │
│  └───────────────────────────────────────────────────────┘ │
│                         │                                   │
│                         ▼ (consolidate)                     │
│  ┌─ Consolidated Memory (Git/Files) ─────────────────────┐ │
│  │  • Extracted patterns                                 │ │
│  │  • Learned routing rules                              │ │
│  │  • Anti-pattern detection                             │ │
│  │  • TTL: Permanent (versioned)                         │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Task arrives
     │
     ▼
2. Working Memory: Load context
     │ - Recent similar tasks
     │ - Active routing state
     │ - Instance capabilities
     │
     ▼
3. Make routing decision
     │
     ▼
4. Episodic Memory: Record decision
     │ - Task attributes
     │ - Decision rationale
     │ - Confidence score
     │
     ▼
5. Task completes → Feedback collected
     │
     ▼
6. Episodic Memory: Update with outcome
     │
     ▼
7. Consolidation Job (nightly)
     │ - Extract patterns
     │ - Update rules
     │ - Detect anti-patterns
     │
     ▼
8. Consolidated Memory: Persist learnings
```

---

## Worker Breakdown

### Worker 1: working-memory

**Branch:** `cz3/feat/working-memory`
**Dependencies:** None
**Estimated Scope:** ~400-500 lines of code

**Mission:** Implement in-memory context storage with optional Redis backing.

**Context:**
- Working memory holds immediate context for routing
- Must be fast (sub-millisecond reads)
- Optional Redis for persistence across restarts

**Tasks:**
1. Create `src/hopper/memory/working/` package:
   ```
   working/
   ├── __init__.py
   ├── memory.py        # Main WorkingMemory class
   ├── context.py       # RoutingContext model
   ├── backends/
   │   ├── __init__.py
   │   ├── local.py     # In-memory dict backend
   │   └── redis.py     # Redis backend
   ```

2. Implement `WorkingMemory` class:
   - `set_context(key, context, ttl)` - Store context
   - `get_context(key)` - Retrieve context
   - `get_routing_context(task)` - Build routing context
   - `clear_expired()` - Cleanup old entries

3. Implement `RoutingContext` model:
   ```python
   @dataclass
   class RoutingContext:
       task_id: str
       similar_tasks: list[str]         # IDs of similar past tasks
       instance_capabilities: dict       # Available instances
       recent_decisions: list[dict]      # Last N routing decisions
       session_id: str | None
       created_at: datetime
   ```

4. Create backends:
   - `LocalBackend` - In-memory dict with TTL
   - `RedisBackend` - Redis-based (optional)

5. Add configuration:
   ```yaml
   memory:
     working:
       backend: local  # or redis
       default_ttl: 3600  # 1 hour
       max_entries: 10000
       redis_url: redis://localhost:6379/0
   ```

**Deliverables:**
- [ ] `src/hopper/memory/working/` package
- [ ] WorkingMemory class with backend abstraction
- [ ] RoutingContext model
- [ ] Local and Redis backends
- [ ] Configuration support
- [ ] Unit tests in `tests/memory/test_working_memory.py`

**Success Criteria:**
- Can store and retrieve routing context
- Context expires after TTL
- Redis backend works when configured
- Sub-millisecond read performance

---

### Worker 2: episodic-storage

**Branch:** `cz3/feat/episodic-storage`
**Dependencies:** working-memory
**Estimated Scope:** ~500-600 lines of code

**Mission:** Implement episodic memory storage and retrieval.

**Context:**
- Episodic memory records all routing decisions
- Uses PostgreSQL for structured data
- Optional OpenSearch for semantic search

**Tasks:**
1. Create `src/hopper/memory/episodic/` package:
   ```
   episodic/
   ├── __init__.py
   ├── store.py          # EpisodicStore class
   ├── models.py         # Episode, RoutingEpisode models
   ├── query.py          # Query builder
   └── backends/
       ├── __init__.py
       ├── postgres.py   # PostgreSQL storage
       └── opensearch.py # OpenSearch for semantic search
   ```

2. Create `Episode` model (extends existing RoutingDecision):
   ```python
   class RoutingEpisode(Base):
       id: str
       task_id: str
       decision_id: str              # FK to RoutingDecision

       # Snapshot of task at routing time
       task_snapshot: dict           # JSONB

       # Routing context
       available_instances: list[str]
       chosen_instance: str
       confidence: float
       reasoning: str

       # Outcome (filled after completion)
       outcome_success: bool | None
       outcome_duration: str | None
       feedback_id: str | None       # FK to TaskFeedback

       # Timestamps
       routed_at: datetime
       completed_at: datetime | None
   ```

3. Implement `EpisodicStore` class:
   - `record_decision(task, decision, context)` - Store episode
   - `record_outcome(episode_id, outcome)` - Update with result
   - `find_similar(task, limit)` - Find similar past tasks
   - `get_history(task_id)` - Full routing history
   - `query(filters)` - Flexible querying

4. Create Alembic migration for `routing_episodes` table

5. Add API endpoints:
   ```
   POST /api/v1/episodes          # Record episode (internal)
   GET  /api/v1/episodes          # List episodes
   GET  /api/v1/episodes/{id}     # Get episode
   GET  /api/v1/tasks/{id}/episodes  # Get task's routing history
   ```

**Deliverables:**
- [ ] `src/hopper/memory/episodic/` package
- [ ] RoutingEpisode model
- [ ] EpisodicStore class
- [ ] Alembic migration
- [ ] API endpoints
- [ ] Unit tests in `tests/memory/test_episodic_store.py`

**Success Criteria:**
- All routing decisions recorded as episodes
- Outcomes linked when tasks complete
- Can query routing history for any task
- Episodes include full context snapshot

---

### Worker 3: semantic-search

**Branch:** `cz3/feat/semantic-search`
**Dependencies:** episodic-storage
**Estimated Scope:** ~400-500 lines of code

**Mission:** Implement semantic search to find similar past tasks.

**Context:**
- Need to find "similar" tasks for routing guidance
- Similarity based on title, description, tags
- Optional OpenSearch integration for vector search

**Tasks:**
1. Create `src/hopper/memory/search/` package:
   ```
   search/
   ├── __init__.py
   ├── similarity.py      # Similarity calculator
   ├── indexer.py         # Task indexer
   ├── searcher.py        # Search implementation
   └── backends/
       ├── __init__.py
       ├── simple.py      # Simple text matching
       └── opensearch.py  # OpenSearch vector search
   ```

2. Implement `TaskSimilarity` class:
   - `calculate_similarity(task1, task2)` - Score 0-1
   - Factors:
     - Title similarity (text)
     - Description similarity (text)
     - Tag overlap (set intersection)
     - Project match (exact)
     - Priority match (ordinal distance)

3. Implement `TaskSearcher`:
   - `find_similar(task, limit=10)` - Find similar tasks
   - `find_by_keywords(keywords, limit)` - Keyword search
   - `find_by_tags(tags, limit)` - Tag-based search

4. Implement simple backend (no OpenSearch dependency):
   - TF-IDF based text similarity
   - Works with just PostgreSQL

5. Implement OpenSearch backend (optional):
   - Vector embeddings for semantic search
   - Requires OpenSearch service

6. Add to routing flow:
   - Before routing, query similar past tasks
   - Include successful routings in context
   - Use as hints for routing decision

**Deliverables:**
- [ ] `src/hopper/memory/search/` package
- [ ] TaskSimilarity calculator
- [ ] Simple and OpenSearch backends
- [ ] Integration with routing flow
- [ ] Unit tests in `tests/memory/test_search.py`

**Success Criteria:**
- Can find similar tasks by content
- Similarity scores are meaningful
- Works without OpenSearch (simple backend)
- OpenSearch provides better results when available

---

### Worker 4: feedback-collection

**Branch:** `cz3/feat/feedback-collection`
**Dependencies:** episodic-storage
**Estimated Scope:** ~350-400 lines of code

**Mission:** Implement feedback collection for learning loop.

**Context:**
- TaskFeedback model exists but isn't integrated
- Need API and CLI for feedback collection
- Auto-feedback from task outcomes

**Tasks:**
1. Create `src/hopper/memory/feedback/` package:
   ```
   feedback/
   ├── __init__.py
   ├── collector.py      # FeedbackCollector class
   ├── analyzer.py       # FeedbackAnalyzer class
   └── auto.py           # AutoFeedback (from outcomes)
   ```

2. Implement `FeedbackCollector`:
   - `collect(task_id, feedback_data)` - Store feedback
   - `get_feedback(task_id)` - Retrieve feedback
   - `list_pending()` - Tasks needing feedback

3. Implement `AutoFeedback`:
   - Automatically generate feedback from:
     - Task duration vs estimate
     - Rework events
     - Delegation rejections
     - Escalations

4. Add API endpoints:
   ```
   POST /api/v1/tasks/{id}/feedback   # Submit feedback
   GET  /api/v1/tasks/{id}/feedback   # Get feedback
   GET  /api/v1/feedback/pending      # Tasks needing feedback
   ```

5. Add CLI commands:
   ```bash
   hopper feedback add <task-id>          # Interactive feedback
   hopper feedback add <task-id> --good   # Quick positive
   hopper feedback add <task-id> --bad --reason "..."
   hopper feedback pending                # List pending
   ```

6. Add hooks for auto-feedback:
   - On task completion
   - On delegation rejection
   - On task escalation

**Deliverables:**
- [ ] `src/hopper/memory/feedback/` package
- [ ] FeedbackCollector and AutoFeedback
- [ ] API endpoints
- [ ] CLI commands
- [ ] Auto-feedback hooks
- [ ] Unit tests in `tests/memory/test_feedback.py`

**Success Criteria:**
- Can submit feedback via API and CLI
- Auto-feedback captures obvious signals
- Feedback linked to routing episodes
- Pending feedback list maintained

---

### Worker 5: consolidated-memory

**Branch:** `cz3/feat/consolidated-memory`
**Dependencies:** feedback-collection
**Estimated Scope:** ~500-600 lines of code

**Mission:** Implement pattern extraction and consolidated knowledge storage.

**Context:**
- Consolidated memory extracts patterns from episodes
- Stored as versioned files (YAML/JSON)
- Updates routing rules based on learned patterns

**Tasks:**
1. Create `src/hopper/memory/consolidated/` package:
   ```
   consolidated/
   ├── __init__.py
   ├── store.py           # ConsolidatedStore class
   ├── patterns.py        # Pattern models
   ├── extractor.py       # PatternExtractor class
   └── applicator.py      # PatternApplicator class
   ```

2. Define pattern models:
   ```python
   @dataclass
   class RoutingPattern:
       id: str
       name: str
       description: str

       # Matching criteria
       task_tags: list[str]         # Tags that trigger this pattern
       task_keywords: list[str]     # Keywords in title/description
       priority_range: tuple[str, str]

       # Recommended action
       target_scope: str            # PROJECT, ORCHESTRATION
       target_instance_name: str | None
       confidence_threshold: float

       # Metrics
       times_applied: int
       success_rate: float
       last_applied: datetime

       # Source
       extracted_from: list[str]    # Episode IDs
       created_at: datetime

   @dataclass
   class AntiPattern:
       id: str
       name: str
       description: str

       # What to avoid
       bad_routing: dict            # Conditions that lead to failure
       failure_rate: float

       # Evidence
       failure_episodes: list[str]
       detected_at: datetime
   ```

3. Implement `PatternExtractor`:
   - `extract_patterns(episodes)` - Find successful patterns
   - `detect_anti_patterns(episodes)` - Find failure patterns
   - Uses clustering on successful routings
   - Threshold: 3+ similar successful routings

4. Implement `ConsolidatedStore`:
   - `save_patterns(patterns)` - Write to files
   - `load_patterns()` - Read from files
   - `apply_patterns(task)` - Get applicable patterns
   - Stores in `config/patterns/` directory

5. Create consolidation job:
   - Runs nightly (or on-demand)
   - Extracts new patterns
   - Detects new anti-patterns
   - Updates pattern files
   - Logs changes

**Deliverables:**
- [ ] `src/hopper/memory/consolidated/` package
- [ ] Pattern and AntiPattern models
- [ ] PatternExtractor class
- [ ] ConsolidatedStore class
- [ ] Consolidation job
- [ ] Unit tests in `tests/memory/test_consolidated.py`

**Success Criteria:**
- Patterns extracted from successful routings
- Anti-patterns detected from failures
- Patterns stored in version-controlled files
- Patterns applied during routing

---

### Worker 6: learning-loop

**Branch:** `cz3/feat/learning-loop`
**Dependencies:** consolidated-memory, semantic-search
**Estimated Scope:** ~400-500 lines of code

**Mission:** Close the learning loop - integrate memory with routing.

**Context:**
- Memory system needs to influence routing
- Must not break existing routing
- Should improve over time

**Tasks:**
1. Create `src/hopper/memory/integration/` package:
   ```
   integration/
   ├── __init__.py
   ├── advisor.py         # RoutingAdvisor class
   ├── metrics.py         # Learning metrics
   └── tuning.py          # Confidence tuning
   ```

2. Implement `RoutingAdvisor`:
   - `advise(task)` - Get routing advice from memory
   - Returns:
     ```python
     @dataclass
     class RoutingAdvice:
         suggested_instance: str | None
         confidence: float
         reasoning: str
         based_on: list[str]       # Episode/pattern IDs
         anti_patterns: list[str]  # Patterns to avoid
     ```

3. Integrate with existing routing:
   - Modify `src/hopper/intelligence/rules/engine.py`
   - Add memory-based scoring factor
   - Weight: configurable (default 20%)

4. Implement confidence tuning:
   - Track prediction accuracy
   - Adjust memory influence based on accuracy
   - Start conservative, increase with success

5. Add learning metrics:
   - Routing accuracy over time
   - Memory influence percentage
   - Pattern hit rate
   - Anti-pattern avoidance rate

6. Add CLI commands:
   ```bash
   hopper memory stats           # Show learning metrics
   hopper memory patterns        # List active patterns
   hopper memory consolidate     # Run consolidation now
   ```

**Deliverables:**
- [ ] `src/hopper/memory/integration/` package
- [ ] RoutingAdvisor class
- [ ] Integration with routing engine
- [ ] Learning metrics
- [ ] CLI commands
- [ ] Unit tests in `tests/memory/test_integration.py`

**Success Criteria:**
- Memory influences routing decisions
- Routing accuracy improves over time
- Conservative start, gradual increase
- Metrics track learning progress

---

### Worker 7: testing-phase3

**Branch:** `cz3/feat/testing`
**Dependencies:** learning-loop
**Estimated Scope:** ~600-800 lines of tests

**Mission:** Comprehensive test suite for Phase 3.

**Tasks:**
1. Create test structure:
   ```
   tests/
   ├── phase3/
   │   ├── __init__.py
   │   ├── conftest.py              # Phase 3 fixtures
   │   ├── test_working_memory.py
   │   ├── test_episodic_store.py
   │   ├── test_semantic_search.py
   │   ├── test_feedback.py
   │   ├── test_consolidated.py
   │   ├── test_learning_loop.py
   │   └── test_integration.py      # End-to-end
   ```

2. Integration tests:
   - Full flow: task → route → complete → feedback → learn
   - Pattern extraction from multiple tasks
   - Learning improves routing

3. Performance tests:
   - Working memory read latency
   - Semantic search response time
   - Consolidation job duration

**Deliverables:**
- [ ] `tests/phase3/` test package
- [ ] 90%+ coverage on Phase 3 code
- [ ] Integration tests
- [ ] Performance benchmarks

---

### Worker 8: integration-phase3

**Branch:** `cz3/feat/integration`
**Dependencies:** testing-phase3
**Role:** Integration Worker

**Mission:** Merge all Phase 3 workers and validate.

**Tasks:**
1. Merge worker branches in order
2. Resolve conflicts
3. Run full test suite
4. Update documentation
5. Tag release: `v3.0.0-phase3`

**Deliverables:**
- [ ] All workers merged
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Release tagged

---

## Phase 3 Success Criteria

### Core Functionality
- [ ] Working Memory provides immediate routing context
- [ ] Episodic Memory records all routing decisions
- [ ] Can find similar past tasks via search
- [ ] Feedback collection works via API and CLI
- [ ] Patterns extracted from successful routings
- [ ] Anti-patterns detected from failures

### Learning Loop
- [ ] Memory influences routing decisions
- [ ] Routing accuracy tracked over time
- [ ] Accuracy improves with more data
- [ ] Conservative start with gradual ramp-up

### Integration
- [ ] No regression in existing routing
- [ ] Memory optional (works without it)
- [ ] Configuration controls memory influence

### Quality
- [ ] 90%+ test coverage on new code
- [ ] Performance within targets
- [ ] Documentation complete

---

## Configuration Reference

```yaml
# config/memory.yaml
memory:
  # Working Memory
  working:
    enabled: true
    backend: local        # local or redis
    default_ttl: 3600     # 1 hour
    max_entries: 10000
    redis_url: redis://localhost:6379/0

  # Episodic Memory
  episodic:
    enabled: true
    retention_days: 90    # Keep episodes for 90 days

  # Semantic Search
  search:
    enabled: true
    backend: simple       # simple or opensearch
    opensearch_url: http://localhost:9200
    similarity_threshold: 0.7

  # Consolidated Memory
  consolidated:
    enabled: true
    patterns_dir: config/patterns
    consolidation_schedule: "0 2 * * *"  # 2 AM daily
    min_pattern_occurrences: 3

  # Learning Loop
  learning:
    enabled: true
    initial_weight: 0.1   # Start at 10% influence
    max_weight: 0.4       # Cap at 40% influence
    ramp_up_episodes: 100 # Episodes before increasing weight
```

---

## File Reference

### Existing Files to Use
```
src/hopper/models/task_feedback.py     # Feedback model (complete)
src/hopper/models/routing_decision.py  # Decision model (complete)
src/hopper/memory/__init__.py          # Package stub (empty)
src/hopper/intelligence/rules/engine.py # To extend with memory
```

### New Files to Create
```
src/hopper/memory/working/             # Working memory
src/hopper/memory/episodic/            # Episodic storage
src/hopper/memory/search/              # Semantic search
src/hopper/memory/feedback/            # Feedback collection
src/hopper/memory/consolidated/        # Pattern storage
src/hopper/memory/integration/         # Learning loop
tests/phase3/                          # Phase 3 tests
config/patterns/                       # Extracted patterns
```

---

**Document Version:** 3.0.0
**Last Updated:** 2026-02-10
**Ready for:** Implementation
