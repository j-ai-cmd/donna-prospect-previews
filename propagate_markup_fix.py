#!/usr/bin/env python3
"""
Second propagation pass: move the section-tabs strip out of the topnav to
directly above the form, and widen the JS sidebar group-spacer. The CSS for
this already propagated via propagate_redesign.py; this handles the two
remaining plain-text substitutions (HTML markup + one JS line) that are
identical across every generated file.
"""
import os

PREVIEWS_DIR = '/tmp/donna-prospect-previews/previews'

OLD_TABS_LINE = '    <div class="preview-part-tabs" id="preview-part-tabs"></div>\n'
NEW_TABS_LINE = ''  # removed from the topnav

OLD_CONTENT_WRAP = '      <div class="preview-content-wrap">\n        <div class="preview-form">\n'
NEW_CONTENT_WRAP = '      <div class="preview-content-wrap">\n        <div class="preview-part-tabs" id="preview-part-tabs"></div>\n        <div class="preview-form">\n'

OLD_SPACER = '<div style="height:6px"></div>'
NEW_SPACER = '<div style="height:14px"></div>'

files = [f for f in os.listdir(PREVIEWS_DIR) if f.endswith('.html')]
updated, already_done, failed = 0, 0, []

for fname in files:
    path = os.path.join(PREVIEWS_DIR, fname)
    with open(path, encoding='utf-8') as f:
        content = f.read()

    if NEW_TABS_LINE == '' and '<div class="preview-part-tabs" id="preview-part-tabs"></div>' not in content:
        already_done += 1
        continue

    if OLD_TABS_LINE not in content or OLD_CONTENT_WRAP not in content:
        failed.append(fname)
        continue

    new_content = content.replace(OLD_TABS_LINE, '', 1)
    new_content = new_content.replace(OLD_CONTENT_WRAP, NEW_CONTENT_WRAP, 1)
    new_content = new_content.replace(OLD_SPACER, NEW_SPACER, 1)

    if new_content == content:
        already_done += 1
        continue

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    updated += 1

print(f'Updated: {updated}')
print(f'Already done / no-op: {already_done}')
print(f'Failed (structure mismatch): {len(failed)}')
if failed:
    print('Failures:', failed[:10])
