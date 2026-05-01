/* ──────────────────────────────────────────────────────────────────
 * liturgical-calendar.js — render daily Rome Calendar badge
 *
 * Data source: data/rome_calendar_YYYY.json
 *   (converted from Calendar_YYYY.csv maintained by Province staff)
 *
 * 5 badges (each hidden if empty):
 *   - Season   ← Liturgical Season/Sunday
 *   - Saints   ← Saints/Feasts
 *   - Special  ← Special Days/Events
 *   - History  ← Historical Events
 *   - Deceased ← Deceased Brothers
 *
 * Required HTML:
 *   <span id="rc-date"></span>
 *   <span id="rc-season"></span>
 *   <span id="rc-saints"></span>
 *   <span id="rc-special"></span>
 *   <span id="rc-history"></span>
 *   <span id="rc-deceased"></span>
 * ────────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  const SECTIONS = ['season', 'saints', 'special', 'history', 'deceased'];

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
      SECTIONS.forEach(s => setTag('rc-' + s, ''));
    } else {
      setTag('rc-season', entry.season);
      setTag('rc-saints', entry.saints);
      setTag('rc-special', entry.special);
      setTag('rc-history', entry.history);
      setTag('rc-deceased', entry.deceased);
    }

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
