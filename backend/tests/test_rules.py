from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import rules


@pytest.fixture
def edited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "rules"
    monkeypatch.setattr(rules, "RULES_DIR", folder)
    return folder


def test_defaults_come_from_prompts(edited: Path) -> None:
    assert rules.read("lettre") and not edited.exists()


def test_an_edit_goes_to_data_and_wins(edited: Path) -> None:
    default = rules.read("tournures")
    assert rules.write("tournures", ["  je me   permets ", ""]) == ["je me permets"]
    assert (edited / "lettre-tournures.md").read_text(encoding="utf-8") == "- je me permets\n"
    assert rules.read("tournures") == ["je me permets"]
    # La liste par défaut du dépôt ne change pas.
    (edited / "lettre-tournures.md").unlink()
    assert rules.read("tournures") == default


def test_a_rule_can_span_several_lines(edited: Path) -> None:
    edited.mkdir()
    (edited / "lettre-regles.md").write_text("- une règle\n  qui continue\n- une autre\n", "utf-8")
    assert rules.read("lettre") == ["une règle qui continue", "une autre"]


def test_unknown_list(client: TestClient, edited: Path) -> None:
    assert client.get("/api/rules/projet").status_code == 404
    assert client.put("/api/rules/lettre", json={"rules": ["Court."]}).json() == {
        "rules": ["Court."]
    }
