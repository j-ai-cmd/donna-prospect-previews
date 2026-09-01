#!/usr/bin/env python3
"""
Research original 83 firms from the cold email spreadsheet.
Pulls website + LinkedIn, scrapes logo + brand color,
saves to /tmp/original_firm_data.json for use by generate_index.py.
"""
import re, json, colorsys, subprocess, sys
from urllib.parse import urljoin
import concurrent.futures

def ensure(*pkgs):
    for pkg in pkgs:
        try: __import__(pkg.split('[')[0].replace('-','_'))
        except ImportError: subprocess.run([sys.executable,'-m','pip','install',pkg,'-q'],check=True)

ensure('requests', 'beautifulsoup4', 'openpyxl')

import requests
from bs4 import BeautifulSoup
import openpyxl

XLSX_PATH  = '/Users/jaidhingra/Downloads/cold email research (1).xlsx'
DRAFT_DATA = '/tmp/draft_data.json'
OUT_PATH   = '/tmp/original_firm_data.json'

def slugify(name):
    s = name.lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    return re.sub(r'-+', '-', s).strip('-')

HEX_RE = re.compile(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36'}

def hex_to_hsv(h):
    h = h.lstrip('#')
    if len(h) == 3: h = ''.join(c*2 for c in h)
    if len(h) != 6: return None
    try:
        r,g,b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
        return colorsys.rgb_to_hsv(r,g,b)
    except: return None

def is_good_color(c):
    hsv = hex_to_hsv(c)
    return hsv and 0.15 <= hsv[2] <= 0.97 and hsv[1] >= 0.15

def fetch(url, timeout=8):
    if not url: return None, None
    if not url.startswith('http'): url = 'https://' + url
    try:
        r = requests.get(url, timeout=timeout, headers=HEADERS, allow_redirects=True)
        r.raise_for_status()
        return r.text, r.url
    except: return None, None

def scrape_logo(html, base_url):
    if not html: return None
    soup = BeautifulSoup(html, 'html.parser')
    def abs_url(u):
        if not u or u.startswith('data:'): return None
        return urljoin(base_url, u.strip())
    for img in soup.find_all('img'):
        combined = (img.get('src','') + img.get('alt','') + img.get('id','') + ' '.join(img.get('class',[]))).lower()
        if 'logo' in combined:
            url = abs_url(img.get('src',''))
            if url and 'favicon' not in url.lower(): return url
    og = soup.find('meta', property='og:image') or soup.find('meta', attrs={'name':'og:image'})
    if og:
        url = abs_url(og.get('content',''))
        if url: return url
    for rel in ['apple-touch-icon','apple-touch-icon-precomposed']:
        link = soup.find('link', rel=lambda r: r and rel in r)
        if link:
            url = abs_url(link.get('href',''))
            if url: return url
    return None

def scrape_color(html):
    if not html: return None
    soup = BeautifulSoup(html, 'html.parser')
    meta = soup.find('meta', attrs={'name':'theme-color'})
    if meta:
        c = meta.get('content','').strip()
        if c.startswith('#') and is_good_color(c): return c
    styles = ' '.join(t.string or '' for t in soup.find_all('style'))
    for pat in [
        r'--(?:primary|brand|accent|color-primary|main-color|brand-color|site-color)[^:]*:\s*(#[0-9a-fA-F]{3,6})',
        r'--(?:color|clr)-(?:primary|accent|brand)[^:]*:\s*(#[0-9a-fA-F]{3,6})',
    ]:
        m = re.search(pat, styles, re.IGNORECASE)
        if m and is_good_color(m.group(1)): return m.group(1)
    for el in soup.find_all(['button','a','header','nav'], limit=60):
        for m in HEX_RE.finditer(el.get('style','')):
            c = '#' + m.group(1)
            if is_good_color(c): return c
    colors = [(hex_to_hsv('#'+m.group(1))[1], '#'+m.group(1)) for m in HEX_RE.finditer(styles) if is_good_color('#'+m.group(1)) and hex_to_hsv('#'+m.group(1))]
    if colors: return max(colors)[1]
    return None

# Load the spreadsheet
wb = openpyxl.load_workbook(XLSX_PATH)
firm_data = {}

for ws in wb.worksheets:
    rows = list(ws.iter_rows(values_only=True))
    if not rows: continue
    hdrs = [str(c).strip() if c else '' for c in rows[0]]
    def col(row, name):
        try: return str(row[hdrs.index(name)]).strip() if name in hdrs and row[hdrs.index(name)] and str(row[hdrs.index(name)]) != 'None' else ''
        except: return ''
    for row in rows[1:]:
        company = col(row, 'Company')
        if not company: continue
        slug = slugify(company)
        if slug not in firm_data:
            firm_data[slug] = {
                'slug': slug,
                'firm_name': company,
                'first_name': col(row, 'First Name'),
                'website': col(row, 'Website'),
                'linkedin_person': col(row, 'Person LinkedIn'),
                'linkedin_company': col(row, 'Company LinkedIn'),
                'logo_url': None,
                'color': None,
            }

print(f'Loaded {len(firm_data)} firms from spreadsheet')

def research(item):
    slug = item['slug']
    website = item['website']
    html, final_url = fetch(website)
    color = scrape_color(html) if html else None
    logo  = scrape_logo(html, final_url or website) if html else None
    return {**item, 'color': color, 'logo_url': logo}

print(f'Researching {len(firm_data)} firms...')
results = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    futures = {ex.submit(research, v): k for k,v in firm_data.items()}
    for i, fut in enumerate(concurrent.futures.as_completed(futures)):
        r = fut.result()
        results[r['slug']] = r
        if (i+1) % 20 == 0 or (i+1) == len(firm_data):
            logos  = sum(1 for x in results.values() if x.get('logo_url'))
            colors = sum(1 for x in results.values() if x.get('color'))
            print(f'  {i+1}/{len(firm_data)} — logos: {logos}, colors: {colors}')

with open(OUT_PATH, 'w') as f:
    json.dump(results, f, indent=2)

print(f'\nSaved → {OUT_PATH}')
