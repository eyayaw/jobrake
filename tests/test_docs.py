"""The user docs: one page per site, links that resolve, and example commands the CLI accepts."""

import re
import shlex
from pathlib import Path

import pytest

from jobrake import cli
from jobrake.sites import SITES
from jobrake.utils import site_options

ROOT = Path(__file__).parents[1]
PAGES = ROOT / "docs" / "sites"
# Skip maintainer scratch notes (docs/_*.md) and the logo attribution README.
DOCS = [
    ROOT / "README.md",
    *(p for p in sorted(ROOT.glob("docs/*.md")) if not p.name.startswith("_")),
    *sorted(PAGES.glob("*.md")),
]
# Standard site-page sections, checked for relative order when present.
SECTIONS = ["Options", "Lookups", "Fields", "Requests", "Terms"]
LINK = re.compile(r"\]\(([^)\s]+)\)|href=\"([^\"]+)\"")
# The README links to the repository by absolute URL, so it also reads right off GitHub.
REPO = "https://github.com/eyayaw/jobrake/blob/main/"
FENCE = re.compile(r"^```(?:sh|bash|console)\n(.*?)^```", re.MULTILINE | re.DOTALL)
SHELL_ENDS = {"|", "||", "&&", ";", ">", ">>", "<", "&"}


def _slug(heading: str) -> str:
    """Return the anchor GitHub gives a heading."""
    text = re.sub(r"[`*_]|\[([^]]*)\]\([^)]*\)", r"\1", heading.strip()).lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    text = re.sub(r"^```.*?^```", "", path.read_text(), flags=re.MULTILINE | re.DOTALL)
    return {_slug(heading) for heading in re.findall(r"^#{1,6} (.+)$", text, re.MULTILINE)}


def test_every_site_has_one_page():
    assert {page.stem for page in PAGES.glob("*.md")} == set(SITES)


@pytest.mark.parametrize("site", SITES)
def test_a_site_page_keeps_the_section_order(site):
    text = (PAGES / f"{site}.md").read_text()
    assert text.startswith("# "), site
    sections = re.findall(r"^## (.+)$", text, re.MULTILINE)
    standard = [name for name in sections if name in SECTIONS]
    assert standard == [name for name in SECTIONS if name in standard], sections


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: str(path.relative_to(ROOT)))
def test_a_link_into_the_repository_names_a_file_and_heading_that_exist(doc):
    broken = []
    for target in (markdown or html for markdown, html in LINK.findall(doc.read_text())):
        local = target.removeprefix(REPO)
        if re.match(r"[a-z]+:", local):
            continue
        name, _, anchor = local.partition("#")
        base = ROOT if local != target else doc.parent
        path = (base / name).resolve() if name else doc
        if not path.exists() or (anchor and path.suffix == ".md" and anchor not in _anchors(path)):
            broken.append(target)
    assert not broken


def _commands(doc: Path) -> list[str]:
    """Return each ``jobrake`` command in a shell block of ``doc``, with continuations joined."""
    found = []
    # A fence inside a quote block, such as a tip, holds commands too.
    text = re.sub(r"^> ?", "", doc.read_text(), flags=re.MULTILINE)
    for block in FENCE.findall(text):
        for raw in block.replace("\\\n", " ").splitlines():
            line = raw.strip().removeprefix("$ ").removeprefix("uvx ")
            if line.startswith("jobrake ") and "..." not in line:  # "jobrake ..." is a placeholder
                found.append(line)
    return found


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: str(path.relative_to(ROOT)))
def test_an_example_command_passes_its_checks(doc, capsys):
    # Parsing and the site function's own checks send no request, so a stale flag or a value the
    # site refuses fails here.
    parser = cli._build_parser()  # noqa: SLF001  parsing alone checks a command without running it
    for line in _commands(doc):
        lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = []
        for word in lexer:
            if word in SHELL_ENDS:
                break
            words.append(word)
        try:
            args = parser.parse_args(words[1:])
        except SystemExit as stop:  # -h exits 0 after printing the help
            if stop.code:
                pytest.fail(f"{doc.name}: {line!r} exits {stop.code}: {capsys.readouterr().err}")
            continue
        if not getattr(args, "site", None):  # jobrake -h or --version
            continue
        function = getattr(SITES[args.site], args.command)
        options = {name: vars(args)[name] for name in site_options(function) if name in vars(args)}
        try:
            function.check(**options)
        except (TypeError, ValueError) as error:
            pytest.fail(f"{doc.name}: {line!r} raises {error!r}")
