#!/usr/bin/env python3
"""
Generate preview HTML files for Apollo prospect firms.

For each firm:
  - Scrapes primary brand color from website CSS/meta
  - Scrapes logo URL from website (og:image, <img class/id/src contains "logo">)
  - Generates branded estate-planning intake form (same template as existing 85 firms)
  - Skips slugs already in previews/ (idempotent — safe to re-run)

After running this, run generate_index.py to rebuild index.html.

Usage:
  pip install requests beautifulsoup4
  python3 generate_apollo_previews.py

Config at top of file — update CSV_PATH and PREVIEWS_DIR as needed.
"""
import csv, io, re, os, json, colorsys
import concurrent.futures
from urllib.parse import urlparse, urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests', 'beautifulsoup4', '-q'])
    import requests
    from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────
PREVIEWS_DIR = '/tmp/donna-prospect-previews/previews'   # ← update if needed
CSV_PATH     = '/Users/jaidhingra/Downloads/apollo-contacts-export.csv'
SUMMARY_OUT  = '/tmp/apollo_preview_summary.json'

FALLBACK_PRIMARY   = '#7a2e3b'
FALLBACK_DARK      = '#5e2230'
FALLBACK_CONTAINER = '#f0ead8'

os.makedirs(PREVIEWS_DIR, exist_ok=True)

# ── Slug ─────────────────────────────────────────────────────────────

def slugify(name):
    s = name.lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s).strip('-')
    return s

# ── Color helpers ─────────────────────────────────────────────────────

def hex_to_hsv(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c*2 for c in h)
    if len(h) != 6:
        return None
    try:
        r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
        return colorsys.rgb_to_hsv(r, g, b)
    except Exception:
        return None

def is_good_brand_color(hex_color):
    hsv = hex_to_hsv(hex_color)
    if not hsv:
        return False
    h, s, v = hsv
    if v < 0.15 or v > 0.97:
        return False
    if s < 0.15:
        return False
    return True

def darken_hex(hex_color, factor=0.75):
    hsv = hex_to_hsv(hex_color)
    if not hsv:
        return FALLBACK_DARK
    h, s, v = hsv
    r, g, b = colorsys.hsv_to_rgb(h, s, max(0, v * factor))
    return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))

def lighten_hex(hex_color):
    hsv = hex_to_hsv(hex_color)
    if not hsv:
        return FALLBACK_CONTAINER
    h, s, v = hsv
    r, g, b = colorsys.hsv_to_rgb(h, s * 0.15, 0.96)
    return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))

HEX_RE = re.compile(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')

# ── Web scraping ──────────────────────────────────────────────────────

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'}

def fetch(url, timeout=8):
    if not url:
        return None, None
    if not url.startswith('http'):
        url = 'https://' + url
    try:
        r = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        r.raise_for_status()
        return r.text, r.url  # content, final URL (after redirects)
    except Exception:
        return None, None

def scrape_logo(html, base_url):
    """
    Try to find a usable logo URL from a page.
    Priority:
      1. <img> whose src/alt/id/class contains 'logo' and is NOT an icon (>= 60px implied or path says logo)
      2. og:image meta (the firm's social share image — often the logo on small firm sites)
      3. apple-touch-icon (high-res favicon)
    Returns absolute URL or None.
    """
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')

    def abs_url(u):
        if not u:
            return None
        u = u.strip()
        if u.startswith('data:'):
            return None
        return urljoin(base_url, u)

    # 1. <img> tags with 'logo' in src, alt, id or class
    for img in soup.find_all('img'):
        src = img.get('src', '')
        alt = img.get('alt', '')
        id_ = img.get('id', '')
        cls = ' '.join(img.get('class', []))
        combined = (src + alt + id_ + cls).lower()
        if 'logo' in combined:
            url = abs_url(src)
            if url and not url.startswith('data:'):
                # skip tiny icons (favicon-ish names)
                if not any(x in url.lower() for x in ['favicon', 'icon-16', 'icon-32']):
                    return url

    # 2. og:image
    og = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name': 'og:image'})
    if og:
        url = abs_url(og.get('content', ''))
        if url:
            return url

    # 3. apple-touch-icon (at least 180x180)
    for rel in ['apple-touch-icon', 'apple-touch-icon-precomposed']:
        link = soup.find('link', rel=lambda r: r and rel in r)
        if link:
            url = abs_url(link.get('href', ''))
            if url:
                return url

    return None

def scrape_brand_color(html):
    """Extract primary brand color from page HTML."""
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')

    # 1. meta theme-color
    meta = soup.find('meta', attrs={'name': 'theme-color'})
    if meta:
        c = meta.get('content', '').strip()
        if c.startswith('#') and is_good_brand_color(c):
            return c

    styles = ' '.join(t.string or '' for t in soup.find_all('style'))

    # 2. CSS custom properties
    for pattern in [
        r'--(?:primary|brand|accent|color-primary|main-color|brand-color|site-color)[^:]*:\s*(#[0-9a-fA-F]{3,6})',
        r'--(?:color|clr)-(?:primary|accent|brand)[^:]*:\s*(#[0-9a-fA-F]{3,6})',
    ]:
        m = re.search(pattern, styles, re.IGNORECASE)
        if m:
            c = m.group(1)
            if is_good_brand_color(c):
                return c

    # 3. Button inline styles
    for el in soup.find_all(['button', 'a', 'header', 'nav'], limit=60):
        style = el.get('style', '')
        for m in HEX_RE.finditer(style):
            c = '#' + m.group(1)
            if is_good_brand_color(c):
                return c

    # 4. Most saturated color in all <style> blocks
    colors = []
    for m in HEX_RE.finditer(styles):
        c = '#' + m.group(1)
        if is_good_brand_color(c):
            hsv = hex_to_hsv(c)
            if hsv:
                colors.append((hsv[1], c))
    if colors:
        colors.sort(reverse=True)
        return colors[0][1]

    return None

def research_firm(website):
    """Return (primary_color, logo_url) for a firm's website."""
    html, final_url = fetch(website)
    if not html:
        return None, None
    color = scrape_brand_color(html)
    logo  = scrape_logo(html, final_url or website)
    return color, logo

# ── HTML template ─────────────────────────────────────────────────────

def make_html(firm_name, primary, primary_dark, primary_container, logo_url=None):
    heading_css = "'Crimson Text', serif"
    gf = 'family=Inter:wght@400;500;600;700&family=Source+Sans+3:wght@400;500;600;700&family=Crimson+Text:wght@400;600;700'

    if logo_url:
        topnav_brand = (
            f'<img src="{logo_url}" alt="{firm_name}" '
            f'style="height:32px;max-width:160px;object-fit:contain;margin-right:20px;" '
            f'onerror="this.style.display=\'none\';document.getElementById(\'topnav-name\').style.display=\'block\'"/>'
            f'<span class="preview-firm-name" id="topnav-name" style="display:none">{firm_name}</span>'
        )
    else:
        topnav_brand = f'<span class="preview-firm-name" id="topnav-name">{firm_name}</span>'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{firm_name} — Estate Planning Intake</title>
<script defer src="/_vercel/insights/script.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{gf}&display=swap"/>
<style>
:root {{
  --firm-primary: {primary};
  --firm-primary-dark: {primary_dark};
  --firm-primary-container: {primary_container};
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
html,body{{height:100%;}}
body{{background:#ffffff;font-family:'Source Sans 3',sans-serif;display:flex;justify-content:center;align-items:flex-start;min-height:100vh;padding:24px 12px;}}
#donna-app{{
  --cream:#f5f5f5;--cream-mid:#f0f0f0;--cream-dark:#e8e8e8;--cream-border:#e0e0e0;--cream-hover:#f5f5f5;
  --text-dark:#1e1209;--text-mid:#5c4d3a;--text-muted:#9a8a75;
  position:relative;font-family:'Inter',sans-serif;border-radius:16px;overflow:hidden;
  box-shadow:0 4px 60px rgba(30,18,9,0.15);width:1080px;max-width:100%;height:800px;
}}
#donna-app button{{cursor:pointer;font-family:inherit;border:none;background:none;}}
#donna-app input,#donna-app textarea,#donna-app select{{font-family:inherit;}}
#donna-app .preview-page{{display:flex;flex-direction:column;height:100%;overflow:hidden;background:#ffffff;border-radius:16px;border:1px solid var(--cream-border);font-family:'Source Sans 3',sans-serif;}}
#donna-app .preview-topnav{{display:flex;align-items:center;padding:0 20px;background:#f8f8f8;border-bottom:1px solid var(--cream-border);flex-shrink:0;height:52px;gap:0;}}
#donna-app .preview-firm-name{{font-family:{heading_css};font-size:1.15rem;color:var(--firm-primary);font-weight:700;margin-right:20px;white-space:nowrap;}}
#donna-app .preview-part-tabs{{display:flex;gap:0;flex:1;height:100%;overflow:hidden;}}
#donna-app .preview-part-tab{{padding:0 12px;font-size:0.76rem;font-weight:500;color:#5c4d3a;border:none;background:none;cursor:pointer;height:100%;border-bottom:2.5px solid transparent;white-space:nowrap;font-family:'Inter',sans-serif;transition:color 0.12s;}}
#donna-app .preview-part-tab.pv-tab-active{{color:var(--firm-primary);border-bottom-color:var(--firm-primary);font-weight:600;}}
#donna-app .preview-draft-saved{{display:flex;align-items:center;gap:5px;font-size:0.74rem;color:#5c4d3a;white-space:nowrap;margin-left:12px;flex-shrink:0;}}
#donna-app .preview-draft-dot{{width:7px;height:7px;border-radius:50%;background:#15803d;flex-shrink:0;}}
#donna-app .preview-body{{flex:1;overflow:hidden;display:flex;}}
#donna-app .preview-sidebar{{width:200px;flex-shrink:0;background:#f8f8f8;border-right:1px solid var(--cream-border);display:flex;flex-direction:column;padding:20px 12px;overflow-y:auto;}}
#donna-app .preview-sidebar::-webkit-scrollbar{{width:4px;}}
#donna-app .preview-sidebar::-webkit-scrollbar-thumb{{background:#c4c9d4;border-radius:2px;}}
#donna-app .preview-page-link{{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;font-size:0.78rem;font-weight:500;color:#5c4d3a;margin-bottom:1px;cursor:pointer;transition:background 0.12s;}}
#donna-app .preview-page-link:not(.pv-active):hover{{background:var(--cream-hover);}}
#donna-app .preview-page-link.pv-active{{background:var(--firm-primary);color:white;}}
#donna-app .pv-icon{{opacity:0.5;display:flex;align-items:center;flex-shrink:0;}}
#donna-app .pv-checkmark{{display:flex;align-items:center;justify-content:center;width:14px;height:14px;border-radius:50%;background:var(--firm-primary);flex-shrink:0;}}
#donna-app .preview-page-link.pv-active .pv-icon{{opacity:1;}}
#donna-app .preview-main{{flex:1;overflow-y:auto;display:flex;flex-direction:column;}}
#donna-app .preview-main::-webkit-scrollbar{{width:4px;}}
#donna-app .preview-main::-webkit-scrollbar-thumb{{background:#c4c9d4;border-radius:2px;}}
#donna-app .preview-content-wrap{{flex:1;padding:20px 24px;overflow-y:auto;background:#ffffff;}}
#donna-app .preview-form{{background:#f9f9f9;border-radius:12px;padding:28px 32px;max-width:680px;width:100%;box-shadow:0 1px 8px rgba(0,0,0,0.06);}}
#donna-app .preview-form-title{{font-size:1.4rem;font-weight:700;color:#1e1209;margin-bottom:4px;font-family:{heading_css};}}
#donna-app .preview-page-sub{{font-size:0.82rem;color:#5c4d3a;margin-bottom:24px;line-height:1.5;}}
#donna-app .preview-section-heading{{font-size:0.95rem;font-weight:700;color:#1e1209;border-left:3px solid var(--firm-primary);padding-left:10px;margin:20px 0 14px;}}
#donna-app .preview-field-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px 16px;margin-bottom:12px;}}
#donna-app .preview-field-grid.cols-4{{grid-template-columns:repeat(4,1fr);}}
#donna-app .preview-field-grid.cols-1{{grid-template-columns:1fr;}}
#donna-app .preview-field{{margin-bottom:0;}}
#donna-app .preview-field.full{{grid-column:1/-1;}}
#donna-app .preview-field label{{display:block;font-size:0.76rem;font-weight:600;color:#5c4d3a;margin-bottom:5px;}}
#donna-app .preview-field .req{{color:#ba1a1a;margin-left:2px;}}
#donna-app .preview-field input{{width:100%;padding:9px 12px;border:1.5px solid var(--cream-border);border-radius:8px;font-size:0.85rem;outline:none;transition:border-color 0.15s;background:#ffffff;color:#1e1209;}}
#donna-app .preview-field input:focus{{border-color:var(--firm-primary);}}
#donna-app .preview-field textarea{{width:100%;padding:9px 12px;border:1.5px solid var(--cream-border);border-radius:8px;font-size:0.85rem;outline:none;resize:vertical;min-height:76px;transition:border-color 0.15s;background:#ffffff;color:#1e1209;}}
#donna-app .preview-field textarea:focus{{border-color:var(--firm-primary);}}
#donna-app .preview-field select{{width:100%;padding:9px 12px;border:1.5px solid var(--cream-border);border-radius:8px;font-size:0.85rem;outline:none;background:#ffffff;color:#1e1209;cursor:pointer;transition:border-color 0.15s;appearance:none;background-image:url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%23565e6c' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center;padding-right:30px;}}
#donna-app .preview-field select:focus{{border-color:var(--firm-primary);}}
#donna-app .preview-radio-group{{display:flex;gap:8px;flex-wrap:wrap;}}
#donna-app .preview-radio-pill{{padding:7px 18px;border:1.5px solid var(--cream-border);border-radius:20px;font-size:0.82rem;font-weight:500;color:#5c4d3a;cursor:pointer;transition:all 0.15s;background:#ffffff;font-family:'Source Sans 3',sans-serif;}}
#donna-app .preview-radio-pill.pv-radio-selected{{border-color:var(--firm-primary);background:var(--firm-primary-container);color:var(--firm-primary);font-weight:600;}}
#donna-app .upload-zone{{border:1.5px dashed #c4c9d4;border-radius:8px;padding:18px;text-align:center;color:#5c4d3a;font-size:0.82rem;cursor:pointer;transition:all 0.15s;}}
#donna-app .upload-zone:hover{{border-color:var(--firm-primary);color:var(--firm-primary);}}
#donna-app .preview-error{{display:none;font-size:0.78rem;color:#ba1a1a;background:#fdecea;border-radius:7px;padding:8px 12px;margin-bottom:12px;border:1px solid #f5c2c7;}}
#donna-app .preview-nav{{display:flex;gap:10px;margin-top:24px;align-items:center;}}
#donna-app .preview-next-btn{{padding:10px 28px;background:var(--firm-primary);color:white;border-radius:8px;font-size:0.86rem;font-weight:600;border:none;cursor:pointer;font-family:'Source Sans 3',sans-serif;transition:background 0.15s;}}
#donna-app .preview-next-btn:hover{{background:var(--firm-primary-dark);}}
#donna-app .preview-back-link{{font-size:0.82rem;color:#5c4d3a;cursor:pointer;display:flex;align-items:center;gap:4px;white-space:nowrap;background:none;border:none;font-family:'Source Sans 3',sans-serif;padding:0;transition:color 0.15s;}}
#donna-app .preview-back-link:hover{{color:#1e1209;}}
#donna-app .preview-success{{display:none;flex-direction:column;align-items:center;justify-content:center;padding:48px 32px;text-align:center;}}
#donna-app .success-icon{{width:56px;height:56px;border-radius:50%;background:#e4f0ea;display:flex;align-items:center;justify-content:center;margin-bottom:16px;}}
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
</style>
</head>
<body>
<div id="donna-app">
<div class="preview-page" id="preview-page">
  <div class="preview-topnav">
    {topnav_brand}
    <div class="preview-part-tabs" id="preview-part-tabs"></div>
    <div class="preview-draft-saved"><span class="preview-draft-dot"></span>Draft saved</div>
  </div>
  <div class="preview-body">
    <div class="preview-sidebar" id="preview-sidebar"></div>
    <div class="preview-main">
      <div class="preview-content-wrap">
        <div class="preview-form">
          <div id="preview-form-container">
            <div class="preview-form-title" id="preview-page-title">Let&rsquo;s get started</div>
            <div class="preview-page-sub" id="preview-page-sub"></div>
            <div class="preview-error" id="preview-error">Please fill in all required fields.</div>
            <div id="preview-fields"></div>
            <div class="preview-nav">
              <button class="preview-back-link" id="preview-back-btn" onclick="prevPreviewPage()" style="display:none">&#8592; Back</button>
              <button class="preview-next-btn" id="preview-next-btn" onclick="nextPreviewPage()">Continue &#8594;</button>
            </div>
          </div>
          <div class="preview-success" id="preview-success">
            <div class="success-icon">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#2a7a4f" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            </div>
            <div style="font-size:1.15rem;font-weight:700;color:#1e1209;margin-bottom:8px">Questionnaire submitted</div>
            <div style="font-size:0.84rem;color:#5c4d3a;line-height:1.6">Thank you. A lawyer will review your answers and be in touch shortly.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
</div>
<script>
(function(){{
var currentFormName='Estate Planning';
var currentPreviewPage=0;
var previewFormData={{}};
var formState={{
  'Estate Planning':{{
    parts:['Identity & Assets','Business & Insurance','Wills & Executors','EPA & Medical'],
    pagePartMap:[0,0,0,0,0,1,2,3,3],
    pages:[
      {{title:"Let's get started",sub:'Please provide your contact details so we can get started.',sections:[
        {{heading:'Name & Contact',grid:2,fields:[
          {{label:'First Name',type:'text',required:true}},
          {{label:'Last Name',type:'text',required:false}},
          {{label:'Email Address',type:'email',required:true,alwaysRequired:true,full:true}},
          {{label:'Mobile Number',type:'tel',required:true}},
          {{label:'Home Phone',type:'tel',required:false}}
        ]}}
      ]}},
      {{title:'Welcome',sub:'Tell us about the nature of this matter.',sections:[
        {{heading:'Engagement',grid:2,fields:[
          {{label:'Who is this matter for?',type:'select',required:true,full:true,options:['','Single Client','Couple (Joint Matter)','Couple (Separate Matters)']}},
          {{label:'State',type:'select',required:true,options:['','AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY']}},
          {{label:'Preferred Contact Method',type:'select',required:false,options:['','Email','Phone','Either']}},
          {{label:'Is this matter urgent?',type:'yesno',required:false,full:true}},
          {{label:'How did you hear about us?',type:'select',required:false,full:true,options:['','Google','Referral from friend / colleague','Social media','Existing client','Other']}}
        ]}}
      ]}},
      {{title:'C1 — Personal Details',sub:'Please provide your personal information as accurately as possible.',sections:[
        {{heading:'Name',grid:4,fields:[
          {{label:'Title',type:'select',required:false,options:['','Mr','Mrs','Ms','Miss','Dr','Prof']}},
          {{label:'First Name',type:'text',required:true}},
          {{label:'Middle Name',type:'text',required:false}},
          {{label:'Last Name',type:'text',required:true}},
          {{label:'Preferred Name / Nickname',type:'text',required:false,full:true}}
        ]}},
        {{heading:'Identity',grid:2,fields:[
          {{label:'Date of Birth',type:'text',required:true}},
          {{label:'Place of Birth',type:'text',required:false}},
          {{label:'Gender',type:'select',required:false,options:['','Male','Female','Non-binary','Prefer not to say']}},
          {{label:'Citizenship / Nationality',type:'text',required:false}},
          {{label:'U.S. Citizen?',type:'yesno',required:false,full:true}}
        ]}},
        {{heading:'Contact & Address',grid:1,fields:[
          {{label:'Residential Address',type:'text',required:true,full:true}},
          {{label:'Occupation',type:'text',required:false,full:true}},
          {{label:'Relationship Status',type:'select',required:false,full:true,options:['','Single','Married','Domestic Partner','Separated','Divorced','Widowed']}}
        ]}}
      ]}},
      {{title:'Children',sub:'Tell us about any children or dependants.',sections:[
        {{heading:'Children & Dependants',grid:1,fields:[
          {{label:'Do you have children?',type:'yesno',required:true,full:true}},
          {{label:'Do you have grandchildren?',type:'yesno',required:false,full:true}},
          {{label:'Do you have other dependants?',type:'yesno',required:false,full:true}},
          {{label:'Any special needs beneficiaries?',type:'select',required:false,full:true,options:['','Yes','No','Not sure']}}
        ]}}
      ]}},
      {{title:'Financial Overview',sub:"Let us know about your financial position.",sections:[
        {{heading:'Assets & Liabilities',grid:1,fields:[
          {{label:'Do you own real estate?',type:'yesno',required:false,full:true}},
          {{label:'Do you have retirement accounts (IRA, 401k, etc.)?',type:'yesno',required:false,full:true}},
          {{label:'Do you have a mortgage or loans?',type:'yesno',required:false,full:true}},
          {{label:'Estimated net worth range',type:'select',required:false,full:true,options:['','Under $500K','$500K–$1M','$1M–$2M','$2M–$5M','Over $5M','Prefer not to say']}}
        ]}}
      ]}},
      {{title:'Business & Insurance',sub:'Tell us about any business interests and insurance policies.',sections:[
        {{heading:'Business',grid:1,fields:[
          {{label:'Do you own or co-own a business?',type:'yesno',required:false,full:true}},
          {{label:'Are you a partner or officer in any company?',type:'yesno',required:false,full:true}},
          {{label:'Are you involved in any trusts?',type:'yesno',required:false,full:true}}
        ]}},
        {{heading:'Insurance',grid:1,fields:[
          {{label:'Do you have life insurance?',type:'yesno',required:false,full:true}},
          {{label:'Financial Advisor Name',type:'text',required:false,full:true}},
          {{label:'Supporting documents',type:'upload',required:false,full:true}}
        ]}}
      ]}},
      {{title:'Wills & Executors',sub:"Tell us about your will structure and who you'd like to appoint.",sections:[
        {{heading:'Existing Will',grid:1,fields:[
          {{label:'Do you have an existing will?',type:'yesno',required:false,full:true}}
        ]}},
        {{heading:'Executors',grid:2,fields:[
          {{label:'Primary Executor — Full Name',type:'text',required:false,full:true}},
          {{label:'Alternate Executor — Full Name',type:'text',required:false,full:true}}
        ]}},
        {{heading:'Beneficiaries',grid:2,fields:[
          {{label:'Primary Beneficiary — Full Name',type:'text',required:false}},
          {{label:'Relationship to You',type:'select',required:false,options:['','Spouse / Partner','Child','Sibling','Parent','Friend','Charity','Other']}}
        ]}}
      ]}},
      {{title:'Healthcare Directives',sub:'Tell us about your wishes for healthcare and financial decision-making.',sections:[
        {{heading:'Healthcare',grid:1,fields:[
          {{label:'Do you want a Healthcare Power of Attorney?',type:'yesno',required:false,full:true}},
          {{label:'Do you have an Advance Healthcare Directive / Living Will?',type:'yesno',required:false,full:true}},
          {{label:'Organ donation preference',type:'select',required:false,full:true,options:['','Yes — all organs','Yes — specific organs only','No']}}
        ]}},
        {{heading:'Financial & Other',grid:1,fields:[
          {{label:'Do you want a Financial Power of Attorney / Durable POA?',type:'yesno',required:false,full:true}},
          {{label:'Burial preference',type:'select',required:false,full:true,options:['','Burial','Cremation','No preference']}}
        ]}}
      ]}},
      {{title:'Declaration',sub:'Please review and confirm the accuracy of your answers.',sections:[
        {{heading:'Additional Information',grid:1,fields:[
          {{label:'Additional information for your attorney',type:'textarea',required:false,full:true}}
        ]}},
        {{heading:'Confirmation',grid:1,fields:[
          {{label:'I confirm the information provided is true and correct',type:'checkbox',required:true,full:true}},
          {{label:'Signature (type your full name)',type:'text',required:true,full:true}}
        ]}}
      ]}}
    ]
  }}
}};

var pageIcons=[
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 2v4M16 2v4M3 10h18"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4L12 2z"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3h-8a2 2 0 0 0-2 2v2h12V5a2 2 0 0 0-2-2z"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>'
];

function renderPreviewSidebar(){{
  var form=formState[currentFormName];
  var sb=document.getElementById('preview-sidebar');
  if(!sb) return;
  var currentPart=form.pagePartMap[currentPreviewPage];
  var html='';var lastPart=-1;
  form.pages.forEach(function(p,i){{
    var thisPart=form.pagePartMap[i];
    if(thisPart!==lastPart){{if(lastPart!==-1) html+='<div style="height:6px"></div>';lastPart=thisPart;}}
    var cls='preview-page-link';
    if(i===currentPreviewPage) cls+=' pv-active';
    else if(i<currentPreviewPage) cls+=' pv-done';
    var iconHtml=(i<currentPreviewPage)
      ?'<span class="pv-checkmark"><svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></span>'
      :'<span class="pv-icon">'+(pageIcons[i]||'')+'</span>';
    html+='<div class="'+cls+'" onclick="jumpToPreviewPage('+i+')">'+iconHtml+p.title+'</div>';
  }});
  sb.innerHTML=html;
  var tabsEl=document.getElementById('preview-part-tabs');
  if(tabsEl&&form.parts){{
    tabsEl.innerHTML=form.parts.map(function(pt,pi){{
      var first=0;
      for(var j=0;j<form.pagePartMap.length;j++){{if(form.pagePartMap[j]===pi){{first=j;break;}}}}
      return '<button class="preview-part-tab'+(pi===currentPart?' pv-tab-active':'')+'" onclick="jumpToPreviewPage('+first+')">'+pt+'</button>';
    }}).join('');
  }}
}}
function makeFieldEl(field,fidx,sIdx){{
  var key=currentPreviewPage+'_'+sIdx+'_'+fidx;
  var div=document.createElement('div');
  div.className='preview-field'+(field.full?' full':'');
  if(field.type==='yesno'){{
    if(field.label){{var lbl=document.createElement('label');lbl.textContent=field.label;if(field.required){{var r=document.createElement('span');r.className='req';r.textContent=' *';lbl.appendChild(r);}}div.appendChild(lbl);}}
    var grp=document.createElement('div');grp.className='preview-radio-group';
    ['Yes','No'].forEach(function(opt){{
      var btn=document.createElement('button');btn.type='button';
      btn.className='preview-radio-pill'+(previewFormData[key]===opt?' pv-radio-selected':'');
      btn.textContent=opt;btn.dataset.key=key;btn.dataset.required=field.required?'1':'0';btn.dataset.value=opt;
      btn.onclick=function(){{previewFormData[this.dataset.key]=this.dataset.value;grp.querySelectorAll('.preview-radio-pill').forEach(function(b){{b.classList.remove('pv-radio-selected');}});this.classList.add('pv-radio-selected');}};
      grp.appendChild(btn);
    }});
    div.appendChild(grp);return div;
  }}
  if(field.type!=='checkbox'){{var lbl2=document.createElement('label');lbl2.textContent=field.label;if(field.required){{var r2=document.createElement('span');r2.className='req';r2.textContent=' *';lbl2.appendChild(r2);}}div.appendChild(lbl2);}}
  if(field.type==='text'||field.type==='email'||field.type==='tel'){{
    var inp=document.createElement('input');inp.type=field.type==='text'?'text':field.type;
    inp.value=previewFormData[key]||'';inp.placeholder=field.label;
    inp.dataset.key=key;inp.dataset.required=field.required?'1':'0';
    inp.oninput=function(){{previewFormData[this.dataset.key]=this.value;}};
    div.appendChild(inp);
  }}else if(field.type==='textarea'){{
    var ta=document.createElement('textarea');ta.value=previewFormData[key]||'';ta.placeholder='Your answer…';
    ta.dataset.key=key;ta.dataset.required=field.required?'1':'0';
    ta.oninput=function(){{previewFormData[this.dataset.key]=this.value;}};
    div.appendChild(ta);
  }}else if(field.type==='select'){{
    var sel=document.createElement('select');sel.dataset.key=key;sel.dataset.required=field.required?'1':'0';
    (field.options||['']).forEach(function(opt){{var o=document.createElement('option');o.value=opt;o.textContent=opt||'— Select —';sel.appendChild(o);}});
    sel.value=previewFormData[key]||'';
    sel.onchange=function(){{previewFormData[this.dataset.key]=this.value;}};
    div.appendChild(sel);
  }}else if(field.type==='upload'){{
    var zone=document.createElement('div');zone.className='upload-zone';
    zone.innerHTML='<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom:5px;display:block;margin-left:auto;margin-right:auto"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>Click to upload or drag and drop';
    div.appendChild(zone);
  }}else if(field.type==='checkbox'){{
    var cLabel=document.createElement('label');
    cLabel.style.cssText='display:flex;align-items:flex-start;gap:10px;cursor:pointer;font-size:0.84rem;color:#1e1209;line-height:1.45;';
    var chk=document.createElement('input');chk.type='checkbox';
    chk.style.cssText='margin-top:2px;accent-color:var(--firm-primary);width:16px;height:16px;flex-shrink:0;cursor:pointer;';
    chk.checked=previewFormData[key]==='1';chk.dataset.key=key;chk.dataset.required=field.required?'1':'0';
    chk.onchange=function(){{previewFormData[this.dataset.key]=this.checked?'1':'';}};
    var cText=document.createElement('span');cText.textContent=field.label;
    if(field.required){{var cReq=document.createElement('span');cReq.style.color='#ba1a1a';cReq.textContent=' *';cText.appendChild(cReq);}}
    cLabel.appendChild(chk);cLabel.appendChild(cText);div.appendChild(cLabel);
  }}
  return div;
}}
function renderPreviewPage(){{
  var form=formState[currentFormName];
  var total=form.pages.length;
  var page=form.pages[currentPreviewPage];
  document.getElementById('preview-page-title').textContent=page.title;
  var subEl=document.getElementById('preview-page-sub');if(subEl) subEl.textContent=page.sub||'';
  document.getElementById('preview-error').style.display='none';
  renderPreviewSidebar();
  var container=document.getElementById('preview-fields');container.innerHTML='';
  (page.sections||[{{fields:page.fields||[]}}]).forEach(function(section,sIdx){{
    if(section.heading){{var h=document.createElement('div');h.className='preview-section-heading';h.textContent=section.heading;container.appendChild(h);}}
    var cols=section.grid||1;
    var gridClass=cols===4?'preview-field-grid cols-4':cols===2?'preview-field-grid':'preview-field-grid cols-1';
    var grid=document.createElement('div');grid.className=gridClass;
    (section.fields||[]).forEach(function(field,fidx){{grid.appendChild(makeFieldEl(field,fidx,sIdx));}});
    container.appendChild(grid);
  }});
  var backBtn=document.getElementById('preview-back-btn');
  var nextBtn=document.getElementById('preview-next-btn');
  backBtn.style.display=currentPreviewPage===0?'none':'';
  if(currentPreviewPage===total-1){{nextBtn.textContent='Submit Questionnaire';nextBtn.onclick=submitPreviewForm;}}
  else{{nextBtn.textContent='Continue →';nextBtn.onclick=nextPreviewPage;}}
}}
function validatePage(){{
  var ok=true;
  document.querySelectorAll('#preview-fields [data-required="1"]').forEach(function(el){{
    if(el.tagName==='BUTTON'){{var grp=el.closest('.preview-radio-group');if(grp&&!grp.querySelector('.pv-radio-selected')) ok=false;}}
    else{{var val=el.type==='checkbox'?(el.checked?'1':''):el.value;if(!val||val.trim()==='') ok=false;}}
  }});
  return ok;
}}
window.jumpToPreviewPage=function(idx){{document.getElementById('preview-error').style.display='none';currentPreviewPage=idx;renderPreviewPage();}};
function nextPreviewPage(){{if(!validatePage()){{document.getElementById('preview-error').style.display='block';return;}}currentPreviewPage++;renderPreviewPage();}}
window.nextPreviewPage=nextPreviewPage;
function prevPreviewPage(){{currentPreviewPage--;renderPreviewPage();}}
window.prevPreviewPage=prevPreviewPage;
function submitPreviewForm(){{
  if(!validatePage()){{document.getElementById('preview-error').style.display='block';return;}}
  document.getElementById('preview-form-container').style.display='none';
  document.getElementById('preview-success').style.display='flex';
}}
window.submitPreviewForm=submitPreviewForm;
document.addEventListener('DOMContentLoaded',function(){{renderPreviewPage();}});
}})();
</script>
</body>
</html>'''

# ── Load CSV ──────────────────────────────────────────────────────────

with open(CSV_PATH, 'rb') as f:
    content = f.read().replace(b'\x00', b'')
rows = list(csv.DictReader(io.StringIO(content.decode('utf-8', errors='replace'))))

companies = {}
for r in rows:
    cn = r['Company Name'].strip()
    if cn and cn not in companies:
        companies[cn] = r

print(f'Loaded {len(companies)} unique firms from Apollo CSV')

existing_slugs = set(f.replace('.html', '') for f in os.listdir(PREVIEWS_DIR) if f.endswith('.html'))

firms_to_process = []
for company_name, row in companies.items():
    slug = slugify(company_name)
    firms_to_process.append({
        'name': company_name,
        'slug': slug,
        'website': row.get('Website', '').strip(),
        'first_name': row.get('First Name', '').strip(),
        'last_name': row.get('Last Name', '').strip(),
        'title': row.get('Title', '').strip(),
        'email': row.get('Email', '').strip(),
        'city': row.get('City', '').strip(),
        'state': row.get('State', '').strip(),
        'linkedin_person': row.get('Person Linkedin Url', '').strip(),
        'linkedin_company': row.get('Company Linkedin Url', '').strip(),
        'technologies': row.get('Technologies', ''),
    })

# Separate: new firms vs already-generated ones
new_firms = [f for f in firms_to_process if f['slug'] not in existing_slugs]
existing_firms = [f for f in firms_to_process if f['slug'] in existing_slugs]
print(f'New firms to generate: {len(new_firms)}')
print(f'Already existing (will re-research for logo+color only): {len(existing_firms)}')

# Re-research ALL firms (to get logo + color for index)
all_firms = firms_to_process

# ── Process firms ─────────────────────────────────────────────────────

def process_firm(firm):
    name = firm['name']
    slug = firm['slug']
    website = firm['website']
    is_new = slug not in existing_slugs

    color, logo = research_firm(website)

    if color:
        primary = color
        primary_dark = darken_hex(color)
        primary_container = lighten_hex(color)
        used_fallback = False
    else:
        primary = FALLBACK_PRIMARY
        primary_dark = FALLBACK_DARK
        primary_container = FALLBACK_CONTAINER
        used_fallback = True

    if is_new:
        html = make_html(name, primary, primary_dark, primary_container, logo)
        out_path = os.path.join(PREVIEWS_DIR, f'{slug}.html')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
    else:
        # Re-write existing file with logo if found
        out_path = os.path.join(PREVIEWS_DIR, f'{slug}.html')
        if logo and os.path.exists(out_path):
            html = make_html(name, primary, primary_dark, primary_container, logo)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(html)

    return {
        'name': name,
        'slug': slug,
        'color': primary,
        'fallback': used_fallback,
        'logo_url': logo,
        'website': website,
        'first_name': firm['first_name'],
        'last_name': firm['last_name'],
        'title': firm['title'],
        'email': firm['email'],
        'city': firm['city'],
        'state': firm['state'],
        'linkedin_person': firm['linkedin_person'],
        'linkedin_company': firm['linkedin_company'],
    }

print(f'\nResearching all {len(all_firms)} firms (logo + color, 20 parallel)...\n')

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(process_firm, firm): firm for firm in all_firms}
    for i, future in enumerate(concurrent.futures.as_completed(futures)):
        result = future.result()
        results.append(result)
        if (i + 1) % 50 == 0 or (i + 1) == len(all_firms):
            logos_found = sum(1 for r in results if r.get('logo_url'))
            colors_found = sum(1 for r in results if not r['fallback'])
            print(f'  {i+1}/{len(all_firms)} done — logos: {logos_found}, colors: {colors_found}')

with open(SUMMARY_OUT, 'w') as f:
    json.dump(results, f, indent=2)

logos_found = sum(1 for r in results if r.get('logo_url'))
colors_found = sum(1 for r in results if not r['fallback'])
print(f'\n{"="*60}')
print(f'DONE: {len(results)} firms researched')
print(f'  Logos found:  {logos_found}/{len(results)}')
print(f'  Colors found: {colors_found}/{len(results)}')
print(f'Summary → {SUMMARY_OUT}')
print(f'\nNow run generate_index.py to rebuild index.html')
