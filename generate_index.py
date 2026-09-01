#!/usr/bin/env python3
"""
Generate index.html for donna-prospect-previews covering all firms.

Requires apollo_preview_summary.json to be present (produced by generate_apollo_previews.py).
The summary must include logo_url, website, linkedin fields for Apollo firms.

Usage:
  python3 generate_index.py
"""
import csv, io, re, os, json

PREVIEWS_DIR   = '/tmp/donna-prospect-previews/previews'
DRAFT_DATA     = '/tmp/draft_data.json'
APOLLO_CSV     = '/Users/jaidhingra/Downloads/apollo-contacts-export.csv'
APOLLO_SUMMARY = '/tmp/apollo_preview_summary.json'
OUT_PATH       = '/tmp/donna-prospect-previews/index.html'
PREVIEW_BASE   = 'https://donna-previews.vercel.app/previews'

def slugify(name):
    s = name.lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s

def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')

# ── Load data ────────────────────────────────────────────────────────

with open(DRAFT_DATA) as f:
    drafts = json.load(f)
original_slugs = set(d['slug'] for d in drafts)

with open(APOLLO_CSV, 'rb') as f:
    content = f.read().replace(b'\x00', b'')
apollo_rows = list(csv.DictReader(io.StringIO(content.decode('utf-8', errors='replace'))))
apollo_firms_csv = {}
for r in apollo_rows:
    cn = r['Company Name'].strip()
    if cn and cn not in apollo_firms_csv:
        apollo_firms_csv[cn] = r

with open(APOLLO_SUMMARY) as f:
    apollo_summary = json.load(f)
summary_by_slug = {item['slug']: item for item in apollo_summary}

# ── PMS detection ─────────────────────────────────────────────────────

def detect_pms(tech_str):
    if 'smokeball' in (tech_str or '').lower():
        return 'Smokeball'
    return 'Clio'

def pms_badge(pms):
    if pms == 'Clio':
        return '<span style="background:#f0f4ff;color:#4b6bfb;font-size:0.68rem;padding:1px 6px;border-radius:8px;font-weight:600;">Clio</span>'
    return '<span style="background:#fff4e6;color:#d97706;font-size:0.68rem;padding:1px 6px;border-radius:8px;font-weight:600;">Smokeball</span>'

def links_html(website, linkedin):
    links = ''
    if website:
        w = website if website.startswith('http') else 'https://' + website
        links += f'<a href="{esc(w)}" target="_blank" title="Website" style="display:inline-flex;align-items:center;justify-content:center;padding:3px 8px;border:1px solid #ddd;border-radius:5px;font-size:0.72rem;color:#444;text-decoration:none;">🌐</a>'
    if linkedin:
        links += f'{"&nbsp;" if website else ""}<a href="{esc(linkedin)}" target="_blank" title="LinkedIn" style="display:inline-flex;align-items:center;justify-content:center;padding:3px 8px;border:1px solid #c0d8ef;border-radius:5px;font-size:0.72rem;font-weight:700;color:#0077b5;text-decoration:none;background:#f0f8ff;">in</a>'
    return links

def logo_img(logo_url, firm_name):
    if not logo_url:
        return ''
    return (
        f'<img src="{esc(logo_url)}" alt="{esc(firm_name)}" '
        f'onerror="this.style.display=\'none\'" '
        f'style="height:22px;max-width:80px;object-fit:contain;vertical-align:middle;margin-bottom:2px;display:block;">'
    )

def color_dot(color):
    return (
        f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
        f'background:{color};margin-right:4px;border:1px solid rgba(0,0,0,0.1);'
        f'vertical-align:middle;flex-shrink:0;"></span>'
        f'<code style="font-size:0.68rem;color:#999;">{color}</code>'
    )

# ── Build rows ────────────────────────────────────────────────────────

rows_html = []

# ── Original 83 firms ────────────────────────────────────────────────
for i, d in enumerate(drafts):
    slug       = d['slug']
    firm_name  = d['firm_name']
    first_name = d['first_name']
    email      = d['email']
    pms        = d['pms']
    preview_url = f'{PREVIEW_BASE}/{slug}.html'

    # Try to get logo + website + linkedin from summary (if re-researched)
    summary = summary_by_slug.get(slug, {})
    logo    = summary.get('logo_url', '')
    website = summary.get('website', '')
    # Original firms don't have linkedin in draft_data — use summary if available
    linkedin = summary.get('linkedin_person', '') or summary.get('linkedin_company', '')
    firm_color = summary.get('color', '')

    source_badge = '<span style="background:#f0fff4;color:#16a34a;font-size:0.68rem;padding:1px 6px;border-radius:8px;font-weight:600;">Original</span>'

    rows_html.append(f'''    <tr data-source="original" data-firm="{esc(firm_name.lower())}" data-email="{esc(email.lower())}" data-contact="{esc(first_name.lower())}">
      <td style="color:#999;font-size:0.75rem;text-align:center;">{i+1}</td>
      <td>
        {logo_img(logo, firm_name)}
        <a href="{preview_url}" target="_blank" style="color:#1a1a1a;font-weight:600;font-size:0.84rem;text-decoration:none;">{esc(firm_name)}</a>
        <div style="display:flex;align-items:center;gap:4px;margin-top:3px;flex-wrap:wrap;">
          {(color_dot(firm_color) + ' ') if firm_color else ''}
          {pms_badge(pms)} {source_badge}
        </div>
      </td>
      <td><div style="font-weight:500;font-size:0.82rem;color:#1a1a1a;">{esc(first_name)}</div></td>
      <td><a href="mailto:{esc(email)}" style="font-size:0.78rem;color:#1a1a1a;text-decoration:none;">{esc(email)}</a></td>
      <td style="text-align:center;white-space:nowrap;">{links_html(website, linkedin)}</td>
      <td style="text-align:center;"><a href="{preview_url}" target="_blank" style="display:inline-block;padding:4px 12px;background:#1a1a1a;color:white;border-radius:6px;font-size:0.78rem;text-decoration:none;white-space:nowrap;">Open ↗</a></td>
    </tr>''')

# ── Apollo firms ─────────────────────────────────────────────────────
apollo_count = 0
for company_name, r in apollo_firms_csv.items():
    slug = slugify(company_name)
    if slug in original_slugs:
        continue

    preview_file = os.path.join(PREVIEWS_DIR, f'{slug}.html')
    if not os.path.exists(preview_file):
        continue

    first_name = r.get('First Name', '').strip()
    last_name  = r.get('Last Name', '').strip()
    full_name  = f'{first_name} {last_name}'.strip()
    title      = r.get('Title', '').strip()
    email      = r.get('Email', '').strip()
    city       = r.get('City', '').strip()
    state      = r.get('State', '').strip()
    tech       = r.get('Technologies', '')
    pms        = detect_pms(tech)

    # Prefer summary data (has logo + website + linkedin)
    summary    = summary_by_slug.get(slug, {})
    logo       = summary.get('logo_url', '')
    website    = summary.get('website', '') or r.get('Website', '').strip()
    linkedin   = summary.get('linkedin_person', '') or r.get('Person Linkedin Url', '').strip()
    company_li = summary.get('linkedin_company', '') or r.get('Company Linkedin Url', '').strip()
    if not linkedin:
        linkedin = company_li
    firm_color  = summary.get('color', '#7a2e3b')
    is_fallback = summary.get('fallback', True)

    preview_url = f'{PREVIEW_BASE}/{slug}.html'
    location    = ', '.join(x for x in [city, state] if x)

    source_badge = '<span style="background:#faf5ff;color:#7c3aed;font-size:0.68rem;padding:1px 6px;border-radius:8px;font-weight:600;">Apollo</span>'

    idx = len(drafts) + apollo_count + 1
    rows_html.append(f'''    <tr data-source="apollo" data-firm="{esc(company_name.lower())}" data-email="{esc(email.lower())}" data-contact="{esc(first_name.lower())}" data-state="{esc(state.lower())}">
      <td style="color:#999;font-size:0.75rem;text-align:center;">{idx}</td>
      <td>
        {logo_img(logo, company_name)}
        <a href="{preview_url}" target="_blank" style="color:#1a1a1a;font-weight:600;font-size:0.84rem;text-decoration:none;">{esc(company_name)}</a>
        <div style="display:flex;align-items:center;gap:4px;margin-top:3px;flex-wrap:wrap;">
          {color_dot(firm_color)}
          {pms_badge(pms)} {source_badge}
          {('<span style="font-size:0.7rem;color:#aaa;">' + esc(location) + '</span>') if location else ''}
        </div>
      </td>
      <td>
        <div style="font-weight:500;font-size:0.82rem;color:#1a1a1a;">{esc(full_name)}</div>
        {('<div style="font-size:0.72rem;color:#888;">' + esc(title) + '</div>') if title else ''}
      </td>
      <td><a href="mailto:{esc(email)}" style="font-size:0.78rem;color:#1a1a1a;text-decoration:none;">{esc(email)}</a></td>
      <td style="text-align:center;white-space:nowrap;">{links_html(website, linkedin)}</td>
      <td style="text-align:center;"><a href="{preview_url}" target="_blank" style="display:inline-block;padding:4px 12px;background:#1a1a1a;color:white;border-radius:6px;font-size:0.78rem;text-decoration:none;white-space:nowrap;">Open ↗</a></td>
    </tr>''')
    apollo_count += 1

total = len(drafts) + apollo_count

# ── Write index.html ──────────────────────────────────────────────────
html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<script defer src="/_vercel/insights/script.js"></script>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Donna Prospect Previews — {total} Firms</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f7f7f7; color: #1a1a1a; padding: 32px 24px; }}
  .header {{ max-width: 1200px; margin: 0 auto 20px; display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }}
  .header h1 {{ font-size: 1.4rem; font-weight: 700; }}
  .header p {{ font-size: 0.82rem; color: #888; }}
  .controls {{ max-width: 1200px; margin: 0 auto 14px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
  #search {{ flex: 1; min-width: 200px; padding: 9px 13px; border: 1.5px solid #ddd; border-radius: 8px; font-size: 0.88rem; outline: none; }}
  #search:focus {{ border-color: #1a1a1a; }}
  .filter-btn {{ padding: 7px 14px; border: 1.5px solid #ddd; border-radius: 8px; font-size: 0.8rem; background: white; cursor: pointer; color: #444; white-space: nowrap; }}
  .filter-btn.active {{ background: #1a1a1a; color: white; border-color: #1a1a1a; }}
  .table-wrap {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; border: 1px solid #e5e5e5; overflow: hidden; overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; min-width: 860px; }}
  thead th {{ background: #fafafa; border-bottom: 1.5px solid #e5e5e5; padding: 10px 14px; font-size: 0.71rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #888; text-align: left; white-space: nowrap; }}
  tbody tr {{ border-bottom: 1px solid #f0f0f0; transition: background 0.1s; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: #fafafa; }}
  tbody td {{ padding: 9px 14px; vertical-align: middle; font-size: 0.84rem; }}
  .count {{ max-width: 1200px; margin: 10px auto 0; font-size: 0.76rem; color: #aaa; text-align: right; }}
  .hidden {{ display: none !important; }}
</style>
</head>
<body>
<div class="header">
  <h1>Donna Prospect Previews</h1>
  <p>{total} firms &nbsp;·&nbsp; {len(drafts)} original &nbsp;+&nbsp; {apollo_count} Apollo</p>
</div>
<div class="controls">
  <input id="search" type="text" placeholder="Search firm, contact, email, state…" oninput="applyFilters()"/>
  <button class="filter-btn active" onclick="setSource('all',this)">All</button>
  <button class="filter-btn" onclick="setSource('original',this)">Original</button>
  <button class="filter-btn" onclick="setSource('apollo',this)">Apollo</button>
</div>
<div class="table-wrap">
  <table id="firms-table">
    <thead>
      <tr>
        <th style="width:32px;">#</th>
        <th>Firm</th>
        <th style="width:180px;">Contact</th>
        <th style="width:210px;">Email</th>
        <th style="width:100px;text-align:center;">Links</th>
        <th style="width:90px;text-align:center;">Preview</th>
      </tr>
    </thead>
    <tbody>
{''.join(rows_html)}
    </tbody>
  </table>
</div>
<div class="count" id="count-label">{total} firms shown</div>
<script>
var activeSource = 'all';
function setSource(src, btn) {{
  activeSource = src;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}
function applyFilters() {{
  var q = document.getElementById('search').value.toLowerCase().trim();
  var rows = document.querySelectorAll('#firms-table tbody tr');
  var shown = 0;
  rows.forEach(function(tr) {{
    var firm    = tr.dataset.firm    || '';
    var email   = tr.dataset.email   || '';
    var contact = tr.dataset.contact || '';
    var state   = tr.dataset.state   || '';
    var source  = tr.dataset.source  || '';
    var matchSearch = !q || firm.includes(q) || email.includes(q) || contact.includes(q) || state.includes(q);
    var matchSource = activeSource === 'all' || activeSource === source;
    if (matchSearch && matchSource) {{
      tr.classList.remove('hidden');
      shown++;
    }} else {{
      tr.classList.add('hidden');
    }}
  }});
  document.getElementById('count-label').textContent = shown + ' firms shown';
}}
</script>
</body>
</html>'''

with open(OUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Done: {total} firms ({len(drafts)} original + {apollo_count} Apollo)')
print(f'Written to: {OUT_PATH}')
