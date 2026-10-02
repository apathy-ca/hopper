"""A push rejected by the server must not silently lose the local edit (t418d978a)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from hopper.cli.local_client import LocalClient
from hopper.upstream.protocol import SyncConflict, SyncResponse
from hopper.upstream.storage import UpstreamStorage
from hopper.upstream.sync import SYNC_NOTE_AUTHOR, sync_with_upstream


class ServerBackedClient:
    """Mirrors the /sync handler in upstream/server.py, against real storage."""

    def __init__(self, server: UpstreamStorage) -> None:
        self.server = server

    def sync(self, tasks, since=0, instance="local", pull_limit=None):
        accepted, rejected = [], []
        for t in tasks:
            ok, _ = self.server.put(t, from_did="did:key:x")
            if ok:
                accepted.append(t.id)
            else:
                rejected.append(
                    SyncConflict(
                        task_id=t.id,
                        local_updated_at=0,
                        server_updated_at=0,
                        resolution="server_wins",
                    )
                )
        page, nxt = self.server.list_since_page(since, instance, pull_limit or 10_000)
        return SyncResponse(
            tasks=page,
            server_time=int(time.time() * 1000),
            accepted=accepted,
            rejected=rejected,
            has_more=nxt is not None,
            next_since=nxt,
        )


@pytest.fixture
def hosts(tmp_path: Path):
    server = UpstreamStorage(tmp_path / "srv")

    def host(name: str):
        path = tmp_path / name / ".hopper"
        path.mkdir(parents=True)
        (path / "config.yaml").write_text("instance:\n  id: shared\n  name: shared\n")
        return LocalClient(path), path

    def sync(client, path):
        return sync_with_upstream(
            client.task_store,
            ServerBackedClient(server),
            path / ".sync_state",
            instance="shared",
        )

    a, pa = host("a")
    b, pb = host("b")
    tid = a.create_task({"title": "shared task", "description": "original"})["id"]
    sync(a, pa)
    sync(b, pb)
    return a, pa, b, pb, tid, sync


def _collide(hosts):
    a, pa, b, pb, tid, sync = hosts
    a.update_task(tid, {"description": "A's edit (older)"})
    time.sleep(0.05)
    b.update_task(tid, {"description": "B's edit (newer)"})
    sync(b, pb)
    return sync(a, pa)


def test_losing_edit_is_saved_as_a_note(hosts):
    a, _, _, _, tid, _ = hosts
    result = _collide(hosts)
    assert result.conflicts == [tid]
    assert result.notes_added == [tid]
    task = a.get_task(tid)
    assert task["description"] == "B's edit (newer)"  # server still wins
    notes = [n for n in task["notes"] if n["author"] == SYNC_NOTE_AUTHOR]
    assert len(notes) == 1
    assert "A's edit (older)" in notes[0]["body"]
    assert "description" in notes[0]["body"]


def test_note_does_not_outrank_the_winners_unsynced_later_edit(hosts):
    """B edits again while offline, before A's conflicting sync runs.

    If saving the note bumped A's updated_at, A's copy would then be newer than
    B's unsynced edit and win on the server, silently discarding B's edit.
    """
    a, pa, b, pb, tid, sync = hosts
    a.update_task(tid, {"description": "A's edit (older)"})
    time.sleep(0.05)
    b.update_task(tid, {"description": "B's first edit"})
    sync(b, pb)
    time.sleep(0.05)
    b.update_task(tid, {"description": "B's second edit (offline)"})
    time.sleep(0.05)
    sync(a, pa)  # conflict: A loses to B's first edit, note is added
    sync(a, pa)  # A's next sync must not push a copy newer than B's second edit
    result = sync(b, pb)
    assert tid in result.pushed and tid not in result.conflicts
    assert b.get_task(tid)["description"] == "B's second edit (offline)"


def test_no_note_when_nothing_differs(hosts):
    a, pa, b, pb, tid, sync = hosts
    # Same edit on both hosts: a conflict by timestamp, but no content is lost.
    a.update_task(tid, {"description": "same"})
    time.sleep(0.05)
    b.update_task(tid, {"description": "same"})
    sync(b, pb)
    result = sync(a, pa)
    assert result.notes_added == []
    assert not [n for n in a.get_task(tid)["notes"] if n["author"] == SYNC_NOTE_AUTHOR]
