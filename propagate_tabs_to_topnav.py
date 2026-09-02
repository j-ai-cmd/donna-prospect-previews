#!/usr/bin/env python3
"""
Fourth propagation pass: move the section-tabs strip back into the topnav,
to the right of the logo/firm-name (reversing the earlier "move above the
form" change per updated direction). CSS already propagated via
propagate_redesign.py; this handles the HTML markup move.
"""
import os, re

PREVIEWS_DIR = '/tmp/donna-prospect-previews/previews'

TABS_DIV = '<div class="preview-part-tabs" id="preview-part-tabs"></div>'

# Currently sits inside .preview-content-wrap, right before .preview-form
OLD_LOCATION_RE = re.compile(
    r'(\n\s*)' + re.escape(TABS_DIV) + r'\n(\s*<div class="preview-form">)'
)

# Target: right after the firm-name span, before .preview-topnav's closing </div>
TOPNAV_CLOSE_RE = re.compile(
    r"(<span class=\"preview-firm-name\" id=\"topnav-name\"[^>]*>[^<]*</span>)\n(\s*)(</div>\n\s*<div class=\"preview-body\">)"
)

files = [f for f in os.listdir(PREVIEWS_DIR) if f.endswith('.html')]
updated, already_done, failed = 0, 0, []

for fname in files:
    path = os.path.join(PREVIEWS_DIR, fname)
    with open(path, encoding='utf-8') as f:
        content = f.read()

    # Already in the topnav? (tabs div appears before preview-body opens)
    topnav_idx = content.find('<div class="preview-topnav">')
    body_idx = content.find('<div class="preview-body">')
    tabs_idx = content.find(TABS_DIV)
    if topnav_idx != -1 and body_idx != -1 and tabs_idx != -1 and topnav_idx < tabs_idx < body_idx:
        already_done += 1
        continue

    m = OLD_LOCATION_RE.search(content)
    if not m:
        failed.append(fname)
        continue
    # Remove from old spot (keep the .preview-form div's own indentation intact)
    without_tabs = content[:m.start()] + '\n' + m.group(2) + content[m.end():]

    m2 = TOPNAV_CLOSE_RE.search(without_tabs)
    if not m2:
        failed.append(fname)
        continue
    new_content = (
        without_tabs[:m2.end(1)] + '\n' + m2.group(2) + TABS_DIV + '\n' +
        m2.group(2) + m2.group(3) + without_tabs[m2.end():]
    )

    if new_content == content:
        already_done += 1
        continue

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    updated += 1

print(f'Updated: {updated}')
print(f'Already done: {already_done}')
print(f'Failed: {len(failed)}')
if failed:
    print('Failures:', failed[:15])
