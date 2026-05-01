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

    # ===== Beatification / Canonization / Martyrdom — Brothers SG specific =====
    ('"Brothers of Christian Instruction of Saint Gabriel"', 'en', 'US', 'sg-brothers'),
    ('"Saint Gabriel" martyrs Spain', 'en', 'US', 'sg-brothers'),
    ('"Stanislao Ortega"', 'en', 'US', 'sg-brothers'),
    ('"Hermanos de San Gabriel" mártires', 'es', 'ES', 'sg-brothers'),
    ('Vatican martyrs decree Pope canonization', 'en', 'US', 'vatican-news'),
    ('"Causes of Saints" Vatican Pope decrees', 'en', 'US', 'vatican-news'),

    # ===== Thai Foundation =====
    ('"ภราดาเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),
    ('"คณะเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),
    ('"มูลนิธิคณะเซนต์คาเบรียล"', 'th', 'TH', 'thai-foundation'),

    # ===== Thai schools (kept lower relevance — see scoring) =====
    ('"มงฟอร์ตวิทยาลัย"', 'th', 'TH', 'thai-school'),
    ('"โรงเรียนอัสสัมชัญ"', 'th', 'TH', 'thai-school'),
    ('"เซนต์หลุยส์" โรงเรียน', 'th', 'TH', 'thai-school'),
    ('"เซนต์คาเบรียล" โรงเรียน', 'th', 'TH', 'thai-school'),

    # ===== ข่าวการศึกษาไทย — ที่สถานศึกษาต้องติดตาม =====
    # (queries กว้าง — ใช้ relevance scoring + age filter กรองอีกชั้น)
    ('"กระทรวงศึกษาธิการ"', 'th', 'TH', 'gov-edu'),
    ('"ศธ." ประกาศ', 'th', 'TH', 'gov-edu'),
    ('"คุรุสภา"', 'th', 'TH', 'gov-edu'),
    ('"สมศ."', 'th', 'TH', 'gov-edu'),
    ('"สช." การศึกษาเอกชน', 'th', 'TH', 'gov-edu'),
    ('"พ.ร.บ.การศึกษา"', 'th', 'TH', 'gov-edu'),
    ('"ครูและบุคลากรทางการศึกษา"', 'th', 'TH', 'gov-edu'),
    ('"หลักสูตรแกนกลาง"', 'th', 'TH', 'gov-edu'),
    ('"การศึกษาเอกชน"', 'th', 'TH', 'gov-edu'),
    ('"O-NET"', 'th', 'TH', 'gov-edu'),
    ('"PISA" ไทย', 'th', 'TH', 'gov-edu'),
    # ===== Thai newspapers' education sections =====
    ('site:thairath.co.th การศึกษา', 'th', 'TH', 'gov-edu'),
    ('site:matichon.co.th การศึกษา', 'th', 'TH', 'gov-edu'),
    ('site:dailynews.co.th การศึกษา', 'th', 'TH', 'gov-edu'),
    ('site:khaosod.co.th การศึกษา', 'th', 'TH', 'gov-edu'),

    # ===== โรงเรียนเอกชน — บริบทเฉพาะ =====
    ('"สมาคมการศึกษาเอกชน"', 'th', 'TH', 'private-edu'),
    ('"สสอท."', 'th', 'TH', 'private-edu'),
    ('"โรงเรียนเอกชน"', 'th', 'TH', 'private-edu'),
    ('"เงินอุดหนุน" "โรงเรียนเอกชน"', 'th', 'TH', 'private-edu'),
    ('"การศึกษาเอกชน" "นโยบาย"', 'th', 'TH', 'private-edu'),

    # ===== วงการศึกษาคาทอลิก — สภาการศึกษาคาทอลิกแห่งประเทศไทย (CECT) =====
    ('"สภาการศึกษาคาทอลิก"', 'th', 'TH', 'catholic-edu'),
    ('"สภาการศึกษาคาทอลิกแห่งประเทศไทย"', 'th', 'TH', 'catholic-edu'),
    ('site:catholic-education.or.th', 'th', 'TH', 'catholic-edu'),
    ('"การศึกษาคาทอลิก"', 'th', 'TH', 'catholic-edu'),
    ('"โรงเรียนคาทอลิก"', 'th', 'TH', 'catholic-edu'),
    ('"พระสังฆราช" "การศึกษา"', 'th', 'TH', 'catholic-edu'),
    ('"อัครสังฆมณฑล" การศึกษา', 'th', 'TH', 'catholic-edu'),
    ('"Catholic Education Council" Thailand', 'en', 'US', 'catholic-edu'),
    ('"Catholic schools" Thailand', 'en', 'US', 'catholic-edu'),
    ('"Catholic education" Asia', 'en', 'US', 'catholic-edu'),
    ('"Catholic schools" Asia', 'en', 'US', 'catholic-edu'),

    # ===== สื่อมวลชนคาทอลิก ประเทศไทย — อุดมสาร / CCT / Bishops' Conference =====
    ('"สื่อมวลชนคาทอลิก"', 'th', 'TH', 'catholic-media'),
    ('"คณะกรรมการคาทอลิกเพื่อสื่อมวลชน"', 'th', 'TH', 'catholic-media'),
    ('"อุดมสาร"', 'th', 'TH', 'catholic-media'),
    ('"อุดมศานต์"', 'th', 'TH', 'catholic-media'),  # นิตยสารคาทอลิกอีกฉบับ
    ('site:udomsarn.com', 'th', 'TH', 'catholic-media'),
    ('site:thaicatholicpress.org', 'th', 'TH', 'catholic-media'),
    ('site:cbct.or.th', 'th', 'TH', 'catholic-media'),  # สภาประมุขบาทหลวงโรมันคาทอลิก
    ('"สภาประมุขบาทหลวง" คาทอลิก', 'th', 'TH', 'catholic-media'),
    ('"พระศาสนจักรคาทอลิก" ไทย', 'th', 'TH', 'catholic-media'),
    ('"Catholic Bishops Conference of Thailand"', 'en', 'US', 'catholic-media'),
    ('"CBCT" Thailand Catholic', 'en', 'US', 'catholic-media'),
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
    # Catholic education + media
    'สภาการศึกษาคาทอลิก', 'การศึกษาคาทอลิก', 'โรงเรียนคาทอลิก',
    'สื่อมวลชนคาทอลิก', 'คณะกรรมการคาทอลิก',
    'อุดมสาร', 'อุดมศานต์', 'พระศาสนจักร', 'สภาประมุขบาทหลวง',
    'พระสังฆราช', 'อัครสังฆมณฑล', 'สังฆมณฑล',
    'catholic education', 'catholic schools', 'bishops conference', 'archdiocese',
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


# ===== Audience-based classifier =====
# Each item gets one or more audience tags — based on title keywords
# Purpose: คัดข่าวเพื่อเรียนรู้/ปรับตัว/เปรียบเทียบ/ขับเคลื่อนคุณภาพ — by reader role
AUDIENCE_KEYWORDS = {
    'students': [
        'นักเรียน', 'ทุนการศึกษา', 'ทุน ', 'สอบเข้า', 'สอบ O-NET', 'สอบเข้ามหาวิทยาลัย',
        'เยาวชน', 'สอวน', 'โอลิมปิก', 'student', 'scholarship', 'youth competition',
        'รับสมัครนักเรียน', 'admission',
    ],
    'teachers': [
        'ครู ', 'วิชาชีพครู', 'ใบประกอบวิชาชีพ', 'คุรุสภา', 'พัฒนาครู', 'อบรมครู',
        'ครูและบุคลากร', 'การสอน', 'ห้องเรียน', 'หลักสูตรการสอน',
        'teacher', 'classroom', 'pedagogy', 'professional development',
    ],
    'administrators': [
        'ผู้อำนวยการ', 'ผอ.', 'ผู้บริหาร', 'นโยบาย', 'พ.ร.บ.', 'ประกาศ',
        'ศธ.', 'รมว.ศธ', 'ปลัด ศธ', 'สช.', 'สพฐ.', 'สมศ.', 'ก.ค.ศ.',
        'มาตรฐาน', 'งบประมาณ', 'กระทรวงศึกษาธิการ', 'ปฏิรูป',
        'principal', 'administrator', 'policy', 'law', 'governance',
    ],
    'alumni': [
        'ศิษย์เก่า', 'centennial', 'reunion', 'รุ่น', 'alumni',
        'ครบรอบ', 'สมาคมศิษย์',
    ],
    'edu-tech': [
        'AI', 'เอไอ', 'ดิจิทัล', 'เทคโนโลยี', 'นวัตกรรม', 'EdTech',
        'STEM', 'coding', 'อัปสกิล', 'reskill',
        'artificial intelligence', 'digital learning', 'innovation',
        'data-driven', 'big data', 'cloud',
    ],
    'quality': [
        'คุณภาพการศึกษา', 'ประเมินคุณภาพ', 'มาตรฐานการศึกษา', 'ranking',
        'การประเมินภายนอก', 'best practice', 'OECD', 'PISA', 'O-NET',
        'การประกันคุณภาพ',
        'quality', 'accreditation', 'assessment', 'evaluation',
    ],
    'montfortian-family': [
        # auto-assigned by source tag below — keywords as backup
        'มงฟอร์ต', 'เซนต์คาเบรียล', 'ภราดา',
        'Montfort', 'Saint Gabriel', 'Brother',
        'Daughters of Wisdom', 'Filles de la Sagesse', 'Pope', 'Vatican',
    ],
    'private-edu': [
        'โรงเรียนเอกชน', 'การศึกษาเอกชน', 'สสอท.', 'สมาคมการศึกษาเอกชน',
        'เงินอุดหนุน',
        'private school', 'private education',
    ],
    'catholic-edu': [
        'คาทอลิก', 'สังฆมณฑล', 'อัครสังฆมณฑล', 'พระสังฆราช',
        'สภาการศึกษาคาทอลิก', 'โรงเรียนคาทอลิก', 'การศึกษาคาทอลิก',
        'Catholic', 'Diocese', 'Archdiocese', 'Bishop',
    ],
    'catholic-media': [
        'สื่อมวลชนคาทอลิก', 'คณะกรรมการคาทอลิก',
        'อุดมสาร', 'อุดมศานต์', 'พระศาสนจักร',
        'สภาประมุขบาทหลวง', 'CBCT',
        'Catholic media', 'Bishops Conference', 'Catholic press',
    ],
}

# Map source-tag → primary audience (auto-assign without keyword match)
SOURCE_TAG_TO_AUDIENCE = {
    'sg-brothers':       ['montfortian-family'],
    'fdls-sisters':      ['montfortian-family'],
    'smm-missionaries':  ['montfortian-family'],
    'vatican-news':      ['montfortian-family'],
    'founder':           ['montfortian-family'],
    'devotion':          ['montfortian-family'],
    'thai-foundation':   ['montfortian-family'],
    'catholic-media':    ['catholic-media', 'catholic-edu'],
}


def classify_audience(item):
    """Return list of audience tags for this item."""
    audiences = set()
    # Auto-assign by source tag
    for a in SOURCE_TAG_TO_AUDIENCE.get(item['tag'], []):
        audiences.add(a)
    # Keyword classification
    title = item['title']
    for audience, keywords in AUDIENCE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in title.lower():
                audiences.add(audience)
                break
    return sorted(audiences)


# gov-edu: ต้องมี indicator จริงของข่าวการศึกษาเชิงนโยบาย — ไม่ใช่แค่คำว่า "ศึกษา" ลอย ๆ
GOV_EDU_REQUIRED = [
    'กระทรวงศึกษา', 'ศธ.', 'รมว.ศธ', 'ปลัด ศธ',
    'สช.', 'สพฐ.', 'สมศ.', 'คุรุสภา', 'ก.ค.ศ.',
    'พ.ร.บ.การศึกษา', 'พ.ร.บ.โรงเรียน',
    'นโยบายการศึกษา', 'ปฏิรูปการศึกษา',
    'หลักสูตร',
    'ครูและบุคลากรทางการศึกษา', 'วิชาชีพครู', 'ใบประกอบวิชาชีพ',
    'การประเมินคุณภาพ', 'การประเมินภายนอก',
    'PISA', 'O-NET', 'V-NET',
    'การศึกษาเอกชน', 'โรงเรียนเอกชน',
    'ศึกษาธิการจังหวัด', 'ศึกษานิเทศก์',
]

# gov-edu: exclude เพิ่ม (สำหรับ tag นี้โดยเฉพาะ)
GOV_EDU_EXCLUDE = [
    'มหาวิทยาลัย', 'ม.กรุงเทพ', 'ม.มหิดล', 'ม.จุฬา', 'ม.ธรรมศาสตร์',
    'ม.เกษตร', 'มก.', 'ม.ขอนแก่น', 'มจพ.', 'มศว',
    'นายกเล็ก', 'เทศบาล', 'อบต.', 'อบจ.',
    'โรงพยาบาล', 'รพ.',
    'ร่วมบริจาค', 'เลขเด็ด', 'ดวงวันนี้', 'หวย',
    'ศุภชัย สมัปปิโต',  # specific noise from earlier test
]


def is_relevant(item):
    """Keep items that are clearly relevant to Brothers/Montfortian family OR Thai education policy."""
    title_lower = item['title'].lower()

    # Tag-specific: gov-edu must have at least one ministry/policy indicator
    if item['tag'] == 'gov-edu':
        # exclude noise specific to gov-edu tag
        for ex in GOV_EDU_EXCLUDE:
            if ex.lower() in title_lower:
                return False
        # require at least one strong indicator
        if not any(req.lower() in title_lower for req in GOV_EDU_REQUIRED):
            return False
        return True

    # Other tags — original logic
    has_priority = any(p.lower() in title_lower for p in PRIORITY_KEYWORDS)
    if has_priority:
        return True
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
        'gov-edu':           85,  # ประกาศกระทรวง/สช/คุรุสภา
        'thai-school':       25,  # tangential
        'private-edu':       95,  # ตรงกับโรงเรียนคุณ
        'catholic-edu':      95,  # ตรงกับเครือคาทอลิก
        'catholic-media':    92,  # สื่อมวลชนคาทอลิก / สภาประมุขฯ
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

    # ★ Balance categories — ตั้ง quota per tag เพื่อให้ feed มีหลายหมวด ไม่ให้หมวดใดหมวดหนึ่งล้น
    QUOTAS = {
        'sg-brothers':       10,
        'fdls-sisters':      8,
        'smm-missionaries':  8,
        'vatican-news':      6,
        'founder':           4,
        'devotion':          3,
        'thai-foundation':   12,
        'gov-edu':           20,
        'thai-school':       5,
        'private-edu':       12,
        'catholic-edu':      14,  # เพิ่มจาก 12 — มี queries เพิ่ม
        'catholic-media':    10,  # tag ใหม่ — สื่อมวลชนคาทอลิก
    }

    # ★ Classify audiences for each item
    for item in deduped:
        item['audiences'] = classify_audience(item)

    # Drop items with no audience tag — they're not relevant to any reader role
    before_aud = len(deduped)
    deduped = [i for i in deduped if i['audiences']]
    print(f'  audience filter: {before_aud} → {len(deduped)} (dropped {before_aud - len(deduped)} unclassified)', file=sys.stderr)

    by_tag = {}
    for item in deduped:
        by_tag.setdefault(item['tag'], []).append(item)

    # ในแต่ละหมวด: sort relevance + recency, เอาตาม quota
    final = []
    for tag, items in by_tag.items():
        items.sort(key=lambda x: (-x['relevance'], -x['pub_ts']))
        quota = QUOTAS.get(tag, 5)
        final.extend(items[:quota])
        print(f'    {tag}: {len(items)} → keep {min(quota, len(items))}', file=sys.stderr)

    # Final ordering: recency-first (ของใหม่ขึ้นบน) — แต่ก็ไม่อยากให้ tag เดียวขึ้นยาว
    # แยกเป็น 3 buckets ตามอายุ → ใน bucket sort by relevance
    now = datetime.now(timezone.utc).timestamp()
    def bucket(item):
        days_old = (now - item['pub_ts']) / 86400
        if days_old < 30: return 0
        if days_old < 90: return 1
        return 2
    final.sort(key=lambda x: (bucket(x), -x['relevance'], -x['pub_ts']))

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
