#!/usr/bin/env python3
"""
Aggregate news about Brothers of Saint Gabriel / Montfortian Family worldwide.

Output: news-feed.json (top 60 items, deduped, sorted by date desc)

Sources:
- Google News RSS (multiple queries — English + Thai)
- (Future: provincial sites with RSS feeds)

USAGE:
  python3 scripts/fetch_news.py
  → writes news-feed.json in repo root

Run via GitHub Actions cron (.github/workflows/news.yml) — daily.
"""
import feedparser
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote
from pathlib import Path

# Optional: deep_translator for English → Thai translation
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print('  deep_translator not available — skipping translation', file=sys.stderr)

ROOT = Path(__file__).resolve().parent.parent

# ★ Maximum age for news items (drop anything older than this)
MAX_AGE_DAYS = 540  # ~18 months

# Query definitions: (query, lang, region, tag)
QUERIES = [
    # ===== Brothers of Saint Gabriel (Gabrielites) =====
    ('"Brothers of Saint Gabriel"', 'en', 'US', 'sg-brothers'),
    ('"Montfort Brothers"', 'en', 'US', 'sg-brothers'),
    ('"Gabrielite" Catholic', 'en', 'US', 'sg-brothers'),

    # ===== Daughters of Wisdom (Filles de la Sagesse / FDLS) =====
    ('"Daughters of Wisdom" Catholic', 'en', 'US', 'fdls-sisters'),
    ('"Filles de la Sagesse"', 'fr', 'FR', 'fdls-sisters'),

    # ===== Montfort Missionaries / Company of Mary (SMM) =====
    ('"Montfort Missionaries"', 'en', 'US', 'smm-missionaries'),
    ('"Company of Mary" Montfort Catholic', 'en', 'US', 'smm-missionaries'),

    # ===== Founder & spiritual heritage =====
    ('"Louis-Marie de Montfort"', 'en', 'US', 'founder'),
    ('"Saint Louis de Montfort"', 'en', 'US', 'founder'),
    ('"Totus Tuus" Mary Pope', 'en', 'US', 'devotion'),

    # ===== Vatican / Catholic news mentioning Montfortians =====
    ('"Pope" "Montfort" -concert -music', 'en', 'US', 'vatican-news'),
    ('Montfort Saint-Laurent-sur-Sevre Catholic', 'en', 'US', 'vatican-news'),

    # ===== Thai Foundation =====
    ('"ภราดาเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),
    ('"คณะเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),
    ('"มูลนิธิคณะเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),

    # ===== Thai schools (kept lower relevance — see scoring) =====
    ('"มงฟอร์ตวิทยาลัย"', 'th', 'TH', 'thai-school'),
    ('"โรงเรียนอัสสัมชัญ"', 'th', 'TH', 'thai-school'),
    ('"เซนต์หลุยส์" โรงเรียน', 'th', 'TH', 'thai-school'),
    ('"เซนต์คาเบรียล" โรงเรียน', 'th', 'TH', 'thai-school'),

    # ===== ข่าวที่สถานศึกษาต้องติดตาม — ประกาศ กฎหมาย นโยบาย =====
    # (Mission framing: ภายใต้พันธกิจ MEC + จิตตารมณ์มงฟอร์ตเตียน)
    ('"ประกาศกระทรวงศึกษาธิการ"', 'th', 'TH', 'gov-edu'),
    ('"สช." โรงเรียน นโยบาย', 'th', 'TH', 'gov-edu'),
    ('"คุรุสภา" ครู ใบประกอบวิชาชีพ', 'th', 'TH', 'gov-edu'),
    ('"พ.ร.บ.การศึกษา"', 'th', 'TH', 'gov-edu'),
    ('"หลักสูตรแกนกลาง"', 'th', 'TH', 'gov-edu'),
    ('"สมศ." ประเมินคุณภาพ', 'th', 'TH', 'gov-edu'),
    ('"โรงเรียนเอกชน" นโยบาย ประกาศ', 'th', 'TH', 'gov-edu'),
    ('"PISA" ไทย คะแนน', 'th', 'TH', 'gov-edu'),
    ('"O-NET" คะแนน', 'th', 'TH', 'gov-edu'),
]

# Words that indicate UNRELATED content (filter out)
# Politics/celebrity tangents that mention schools but aren't about education
EXCLUDE_KEYWORDS = [
    'นายกฯ', 'อนุทิน', 'การเมือง', 'พรรค',
    'ทักษิณ', 'ชินวัตร', 'อิ๊งค์', 'แพทองธาร',
    'เรือนจำ', 'ส.ส.', 'ส.ว.',
    'รมต.', 'รัฐบาล', 'เลือกตั้ง',
    'หุ้น', 'อสังหา', 'คอนโด',  # business noise
    'มหาวิทยาลัย', 'เตรียมอุดมฯ',  # not about Brothers schools (different institution)
]

# Strong relevance signals — keep even if has noise word
PRIORITY_KEYWORDS = [
    'brother', 'sister', 'congregation', 'saint gabriel', 'montfort', 'gabrielite',
    'ภราดา', 'คณะภราดา', 'มูลนิธิคณะ', 'มงฟอร์ต',
    'ศิษย์เก่า', 'ครบรอบ', 'ก่อตั้ง', 'อธิการ',
    'หลักสูตร', 'การเรียนการสอน', 'รับสมัคร',
]

def fetch_query(query, lang, region, tag):
    """Fetch one Google News RSS query."""
    url = f'https://news.google.com/rss/search?q={quote(query)}&hl={lang}-{region}&gl={region}&ceid={region}:{lang}'
    d = feedparser.parse(url)
    items = []
    for e in d.entries:
        # Parse pub date
        pub_struct = e.get('published_parsed')
        pub_iso = ''
        pub_ts = 0
        if pub_struct:
            try:
                dt = datetime(*pub_struct[:6], tzinfo=timezone.utc)
                pub_iso = dt.isoformat()
                pub_ts = int(dt.timestamp())
            except Exception:
                pass

        source = ''
        if 'source' in e:
            source = e.source.get('title', '') if hasattr(e.source, 'get') else str(e.source)
        if not source:
            # try parse from title (Google News format: "Title - Source")
            m = re.search(r' - ([^-]+)$', e.title)
            if m:
                source = m.group(1).strip()

        items.append({
            'title': e.title,
            'link': e.link,
            'pub_date': pub_iso,
            'pub_ts': pub_ts,
            'source': source,
            'lang': lang,
            'tag': tag,
            'query': query,
            'summary': re.sub(r'<[^>]+>', '', e.get('summary', ''))[:280],
        })
    return items


def is_relevant(item):
    """Keep items that are clearly about Brothers of Saint Gabriel / Montfortian family."""
    title_lower = item['title'].lower()
    # Strong priority keyword? — keep regardless
    has_priority = any(p.lower() in title_lower for p in PRIORITY_KEYWORDS)
    if has_priority:
        return True
    # Has exclude keyword and no priority? → reject
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in title_lower:
            return False
    return True


def relevance_score(item):
    """Higher = more relevant for Montfortian Family context."""
    score = 0
    title_lower = item['title'].lower()
    # Tag-based base score
    tag_scores = {
        'sg-brothers':       100,  # core
        'fdls-sisters':      100,  # core
        'smm-missionaries':  100,  # core
        'vatican-news':      95,
        'founder':           80,
        'devotion':          70,
        'thai-foundation':   90,
        'gov-edu':           85,  # ประกาศกระทรวง/สช/คุรุสภา — สถานศึกษาต้องตาม
        'thai-school':       25,  # tangential
    }
    score += tag_scores.get(item['tag'], 40)
    # Priority keyword boost
    for p in PRIORITY_KEYWORDS:
        if p.lower() in title_lower:
            score += 15
    # Recency — STRONG factor (we want fresh news)
    if item['pub_ts'] > 0:
        days_old = (datetime.now(timezone.utc).timestamp() - item['pub_ts']) / 86400
        if days_old < 30:
            score += 80
        elif days_old < 90:
            score += 50
        elif days_old < 180:
            score += 25
        elif days_old < 365:
            score += 10
        # > 1 year = no boost
    return score


def main():
    all_items = []
    for q, lang, region, tag in QUERIES:
        try:
            items = fetch_query(q, lang, region, tag)
            print(f'  {tag} "{q}" → {len(items)} items', file=sys.stderr)
            all_items.extend(items)
        except Exception as ex:
            print(f'  ERROR {tag}: {ex}', file=sys.stderr)

    # ★ Filter by age — drop anything older than MAX_AGE_DAYS
    cutoff_ts = datetime.now(timezone.utc).timestamp() - (MAX_AGE_DAYS * 86400)
    before_age = len(all_items)
    all_items = [i for i in all_items if i['pub_ts'] >= cutoff_ts]
    after_age = len(all_items)
    print(f'  age filter: {before_age} → {after_age} (dropped {before_age - after_age} older than {MAX_AGE_DAYS} days)', file=sys.stderr)

    # Filter relevance
    all_items = [i for i in all_items if is_relevant(i)]

    # Dedupe by link (or title if same source)
    seen_links = set()
    seen_titles = set()
    deduped = []
    for item in all_items:
        link = item['link']
        title_key = item['title'][:80].lower()
        if link in seen_links or title_key in seen_titles:
            continue
        seen_links.add(link)
        seen_titles.add(title_key)
        deduped.append(item)

    # Add relevance score to each
    for item in deduped:
        item['relevance'] = relevance_score(item)

    # Sort: relevance score desc, then pub_ts desc
    deduped.sort(key=lambda x: (-x['relevance'], -x['pub_ts']))

    # Cap at 60
    final = deduped[:60]

    # ★ Translate English titles → Thai (for Thai-display pages like fsgthailand.org/news)
    translation_count = 0
    if TRANSLATOR_AVAILABLE:
        translator = GoogleTranslator(source='auto', target='th')
        for item in final:
            if item['lang'] != 'th':
                # Translate any non-Thai item (en, fr, etc.)
                try:
                    item['title_th'] = translator.translate(item['title'])
                    translation_count += 1
                    time.sleep(0.1)  # gentle rate-limit
                except Exception as e:
                    item['title_th'] = item['title']  # fallback to original
                    print(f'    translate fail "{item["title"][:40]}...": {e}', file=sys.stderr)
            else:
                item['title_th'] = item['title']  # already Thai
        print(f'  translated {translation_count} non-Thai items → Thai', file=sys.stderr)
    else:
        # Fallback if translator unavailable — title_th = original
        for item in final:
            item['title_th'] = item['title']

    out = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'count': len(final),
        'sources_queried': len(QUERIES),
        'translated': translation_count,
        'items': final,
    }

    out_path = ROOT / 'news-feed.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f'\n✅ Wrote {len(final)} items → {out_path.relative_to(ROOT)}', file=sys.stderr)
    print(f'   Total fetched: {len(all_items)}', file=sys.stderr)
    print(f'   After dedupe: {len(deduped)}', file=sys.stderr)


if __name__ == '__main__':
    main()
