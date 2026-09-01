#!/usr/bin/env python3
"""
Injects mobile-responsive CSS into every existing preview HTML file.
Idempotent: skips files that already have the marker comment.
"""
import os, glob

PREVIEWS_DIR = '/tmp/donna-prospect-previews/previews'
MARKER = '/* __RESPONSIVE_V1__ */'

RESPONSIVE_CSS = f'''{MARKER}
@media (max-width: 900px) {{
  body {{ padding: 12px 8px; }}
  #donna-app {{ width: 100%; height: 88vh; max-height: 720px; border-radius: 12px; box-shadow: 0 2px 24px rgba(30,18,9,0.12); }}
  #donna-app .preview-page {{ border-radius: 12px; }}
  #donna-app .preview-topnav {{ flex-wrap: wrap; height: auto; min-height: 52px; padding: 8px 12px; row-gap: 6px; }}
  #donna-app .preview-firm-name {{ font-size: 1rem; margin-right: 10px; }}
  #donna-app .preview-part-tabs {{ order: 3; width: 100%; overflow-x: auto; flex: none; -webkit-overflow-scrolling: touch; }}
  #donna-app .preview-part-tab {{ flex-shrink: 0; padding: 8px 10px; font-size: 0.72rem; }}
  #donna-app .preview-body {{ flex-direction: column; }}
  #donna-app .preview-sidebar {{ width: 100%; flex-direction: row; overflow-x: auto; padding: 10px 12px; border-right: none; border-bottom: 1px solid var(--cream-border); -webkit-overflow-scrolling: touch; }}
  #donna-app .preview-page-link {{ flex-shrink: 0; white-space: nowrap; margin-bottom: 0; }}
  #donna-app .preview-content-wrap {{ padding: 16px; }}
  #donna-app .preview-form {{ padding: 18px 16px; border-radius: 10px; }}
  #donna-app .preview-form-title {{ font-size: 1.15rem; }}
  #donna-app .preview-field-grid,
  #donna-app .preview-field-grid.cols-4 {{ grid-template-columns: 1fr; }}
  #donna-app .preview-radio-pill {{ padding: 7px 14px; font-size: 0.8rem; }}
}}
@media (max-width: 480px) {{
  #donna-app .preview-topnav img {{ height: 24px; max-width: 90px; margin-right: 10px; }}
  #donna-app .preview-firm-name {{ font-size: 0.9rem; margin-right: 8px; }}
  #donna-app .preview-draft-saved {{ font-size: 0.68rem; }}
  #donna-app .preview-next-btn {{ padding: 10px 20px; font-size: 0.82rem; }}
  #donna-app .preview-back-link {{ font-size: 0.78rem; }}
  #donna-app .preview-form-title {{ font-size: 1.05rem; }}
  #donna-app .preview-page-sub {{ font-size: 0.78rem; }}
}}
'''

VIEWPORT_TAG = '<meta name="viewport" content="width=device-width, initial-scale=1.0"/>'

files = glob.glob(os.path.join(PREVIEWS_DIR, '*.html'))
updated = 0
skipped = 0

for path in files:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    if MARKER in content:
        skipped += 1
        continue

    if '</style>' not in content:
        continue

    content = content.replace('</style>', RESPONSIVE_CSS + '</style>', 1)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    updated += 1

print(f'Updated: {updated}')
print(f'Already responsive (skipped): {skipped}')
print(f'Total files: {len(files)}')
