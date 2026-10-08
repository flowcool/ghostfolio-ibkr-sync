"""Offline tests for PR release-note labeling."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("release_labels", Path(__file__).parents[1] / "scripts/label_pr_release.py")
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


def test_title_types_map_to_labels():
    assert labels.labels_for_title("fix: stop duplicate dividends") == {"fix"}
    assert labels.labels_for_title("feat(cleanup): resume journals") == {"feature"}
    assert labels.labels_for_title("docs: refresh README") == {"documentation"}
    assert labels.labels_for_title("chore(deps): bump requests") == {"maintenance"}


def test_bang_marks_breaking_change():
    assert labels.labels_for_title("feat!: drop JSON resume") == {"feature", "breaking-change"}
    assert labels.labels_for_title("refactor(api)!: rename flag") == {"maintenance", "breaking-change"}


def test_type_is_case_insensitive():
    assert labels.labels_for_title("Feat!: drop JSON resume") == {"feature", "breaking-change"}
    assert labels.labels_for_title("FIX: x") == {"fix"}


def test_non_conventional_title_gets_nothing():
    assert labels.labels_for_title("Update stuff") == set()
    assert labels.labels_for_title("") == set()
    assert labels.labels_for_title(None) == set()


def test_impact_section_requires_real_text():
    template = "## Behavior\nx\n\n## Release impact\n\n<!-- bump, migration, rollback; write None if no impact -->\n\n## Verification\ny"
    assert not labels.impact_section_filled(template)
    assert not labels.impact_section_filled("no section here")
    assert not labels.impact_section_filled(None)
    filled = "## Release impact\nMinor bump. Migration: re-run dry-run. Rollback: previous digest.\n## Verification\n"
    assert labels.impact_section_filled(filled)
