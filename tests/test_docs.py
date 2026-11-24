"""The links of every Markdown document, and the contents at the top of a
README, as mailbox checks its own.

A link renders whether it leads anywhere or not, so a renamed heading or a
moved file goes unnoticed. Checked here, without the network:

- a link to a heading lands on one, in the same file or another one of
  the repository;
- a link into the repository, relative or as an address on GitHub,
  names a file or folder that is there;
- a README with two sections or more lists them all, in order, in its
  contents after the title and the short description. The organisation
  profile is left out: it is the page github.com/benethos-hub shows.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "https://github.com/benethos-hub/.github"
CONTENTS = "**Contents**"
PROFILE = "profile/README.md"

# Only the ``](target)`` tail of a link: a badge is a link around an image,
# and its outer target is the one that counts.
_LINK = re.compile(r"\]\(([^)\s]+)\)")
_SRC = re.compile(r"""<img\b[^>]*?\bsrc=["']([^"']+)["']""")
_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
_HEADING = re.compile(r"^(#{1,6}) (.+)$", re.M)
_IN_REPOSITORY = re.compile(
    r"^https://(?:github\.com/benethos-hub/\.github/(?:blob|tree)/main/"
    r"|raw\.githubusercontent\.com/benethos-hub/\.github/main/)([^#?]*)(?:#(.*))?$"
)


def _documents() -> list[Path]:
    """Every Markdown file git lists, tracked or new. A virtual
    environment or a cache never counts."""
    git = shutil.which("git")
    if git is None:
        pytest.fail("the documents are found through git, which is missing")
    done = subprocess.run(
        [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.fail("the documents are found through git: not a git checkout")
    names = sorted(set(filter(None, done.stdout.decode().split("\0"))))
    return [ROOT / name for name in names if name.endswith(".md")]


def _readmes() -> list[Path]:
    return [
        path
        for path in _documents()
        if path.name == "README.md" and _name(path) != PROFILE
    ]


def _name(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _text(markdown: str) -> str:
    return _FENCE.sub("", markdown)


def _targets(markdown: str) -> list[str]:
    text = _text(markdown)
    return _LINK.findall(text) + _SRC.findall(text)


def anchor(heading: str) -> str:
    """GitHub's anchor of a heading: the text without HTML and code marks,
    in lower case, punctuation dropped, spaces as hyphens."""
    text = re.sub(r"<[^>]+>", "", heading).replace("`", "").strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _headings(markdown: str) -> list[tuple[int, str, str]]:
    """Level, text and anchor of each heading. A repeated anchor gets -1,
    -2 and so on, as on GitHub."""
    found: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for marks, heading in _HEADING.findall(_text(markdown)):
        base = unique = anchor(heading)
        suffix = 0
        while unique in seen:
            suffix += 1
            unique = f"{base}-{suffix}"
        seen.add(unique)
        found.append((len(marks), heading, unique))
    return found


def _anchors(path: Path) -> set[str]:
    return {a for _, _, a in _headings(path.read_text("utf-8"))}


def _broken(document: Path, target: str) -> str | None:
    """Why ``target`` in ``document`` leads nowhere, or None."""
    if target.startswith("#"):
        return None if target[1:] in _anchors(document) else "no such heading"
    found = _IN_REPOSITORY.match(target)
    if found:
        path, fragment = ROOT / found[1], found[2]
    elif target.startswith(("http://", "https://", "mailto:")):
        return None
    else:
        file, _, fragment = target.partition("#")
        path = (document.parent / file).resolve()
    if not path.exists():
        return "no such file"
    if fragment and path.suffix == ".md" and fragment not in _anchors(path):
        return "no such heading there"
    return None


@pytest.mark.parametrize("document", _documents(), ids=_name)
def test_every_link_leads_somewhere(document: Path) -> None:
    broken = [
        f"{target}: {why}"
        for target in _targets(document.read_text("utf-8"))
        if (why := _broken(document, target))
    ]
    assert not broken, "\n  ".join(["links that lead nowhere:", *broken])


def contents(markdown: str) -> str:
    """The contents a README shows: its sections and their parts, after
    the title, linked to their headings."""
    lines = [CONTENTS, ""]
    for level, heading, target in _headings(markdown):
        if level in (2, 3):
            indent = "  " * (level - 2)
            title = re.sub(r"<[^>]+>", "", heading).strip()
            lines.append(f"{indent}- [{title}](#{target})")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("readme", _readmes(), ids=_name)
def test_a_readme_of_several_sections_lists_them_at_its_top(readme: Path) -> None:
    text = readme.read_text("utf-8")
    sections = [h for h in _headings(text) if h[0] == 2]
    if len(sections) < 2:
        assert CONTENTS not in text
        return
    wanted = contents(text)
    assert wanted in text, f"the contents should read:\n\n{wanted}"
    assert text.index(wanted) < text.index("\n## "), "the contents come first"


def test_the_documents_are_found() -> None:
    names = {_name(p) for p in _documents()}
    assert {
        "README.md",
        "docs/README.md",
        "docs/FRESHNESS.md",
        "docs/freshness/calling.md",
        PROFILE,
    } <= names
    assert not any(".venv" in name.split("/") for name in names)
    assert {_name(p) for p in _readmes()} >= {"README.md", "docs/README.md"}
    assert PROFILE not in {_name(p) for p in _readmes()}


def test_the_anchor_follows_githubs_rules() -> None:
    assert anchor("What it holds") == "what-it-holds"
    assert anchor("A `package-lock.json`") == "a-package-lockjson"
    assert anchor("C. `details: false`: the core") == "c-details-false-the-core"
    assert anchor('<img src="x.svg"> Mailbox') == "mailbox"


def test_the_check_sees_what_is_broken(tmp_path: Path) -> None:
    document = tmp_path / "README.md"
    document.write_text(
        "# T\n\n## Here\n\n[a](#here) [b](#gone) [c](missing.md)\n"
        "[![x](https://img.example/x.svg)](LICENSE)\n```\n[d](nothing)\n```\n",
        "utf-8",
    )
    targets = _targets(document.read_text("utf-8"))
    assert targets == [
        "#here",
        "#gone",
        "missing.md",
        "https://img.example/x.svg",
        "LICENSE",
    ]
    assert [_broken(document, t) for t in targets] == [
        None,
        "no such heading",
        "no such file",
        None,
        "no such file",
    ]
    assert _broken(document, f"{REPOSITORY}/blob/main/nope.md")
    assert not _broken(document, f"{REPOSITORY}/blob/main/LICENSE")
    assert _broken(document, f"{REPOSITORY}/blob/main/README.md#nowhere")
