"""Audit CPU wheel versions without losing registry advisory coverage."""

import pytest

from scripts.ci_audit_requirements import audit_requirement


def test_registry_version_is_preserved():
    assert audit_requirement("Pillow", "13.0.0") == "pillow==13.0.0"


def test_cpu_torch_is_audited_against_its_upstream_version():
    assert audit_requirement("torch", "2.15.0+cpu") == "torch==2.15.0"


def test_only_the_local_project_is_excluded():
    assert audit_requirement("yt2karaoke", "0.1.0") is None


@pytest.mark.parametrize("name,version", [
    ("torch", "2.15.0+custom"), ("other-package", "1.0+cpu"),
    ("bad name", "1.0"), ("torch", "not-a-version"),
])
def test_unsupported_metadata_fails_instead_of_skipping(name, version):
    with pytest.raises(ValueError):
        audit_requirement(name, version)
