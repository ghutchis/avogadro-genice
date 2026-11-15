"""Raise dependency floors to the latest release and bump the version.

The packages to track are listed in pyproject.toml:

    [tool.update-dependencies]
    track = ["somepackage", "otherpackage"]

Each is looked up wherever it is declared, and must have a ">=" floor there:

    [project].dependencies          PyPI
    [tool.pixi.pypi-dependencies]   PyPI
    [tool.pixi.dependencies]        conda-forge

If a newer final release exists than the floor, the floor is raised to it. On
conda-forge, only a version built for every platform in the pixi workspace (or
as noarch) counts, since pixi solves all of them. If any floor moved, the patch
number of [project].version is bumped, so that Avogadro's plugin manager offers
installed copies of the plugin an update.

Writes changed/version/summary lines for $GITHUB_OUTPUT to stdout.
"""

import json
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

PYPROJECT = Path(sys.argv[1] if len(sys.argv) > 1 else "pyproject.toml")
FLOOR_RE = re.compile(r"(>=\s*)([0-9][0-9.]*)")


def release_tuple(version):
    """Numeric release parts without trailing zeros, so 2.0 == 2.0.0.

    Returns None for pre-releases and other non-numeric forms."""
    if not re.fullmatch(r"\d+(\.\d+)*", version):
        return None
    parts = [int(part) for part in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def pypi_releases(package):
    data = fetch_json(f"https://pypi.org/pypi/{package}/json")
    releases = [
        version
        for version, files in data["releases"].items()
        if release_tuple(version) and any(not f.get("yanked") for f in files)
    ]
    if not releases:
        raise SystemExit(f"No final releases of {package} on PyPI")
    return releases


def conda_releases(package, platforms):
    if not platforms:
        raise SystemExit("No platforms in [tool.pixi.workspace]")
    data = fetch_json(f"https://api.anaconda.org/package/conda-forge/{package}")
    subdirs = {}
    for f in data.get("files", []):
        if "main" not in f.get("labels", []):
            continue
        version = f.get("version", "")
        if release_tuple(version):
            subdirs.setdefault(version, set()).add(f["attrs"].get("subdir"))
    complete = [
        version
        for version, built in subdirs.items()
        if "noarch" in built or set(platforms) <= built
    ]
    if not complete:
        raise SystemExit(
            f"No release of {package} on conda-forge covers {', '.join(platforms)}"
        )
    return complete


CLAUSE_RE = re.compile(r"\s*(<=|<|!=|>=|>|==|~=)?\s*([0-9][0-9.]*)(\.\*)?\s*")
COMPARE = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "!=": lambda a, b: a != b,
}


def version_spec(spec):
    """The version part of a PEP 508 requirement or a pixi version string."""
    spec = spec.split(";", 1)[0]
    return re.sub(r"^\s*[A-Za-z][A-Za-z0-9._-]*\s*(\[[^\]]*\])?", "", spec)


def newest_allowed(releases, spec, where):
    """Newest release that every clause of spec except the floor allows.

    Upper bounds are kept, so a new major version excluded by "<3" is not
    taken. Pins (==, ~=, wildcards) cannot be tracked."""
    releases = [v for v in releases if release_tuple(v)]
    bounds = []
    for clause in version_spec(spec).split(","):
        if not clause.strip():
            continue
        match = CLAUSE_RE.fullmatch(clause)
        op = match and match.group(1)
        if match is None or op in (None, "==", "~=") or match.group(3):
            raise SystemExit(f'{where}: cannot track "{spec}" (pinned)')
        if op != ">=":
            bounds.append((COMPARE[op], release_tuple(match.group(2))))
    allowed = [
        v for v in releases if all(ok(release_tuple(v), b) for ok, b in bounds)
    ]
    newest = max(releases, key=release_tuple)
    if not allowed:
        raise SystemExit(f'{where}: no release satisfies "{spec}"')
    best = max(allowed, key=release_tuple)
    if best != newest:
        print(f'{where}: {newest} is out, but "{spec}" excludes it', file=sys.stderr)
    return best


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def table_bounds(text, header):
    """Start and end of the [header] table in text, or None."""
    match = re.search(rf"^\[{re.escape(header)}\]\s*$", text, re.MULTILINE)
    if match is None:
        return None
    following = re.search(r"^\[", text[match.end() :], re.MULTILINE)
    end = match.end() + following.start() if following else len(text)
    return match.start(), end


def edit_table(text, header, edit):
    bounds = table_bounds(text, header)
    if bounds is None:
        raise SystemExit(f"Cannot find [{header}] to edit")
    start, end = bounds
    return text[:start] + edit(text[start:end]) + text[end:]


def floor_of(spec, where):
    match = FLOOR_RE.search(spec)
    if match is None or release_tuple(match.group(2)) is None:
        raise SystemExit(f'{where}: "{spec}" has no ">=x.y.z" floor')
    return match.group(2)


def find_declarations(data, package):
    """Yield (source, table header, key or requirement, spec) for package."""
    for requirement in data.get("project", {}).get("dependencies", []):
        match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
        if match and normalize(match.group(1)) == normalize(package):
            yield "pypi", "project", requirement, requirement

    pixi = data.get("tool", {}).get("pixi", {})
    for source, table in (("pypi", "pypi-dependencies"), ("conda", "dependencies")):
        for key, value in pixi.get(table, {}).items():
            if normalize(key) != normalize(package):
                continue
            spec = value.get("version", "") if isinstance(value, dict) else value
            yield source, f"tool.pixi.{table}", key, spec


def raise_requirement(table, requirement, latest):
    quoted = f'"{requirement}"'
    if quoted not in table:
        raise SystemExit(f"Cannot find {quoted} in [project]")
    raised = FLOOR_RE.sub(rf"\g<1>{latest}", requirement, count=1)
    return table.replace(quoted, f'"{raised}"', 1)


def raise_key(table, key, latest, header):
    line_re = re.compile(rf'^\s*"?{re.escape(key)}"?\s*=.*$', re.MULTILINE)
    match = line_re.search(table)
    if match is None or not FLOOR_RE.search(match.group(0)):
        raise SystemExit(f"Cannot find a one-line {key} floor in [{header}]")
    line = FLOOR_RE.sub(rf"\g<1>{latest}", match.group(0), count=1)
    return table[: match.start()] + line + table[match.end() :]


def main():
    text = PYPROJECT.read_text()
    data = tomllib.loads(text)
    tracked = data.get("tool", {}).get("update-dependencies", {}).get("track", [])
    pixi = data.get("tool", {}).get("pixi", {})
    workspace = pixi.get("workspace", pixi.get("project", {}))
    # Entries are subdirs, or tables like { name = "linux-cuda", platform = "linux-64" }.
    platforms = sorted({
        p["platform"] if isinstance(p, dict) else p
        for p in workspace.get("platforms", [])
    })
    release_cache = {}
    changes = []

    for package in tracked:
        if normalize(package) == "python":
            raise SystemExit("python cannot be tracked")
        declarations = list(find_declarations(data, package))
        if not declarations:
            raise SystemExit(f"{package} is tracked but not declared as a dependency")
        for source, header, name, spec in declarations:
            where = f"[{header}] {package}"
            floor = floor_of(spec, where)
            if (source, package) not in release_cache:
                release_cache[source, package] = (
                    pypi_releases(package)
                    if source == "pypi"
                    else conda_releases(package, platforms)
                )
            latest = newest_allowed(release_cache[source, package], spec, where)
            if release_tuple(latest) <= release_tuple(floor):
                continue
            if header == "project":
                text = edit_table(
                    text, header, lambda t: raise_requirement(t, name, latest)
                )
            else:
                text = edit_table(
                    text, header, lambda t: raise_key(t, name, latest, header)
                )
            label = "PyPI" if source == "pypi" else "conda-forge"
            changes.append(f"{package} {floor} → {latest} ({label})")

    if not changes:
        print("changed=false")
        return

    version_re = re.compile(r'^(version\s*=\s*")(\d+)\.(\d+)\.(\d+)(")', re.MULTILINE)
    new_version = None

    def bump(table):
        nonlocal new_version
        match = version_re.search(table)
        if match is None:
            raise SystemExit("No x.y.z version in [project]")
        major, minor, patch = (int(g) for g in match.group(2, 3, 4))
        new_version = f"{major}.{minor}.{patch + 1}"
        return version_re.sub(rf"\g<1>{new_version}\g<5>", table, count=1)

    text = edit_table(text, "project", bump)
    tomllib.loads(text)  # never write a pyproject.toml that does not parse
    PYPROJECT.write_text(text)
    print("changed=true")
    print(f"version={new_version}")
    print(f"summary={', '.join(changes)}")


if __name__ == "__main__":
    main()
