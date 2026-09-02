#!/usr/bin/env python3
"""
Third propagation pass: move "Draft saved" out of the topnav into a proper
footer bar at the bottom of the widget. CSS already propagated via
propagate_redesign.py; this handles the HTML markup move, which is
identical across every generated file except the topnav's img/alt/logo bits
(untouched — we only touch the draft-saved div and closing tags).
"""
import os, re

PREVIEWS_DIR = '/tmp/donna-prospect-previews/previews'

DRAFT_SAVED_RE = re.compile(
    r'\n\s*<div class="preview-draft-saved"><span class="preview-draft-dot"></span>Draft saved</div>'
)

files = [f for f in os.listdir(PREVIEWS_DIR) if f.endswith('.html')]
updated, already_done, failed = 0, 0, []

for fname in files:
    path = os.path.join(PREVIEWS_DIR, fname)
    with open(path, encoding='utf-8') as f:
        content = f.read()

    if '<div class="preview-footer">' in content:
        already_done += 1
        continue

    m = DRAFT_SAVED_RE.search(content)
    if not m:
        failed.append(fname)
        continue

    # Remove it from wherever it currently sits (inside .preview-topnav)
    new_content = content[:m.start()] + content[m.end():]

    # Re-insert it as a footer, right after </div> that closes .preview-body,
    # i.e. right before the two closing </div></div> that end #donna-app's
    # .preview-page and #donna-app itself, followed by <script>.
    anchor = '  </div>\n</div>\n</div>\n<script>'
    if anchor not in new_content:
        failed.append(fname)
        continue
    footer_html = (
        '  </div>\n'
        '  <div class="preview-footer">\n'
        '    <div class="preview-draft-saved"><span class="preview-draft-dot"></span>Draft saved</div>\n'
        '  </div>\n'
        '</div>\n</div>\n<script>'
    )
    new_content = new_content.replace(anchor, footer_html, 1)

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
