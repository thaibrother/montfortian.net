/* ──────────────────────────────────────────────────────────────────
 * liturgical-calendar.js — render daily Rome Calendar badge
 *
 * Data source: data/rome_calendar_YYYY.json
 *   (converted from Calendar_YYYY.csv maintained by Province staff)
 *
 * 8 badges (each hidden if empty):
 *   - Season   ← Liturgical Season/Sunday
 *   - Saints   ← Saints/Feasts
 *   - Special  ← Special Days/Events
 *   - History  ← Historical Events
 *   - Deceased ← Deceased Brothers (from rome calendar JSON)
 *   - Feastday ← Living Brothers' Saint name day (วันฉลองศาสนนาม)
 *   - Firstvow ← Living Brothers' First Vows anniversary (with years)
 *   - Perpvow  ← Living Brothers' Perpetual Vows anniversary (with years)
 *
 * NOTE: Birthday is intentionally NOT shown here — privacy rule
 *   (see brobook-memory/feedback_no_birthdate_brothers.md)
 *
 * Brothers data source: data/brothers_dates.json
 *   { "first_vows": {...}, "perpetual_vows": {...}, "feast_days": {...} }
 *   (no "birthdays" key on montfortian.net)
 *
 * Required HTML:
 *   <span id="rc-date"></span>
 *   <span id="rc-season"></span>
 *   <span id="rc-saints"></span>
 *   <span id="rc-special"></span>
 *   <span id="rc-history"></span>
 *   <span id="rc-deceased"></span>
 *   <span id="rc-feastday"></span>
 *   <span id="rc-firstvow"></span>
 *   <span id="rc-perpvow"></span>
 * ────────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  const SECTIONS = ['season', 'saints', 'special', 'history', 'deceased',
                    'feastday', 'firstvow', 'perpvow'];

  function fmtDate(date) {
    const m = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const d = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    return `${m[date.getMonth()]} ${date.getDate()} · ${d[date.getDay()]}`;
  }

  function ymd(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function setTag(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!value || !String(value).trim()) {
      el.style.display = 'none';
      return;
    }
    const m = el.innerHTML.match(/<span class="rc-label">[^<]*<\/span>/);
    el.innerHTML = (m ? m[0] + ' ' : '') + value;
    el.style.display = '';
  }

  async function loadCalendar(year) {
    // Try data/rome_calendar_YYYY.json
    const url = `data/rome_calendar_${year}.json`;
    const resp = await fetch(url, { cache: 'no-cache' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching ${url}`);
    return await resp.json();
  }

  async function loadBrotherDates() {
    const resp = await fetch('data/brothers_dates.json', { cache: 'no-cache' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching brothers_dates.json`);
    return await resp.json();
  }

  function fmtAnniversary(list, suffixFn) {
    if (!Array.isArray(list) || list.length === 0) return '';
    const thisYear = new Date().getFullYear();
    return list.map(b => {
      const yrs = (typeof b.year === 'number') ? (thisYear - b.year) : null;
      const meta = [];
      if (b.community) meta.push(b.community);
      if (yrs !== null) meta.push(suffixFn(yrs));
      const tail = meta.length ? ' (' + meta.join(', ') + ')' : '';
      return `${b.name}${tail}`;
    }).join(', ');
  }

  function fmtFeastList(list) {
    if (!Array.isArray(list) || list.length === 0) return '';
    const byFeast = {};
    list.forEach(b => {
      const key = b.feast || b.saint;
      if (!byFeast[key]) byFeast[key] = [];
      byFeast[key].push(b);
    });
    return Object.keys(byFeast).map(feast => {
      const bros = byFeast[feast].map(b =>
        b.name + (b.community ? ' (' + b.community + ')' : '')
      ).join(', ');
      return feast + ' — ' + bros;
    }).join(' · ');
  }

  // ─── Adjust layout when rome-cal height changes ───
  // Pages may have nav with fixed top — recalculate it after badge content
  // is filled, so nav doesn't overlap the calendar bar.
  function adjustLayout() {
    const cal = document.querySelector('.rome-cal');
    const nav = document.querySelector('nav');
    if (!cal) return;

    const calH = cal.offsetHeight;
    if (nav && getComputedStyle(nav).position === 'fixed') {
      nav.style.top = calH + 'px';
    }

    // Find first content section after nav and adjust its top spacing
    // Only push hero down if the nav is FIXED (layout depends on calendar offset).
    // Pages with sticky nav (montfortian.net) don't need this — calendar floats
    // above the natural flow and hero begins at the top normally.
    if (nav && getComputedStyle(nav).position === 'fixed') {
      const navH = nav.offsetHeight;
      const firstHero = document.querySelector('.hero, .hero-section, main, .main-content');
      if (firstHero && getComputedStyle(firstHero).position !== 'fixed') {
        firstHero.style.marginTop = (calH + navH) + 'px';
      }
    }
  }

  async function render(date) {
    date = date || new Date();
    const today = new Date(date.getFullYear(), date.getMonth(), date.getDate());

    // Date label
    const elDate = document.getElementById('rc-date');
    if (elDate) elDate.textContent = fmtDate(today);

    let entry = null;
    try {
      const calendar = await loadCalendar(today.getFullYear());
      entry = calendar[ymd(today)] || null;
    } catch (err) {
      console.warn('liturgical-calendar:', err.message);
    }

    if (!entry) {
      ['season', 'saints', 'special', 'history', 'deceased'].forEach(s => setTag('rc-' + s, ''));
    } else {
      setTag('rc-season', entry.season);
      setTag('rc-saints', entry.saints);
      setTag('rc-special', entry.special);
      setTag('rc-history', entry.history);
      setTag('rc-deceased', entry.deceased);
    }

    // Brothers' anniversaries — independent of liturgical calendar
    // Birthday is NOT loaded here per privacy rule
    let fdText = '', fvText = '', pvText = '';
    try {
      const data = await loadBrotherDates();
      const mmdd = String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
      fdText = fmtFeastList((data.feast_days || {})[mmdd]);
      fvText = fmtAnniversary((data.first_vows || {})[mmdd], (yrs) => yrs + ' yrs');
      pvText = fmtAnniversary((data.perpetual_vows || {})[mmdd], (yrs) => yrs + ' yrs');
    } catch (err) {
      console.warn('liturgical-calendar (brothers):', err.message);
    }
    setTag('rc-feastday', fdText);
    setTag('rc-firstvow', fvText);
    setTag('rc-perpvow', pvText);

    // After content set, recompute heights
    adjustLayout();
    // Adjust again on window resize (e.g. mobile orientation change)
    if (!window._liturgicalResize) {
      window._liturgicalResize = true;
      window.addEventListener('resize', adjustLayout);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => render());
  } else {
    render();
  }

  window.LiturgicalCalendar = { render, loadCalendar };
})();
