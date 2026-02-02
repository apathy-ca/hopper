# Hopper Inbox

File drop zone for external task intake. Drop JSON files here for Hopper to ingest.

## File Format

```json
{
  "source": "czarina",
  "type": "learning",
  "project": "project-name",
  "phase": "1",
  "version": "0.7.0",
  "title": "Pattern: All workers contributed",
  "description": "All workers made commits - good task distribution",
  "priority": "medium",
  "tags": ["learning", "northbound", "orchestration"],
  "context": {
    "pattern_id": "ww-all-contributed",
    "type": "what_worked",
    "evidence": "6/6 workers committed",
    "confidence": "high",
    "generalizable": true
  },
  "suggested_destination": "agent-knowledge",
  "created_at": "2026-02-02T10:30:00Z"
}
```

## File Naming

- `czarina-<project>-phase-<N>-<pattern-id>.json`
- Example: `czarina-myproject-phase-1-ww-all-contributed.json`

## Processing

Hopper's inbox watcher (when implemented) will:
1. Read files from this directory
2. Validate and create Task entries
3. Route through intelligence layer
4. Archive processed files to `inbox/processed/`

## Sources

| Source | Description |
|--------|-------------|
| `czarina` | Learnings from Czarina phase closeouts |
| `manual` | Manually created drop files |

## Czarina Integration

Czarina exports northbound learnings via:
```bash
czarina learnings export [--to-hopper]
```

This creates drop files for each northbound candidate.
