"""Offline checks for onboarding navigation and moved operational guides."""
from pathlib import Path
import re
from urllib.parse import unquote

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUIDES = ('ibkr-setup.md', 'upgrading-to-2.2.md', 'troubleshooting.md', 'cleanup.md')
ADRS = ('0001-single-file-runtime.md', '0002-comment-and-proximity-deduplication.md',
        '0003-additive-imports.md', '0004-independent-cash-update.md',
        '0005-flex-window-and-corporate-actions.md', '0006-latest-follows-main.md',
        '0007-pinned-degiro-core.md')
DOCUMENTS = (('README.md',) + tuple(f'docs/{name}' for name in GUIDES)
             + ('docs/adr/README.md',) + tuple(f'docs/adr/{name}' for name in ADRS))


def markdown_headings(text):
    # Exclude fenced examples; their contents are not document headings or links.
    prose = re.sub(r'^```[^\n]*\n.*?^```\s*$', '', text, flags=re.M | re.S)
    headings = re.findall(r'^#{1,6} (.+)$', prose, flags=re.M)
    return {re.sub(r'[^\w\- ]', '', heading.replace('`', '').lower()).replace(' ', '-')
            for heading in headings}


@pytest.mark.parametrize('name', DOCUMENTS)
def test_documentation_local_links_resolve(name):
    source = ROOT / name
    text = source.read_text(encoding='utf-8')
    prose = re.sub(r'^```[^\n]*\n.*?^```\s*$', '', text, flags=re.M | re.S)
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', prose):
        if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:', target):
            continue
        path, separator, fragment = target.partition('#')
        destination = source.parent / unquote(path) if path else source
        assert destination.is_file(), f'{name}: missing local link {target}'
        if separator:
            assert unquote(fragment) in markdown_headings(destination.read_text(encoding='utf-8')), (
                f'{name}: missing heading in {target}')


def test_readme_retains_onboarding_and_links_each_guide():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    for heading in ('Get started', 'Prerequisites', 'Configuration', 'Limitations'):
        assert f'## {heading}\n' in text
    for guide in GUIDES:
        assert f'](docs/{guide})' in text
    for moved_heading in ('### 2. Create a Flex Query', '### Exit codes'):
        assert moved_heading not in text
    assert 'python cleanup_duplicates.py --resume' not in text


def test_adr_index_links_all_seven_dated_existing_decisions():
    index = (ROOT / 'docs/adr/README.md').read_text(encoding='utf-8')
    assert '](docs/adr/README.md)' in (ROOT / 'README.md').read_text(encoding='utf-8')
    assert {path.name for path in (ROOT / 'docs/adr').glob('[0-9]*.md')} == set(ADRS)
    for name in ADRS:
        assert f']({name})' in index
        text = (ROOT / 'docs/adr' / name).read_text(encoding='utf-8')
        assert re.search(r'^Date: \d{4}-\d{2}-\d{2}\. Status: accepted \(existing behavior\)\.$',
                         text, flags=re.M)
