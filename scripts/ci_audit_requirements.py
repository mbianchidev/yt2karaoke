"""Export installed versions for strict registry vulnerability lookup."""

from __future__ import annotations

import argparse
from importlib.metadata import distributions
from pathlib import Path

from packaging.utils import canonicalize_name
from packaging.version import Version


def audit_requirement(name: str, version: str) -> str | None:
    name = canonicalize_name(name, validate=True)
    if name == "yt2karaoke":
        return None
    parsed = Version(version)
    if parsed.local and not (name == "torch" and parsed.local == "cpu"):
        raise ValueError(f"Cannot map local distribution {name}=={version} to a registry release.")
    return f"{name}=={parsed.public}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    output = parser.parse_args().output
    requirements = {}
    for distribution in distributions():
        name = distribution.metadata.get("Name")
        if not name:
            raise ValueError("An installed distribution has no package name.")
        requirement = audit_requirement(name, distribution.version)
        if requirement is None:
            continue
        canonical = canonicalize_name(name)
        if canonical in requirements and requirements[canonical] != requirement:
            raise ValueError(f"Multiple installed versions of {canonical} cannot be audited unambiguously.")
        requirements[canonical] = requirement
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sorted(requirements.values())) + "\n", encoding="utf-8")
    print(
        f"Prepared {len(requirements)} installed registry versions for auditing. "
        "CPU Torch wheels use their upstream release version; the local project is excluded."
    )


if __name__ == "__main__":
    main()
