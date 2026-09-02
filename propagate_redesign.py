#!/usr/bin/env python3
"""
Propagate the Hallmark-redesigned <link>+<style> block from the finalized
template (taylor-huguley-powers-pllc.html) to every other generated preview
file. Per-firm bits (--firm-primary/-dark/-container tokens, and everything
in <body>/<script>) are untouched — only the shared chrome is swapped.
"""
import re, os, sys

PREVIEWS_DIR = '/tmp/donna-prospect-previews/previews'
TEMPLATE = os.path.join(PREVIEWS_DIR, 'taylor-huguley-powers-pllc.html')

with open(TEMPLATE, encoding='utf-8') as f:
    template = f.read()

# Extract the new shared block: from the first <link rel="preconnect" up to </style>
m = re.search(r'(<link rel="preconnect".*?</style>)', template, re.DOTALL)
if not m:
    print('ERROR: could not find the new shared block in the template.')
    sys.exit(1)
new_block = m.group(1)

# The new block still contains the template's own --firm-primary values in the
# :root token block — those must NOT propagate. Replace them with placeholders
# tied to each target file's own existing values before writing.
NEW_ROOT_RE = re.compile(
    r':root \{\s*--firm-primary:\s*[^;]+;\s*--firm-primary-dark:\s*[^;]+;\s*--firm-primary-container:\s*[^;]+;\s*\}',
    re.DOTALL)
if not NEW_ROOT_RE.search(new_block):
    print('ERROR: could not find the :root token block to templatize.')
    sys.exit(1)

OLD_LINK_STYLE_RE = re.compile(r'<link rel="preconnect".*?</style>', re.DOTALL)
OLD_ROOT_RE = re.compile(
    r':root\s*\{\s*--firm-primary:\s*([^;]+);\s*--firm-primary-dark:\s*([^;]+);\s*--firm-primary-container:\s*([^;]+);\s*\}',
    re.DOTALL)

files = [f for f in os.listdir(PREVIEWS_DIR) if f.endswith('.html')]
updated, skipped, failed = 0, 0, []

for fname in files:
    path = os.path.join(PREVIEWS_DIR, fname)
    with open(path, encoding='utf-8') as f:
        content = f.read()

    root_match = OLD_ROOT_RE.search(content)
    if not root_match:
        skipped += 1
        continue

    primary, dark, container = (g.strip() for g in root_match.groups())
    firm_block = new_block
    # Swap the template's own firm tokens for this file's actual firm tokens.
    firm_block = NEW_ROOT_RE.sub(
        f':root {{\n  --firm-primary: {primary};\n  --firm-primary-dark: {dark};\n  --firm-primary-container: {container};\n}}',
        firm_block, count=1)

    if not OLD_LINK_STYLE_RE.search(content):
        failed.append(fname)
        continue

    new_content = OLD_LINK_STYLE_RE.sub(lambda _m: firm_block.replace('\\', '\\\\'), content, count=1)
    if new_content == content:
        skipped += 1
        continue

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    updated += 1

print(f'Updated: {updated}')
print(f'Skipped (no change / no root match): {skipped}')
print(f'Failed (no link/style block found): {len(failed)}')
if failed:
    print('First 10 failures:', failed[:10])
