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
from datetime import datetime, timezone
from urllib.parse import quote
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Query definitions: (query, lang, region, tag)
QUERIES = [
    # English — strict / global
    ('"Brothers of Saint Gabriel"', 'en', 'US', 'global-en'),
    ('"Montfort Brothers"', 'en', 'US', 'global-en'),
    ('"Gabrielite" Catholic', 'en', 'US', 'global-en'),
    ('"Montfortian education"', 'en', 'US', 'education'),
    # Thai — Foundation-related
    ('"ภราดาเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),
    ('"คณะเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),
    # Thai — major schools (filtered for relevance)
    ('"มงฟอร์ตวิทยาลัย"', 'th', 'TH', 'thai-school'),
    ('"โรงเรียนอัสสัมชัญ"', 'th', 'TH', 'thai-school'),
    ('"เซนต์หลุยส์" โรงเรียน', 'th', 'TH', 'thai-school'),
    ('"เซนต์คาเบรียล" โรงเรียน', 'th', 'TH', 'thai-school'),
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
    """Higher = more relevant for Brothers of Saint Gabriel context."""
    score = 0
    title_lower = item['title'].lower()
    # Tag-based base score (foundation news ranked higher than tangential school sports news)
    tag_scores = {
        'global-en': 100,
        'thai-foundation': 90,
        'education': 80,
        'thai-school': 30,  # lower base — school sports/events tangential
    }
    score += tag_scores.get(item['tag'], 50)
    # Priority keywords boost
    for p in PRIORITY_KEYWORDS:
        if p.lower() in title_lower:
            score += 20
    # Recency boost (newer = more relevant)
    if item['pub_ts'] > 0:
        days_old = (datetime.now(timezone.utc).timestamp() - item['pub_ts']) / 86400
        if days_old < 7:
            score += 30
        elif days_old < 30:
            score += 15
        elif days_old < 90:
            score += 5
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

    out = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'count': len(final),
        'sources_queried': len(QUERIES),
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
