from __future__ import annotations

from suno_mastering import pipeline


def test_announce_progress_emits_bar(capsys):
    pipeline._announce_progress(3, "Corrective EQ", "targets-based")
    output = capsys.readouterr().out

    assert "[Stage 3]" in output
    assert "|" in output
    assert "%" in output
    assert "Corrective EQ" in output
