#!/usr/bin/env python3
"""
One-off batch: LinkedIn ICP connections (estate planning / probate attorneys).
Researches logo+color, builds preview forms, pushes to GitHub, prints preview links.
"""
import re, os, json, colorsys, subprocess, sys
from urllib.parse import urljoin
import concurrent.futures

def ensure(*pkgs):
    for pkg in pkgs:
        try: __import__(pkg.split('[')[0].replace('-','_'))
        except ImportError: subprocess.run([sys.executable,'-m','pip','install',pkg,'-q'],check=True)
ensure('requests','beautifulsoup4')
import requests
from bs4 import BeautifulSoup

SCRIPT_DIR   = '/tmp/donna-prospect-previews'
PREVIEWS_DIR = os.path.join(SCRIPT_DIR, 'previews')
PREVIEW_BASE = 'https://donna-previews.vercel.app/previews'
os.makedirs(PREVIEWS_DIR, exist_ok=True)

FIRMS = [
    {'first_name': 'Meaghan',  'name': 'Miracle Law PLLC',                 'website': 'miracleattorney.com',       'linkedin': 'https://www.linkedin.com/in/meaghan-miracle-94789b13/'},
    {'first_name': 'Kaitlyn',  'name': 'Liberty Legacy Law Group',         'website': 'mdestateplanninglaw.com',   'linkedin': 'https://www.linkedin.com/in/kaitlynptauber/'},
    {'first_name': 'Alexander','name': 'Full Circle Estate Planning and Probate', 'website': 'fullcircleestateplanning.com', 'linkedin': 'https://www.linkedin.com/in/alexander-robinson-55747469/'},
    {'first_name': 'Claire',   'name': 'Yanowitz Law Firm, PLLC',          'website': 'yanowitzlaw.com',           'linkedin': 'https://www.linkedin.com/in/claire-langton-yanowitz-96b7a2aa/'},
    {'first_name': 'DeDe',     'name': 'The Soto Law Group',               'website': 'thesotolawgroup.com',       'linkedin': 'https://www.linkedin.com/in/dedesoto/'},
    {'first_name': 'Crissy',   'name': 'LEEP Law Group',                   'website': 'leeplawgroup.com',          'linkedin': 'https://www.linkedin.com/in/crissyvenezia/'},
    {'first_name': 'Whitney',  'name': 'Whitney Thomas Law Firm',          'website': 'whitneythomaslaw.com',      'linkedin': 'https://www.linkedin.com/in/whitneythomasesq/'},
    {'first_name': 'Kevin',    'name': 'The Art of Planning, PLLC',        'website': 'artofplanninglaw.com',      'linkedin': 'https://www.linkedin.com/in/kevinmdonovanjd/'},
    {'first_name': 'James',    'name': 'Law Office of James Burns',        'website': 'jamesburnslaw.com',         'linkedin': 'https://www.linkedin.com/in/jambur/'},
    {'first_name': 'Ethel',    'name': 'Wills and Trusts LLC',             'website': 'willsandtrusts.net',        'linkedin': 'https://www.linkedin.com/in/ethel-mitchell-b5369356/'},
    {'first_name': 'Matthew',  'name': 'DeGioia Law, PLLC',                'website': 'degioialaw.com',            'linkedin': 'https://www.linkedin.com/in/matthew-degioia-esq-986775175/'},
    {'first_name': 'Phil',     'name': 'Tamarisk Legal Advisors',          'website': 'tamarisklegal.com',         'linkedin': 'https://www.linkedin.com/in/philharwood/'},
    {'first_name': 'Melenni',  'name': 'Balbach & Davenport Legal',        'website': 'balbachdavenportlegal.com', 'linkedin': 'https://www.linkedin.com/in/melennibalbach/'},
    {'first_name': 'John',     'name': 'Fritz Law LLC',                   'website': 'fritzlawstl.com',           'linkedin': 'https://www.linkedin.com/in/john-fritz-63a0a235/'},
    {'first_name': 'Joseph',   'name': 'Strazzeri Mancini LLP',            'website': 'strazzerimancini.com',      'linkedin': 'https://www.linkedin.com/in/joestrazzeri/'},
    {'first_name': 'Tim',      'name': 'Beaupre Law, PLLC',                'website': 'beauprelaw.com',            'linkedin': 'https://www.linkedin.com/in/tbeaupre/'},
    {'first_name': 'Carl',     'name': 'Stenberg Law, PLLC',               'website': 'stenberg.law',              'linkedin': 'https://www.linkedin.com/in/carl-stenberg-5ba436128/'},
    {'first_name': 'Jeffrey',  'name': 'Jeffrey M. Zabner, a Law Corporation', 'website': 'zabnerlaw.com',         'linkedin': 'https://www.linkedin.com/in/jeffrey-zabner-623b2a1/'},
    {'first_name': 'Sage',     'name': 'Porter Smith Law',                 'website': 'portersmithlaw.com',        'linkedin': 'https://www.linkedin.com/in/sage-smith-porter-smith-law/'},
    {'first_name': 'Eric',     'name': 'Jeppson Law',                      'website': 'jeppsonlaw.com',            'linkedin': 'https://www.linkedin.com/in/eric-jeppson-28910911/'},
    {'first_name': 'Rachel',   'name': 'Roche Legal',                      'website': 'rochelegal.co.uk',          'linkedin': 'https://www.linkedin.com/in/rachelroche/'},
]

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

def darken(c, f=0.75):
    hsv = hex_to_hsv(c)
    if not hsv: return '#5e2230'
    r,g,b = colorsys.hsv_to_rgb(hsv[0], hsv[1], max(0, hsv[2]*f))
    return '#{:02x}{:02x}{:02x}'.format(int(r*255),int(g*255),int(b*255))

def lighten(c):
    hsv = hex_to_hsv(c)
    if not hsv: return '#f0ead8'
    r,g,b = colorsys.hsv_to_rgb(hsv[0], hsv[1]*0.15, 0.96)
    return '#{:02x}{:02x}{:02x}'.format(int(r*255),int(g*255),int(b*255))

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

# Import the shared HTML template generator from run_pipeline.py without executing its CLI section
import importlib.util
spec = importlib.util.spec_from_file_location('run_pipeline_lib', os.path.join(SCRIPT_DIR, 'run_pipeline.py'))
# run_pipeline.py runs top-level CLI code on import, so instead inline-load just make_html via exec of the function body is complex.
# Simplest robust approach: re-declare the same make_html here by reading it out of run_pipeline.py source.
with open(os.path.join(SCRIPT_DIR, 'run_pipeline.py')) as f:
    src = f.read()
start = src.index('def make_html')
end = src.index("\n# ── Read XLSX")
make_html_src = src[start:end]
ns = {}
exec(make_html_src, ns)
make_html = ns['make_html']

FALLBACK = ('#7a2e3b', '#5e2230', '#f0ead8')

def process(firm):
    name = firm['name']
    slug = slugify(name)
    html, final_url = fetch(firm['website'])
    color = scrape_color(html) if html else None
    logo  = scrape_logo(html, final_url or firm['website']) if html else None
    if color:
        primary, p_dark, p_cont = color, darken(color), lighten(color)
    else:
        primary, p_dark, p_cont = FALLBACK
    page_html = make_html(name, primary, p_dark, p_cont, logo)
    out_path = os.path.join(PREVIEWS_DIR, f'{slug}.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(page_html)
    return {**firm, 'slug': slug, 'color': primary, 'logo_url': logo, 'preview_url': f'{PREVIEW_BASE}/{slug}.html'}

print(f'Researching & generating {len(FIRMS)} firms...\n')
results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    futures = {ex.submit(process, f): f for f in FIRMS}
    for fut in concurrent.futures.as_completed(futures):
        results.append(fut.result())

results.sort(key=lambda r: r['name'])

print(f'\n{"="*70}')
for r in results:
    logo_tag = '✓ logo' if r['logo_url'] else '  no logo'
    print(f"{r['first_name']:10} {r['name']:42} {logo_tag}")
    print(f"           {r['preview_url']}")
print(f'{"="*70}\n')

with open('/tmp/linkedin_icp_summary.json', 'w') as f:
    json.dump(results, f, indent=2)

# Push
os.chdir(SCRIPT_DIR)
subprocess.run(['git', 'add', 'previews/', 'linkedin_icp_batch.py'], check=True)
subprocess.run(['git', 'commit', '-m', f'Add {len(results)} LinkedIn ICP prospect preview forms', '--allow-empty'], check=True)
subprocess.run(['git', 'push', 'origin', 'main'], check=True)
print('Pushed to GitHub — Vercel deploying now.')
