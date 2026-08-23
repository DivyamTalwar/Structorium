from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_package_metadata_preserves_author_and_names_current_maintainer() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert metadata["authors"][0]["name"] == "Peter O'Malley"
    assert metadata["maintainers"][0]["name"] == "Divyam Talwar"
    assert metadata["urls"]["Repository"].endswith("/DivyamTalwar/Structorium")


def test_notice_and_license_preserve_original_attribution() -> None:
    license_text = (ROOT / "LICENSE").read_text()
    notice_text = (ROOT / "NOTICE").read_text()

    assert "Copyright (c) 2025 Peter O'Malley" in license_text
    assert "Copyright (c) 2025 Peter O'Malley" in notice_text
    assert "does not make claims" in notice_text
