"""Direct tests for shared security phase potential accounting."""

from __future__ import annotations

from types import SimpleNamespace

import languages._framework.base.shared_phases as shared_phases_mod
from languages._framework.base.shared_phases import phase_security
from languages._framework.base.types import LangSecurityResult


def _lang_stub(*, files_scanned: int):
    return SimpleNamespace(
        zone_map=None,
        name="python",
        file_finder=lambda _path: ["src/app.py"],
        detect_lang_security_detailed=lambda _files, _zone: LangSecurityResult(
            entries=[],
            files_scanned=files_scanned,
        ),
        detector_coverage={},
    )


def test_phase_security_uses_max_scan_count_with_lang_security_result(monkeypatch, tmp_path):
    monkeypatch.setattr(
        shared_phases_mod,
        "detect_security_issues",
        lambda _files, _zone, _lang, **_kwargs: ([], 2),
    )
    findings, potentials = phase_security(tmp_path, _lang_stub(files_scanned=7))
    assert findings == []
    assert potentials == {"security": 7}


def test_phase_security_keeps_cross_lang_scan_count_when_larger(monkeypatch, tmp_path):
    monkeypatch.setattr(
        shared_phases_mod,
        "detect_security_issues",
        lambda _files, _zone, _lang, **_kwargs: ([], 9),
    )
    findings, potentials = phase_security(tmp_path, _lang_stub(files_scanned=3))
    assert findings == []
    assert potentials == {"security": 9}
