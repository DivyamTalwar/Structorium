"""Tests for review packet AI-context enrichment."""

from __future__ import annotations

from structorium.app.commands.review.ai_context import (
    enrich_holistic_packet_with_ai_context,
)


def test_enrich_packet_skips_when_disabled(tmp_path, monkeypatch):
    packet: dict[str, object] = {"dimensions": ["design_coherence"]}

    called = {"value": False}

    def _fake_build(**_kwargs):
        called["value"] = True
        return {"status": "ready"}

    monkeypatch.setattr(
        "structorium.app.commands.review.ai_context.build_ai_review_context",
        _fake_build,
    )

    enrich_holistic_packet_with_ai_context(
        packet=packet,
        repo_root=tmp_path,
        lang=object(),
        files=[],
        config={"ai_enabled": False},
    )

    assert called["value"] is False
    assert "ai_context" not in packet


def test_enrich_packet_adds_context_and_batch_hints(tmp_path, monkeypatch):
    packet: dict[str, object] = {
        "dimensions": ["design_coherence"],
        "investigation_batches": [
            {"name": "b1", "files_to_read": ["src/a.py"]},
            {"name": "b2", "files_to_read": []},
        ],
    }

    def _fake_build(**_kwargs):
        return {
            "status": "ready",
            "vector": {
                "top_hits": [
                    {"file": "src/a.py", "score": 0.9},
                    {"file": "src/b.py", "score": 0.8},
                    {"file": "src/c.py", "score": 0.7},
                ]
            },
        }

    monkeypatch.setattr(
        "structorium.app.commands.review.ai_context.build_ai_review_context",
        _fake_build,
    )

    enrich_holistic_packet_with_ai_context(
        packet=packet,
        repo_root=tmp_path,
        lang=object(),
        files=["src/a.py", "src/b.py"],
        config={"ai_enabled": True, "ai_include_in_review": True},
    )

    assert packet.get("ai_context", {}).get("status") == "ready"
    batches = packet["investigation_batches"]
    assert isinstance(batches, list)
    assert batches[0]["ai_seed_files"] == ["src/b.py", "src/c.py"]
    assert batches[1]["ai_seed_files"] == ["src/a.py", "src/b.py", "src/c.py"]
