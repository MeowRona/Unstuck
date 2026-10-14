(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const STORE_KEY = 'unstuck-planner-saved-v1';
  const LAST_DATE_KEY = 'unstuck-planner-last-date';
  const STORE_VERSION = 1;
  const STUDY_STORE_KEY = 'unstuck-anonymous-study-v1';

  const rescueBtn = $('#rescueModeButton');
  const plannerBtn = $('#plannerModeButton');
  const surface = $('#plannerSurface');
  if (!rescueBtn || !plannerBtn || !surface) return;

  let catalog = null;
  let dateCatalog = null;
  let origins = [];
  let plans = [];
  let selectedPlan = 0;
  let currentBrief = null;
  let lockedIds = new Set();
  let excludedIds = new Set();
  let originCoords = null;
  let returnCoords = null;
  let calendarMonth = null;
  let map = null;
  let markerLayer = null;
  let routeLayer = null;
  let routeSerial = 0;
  let activeStudyTrial = null;

  function esc(value) {
    return String(value == null ? '' : value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  async function request(path, options) {
    const response = await fetch(path, options || {});
    const type = response.headers.get('content-type') || '';
    if (!response.ok) {
      let message = 'Request failed (' + response.status + ')';
      if (type.includes('application/json')) {
        const body = await response.json().catch(() => ({}));
        if (body.error) message = body.error;
      }
      throw new Error(message);
    }
    return type.includes('application/json') ? response.json() : response;
  }

  function post(path, body) {
    return request(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
  }

  function warsawDate(now) {
    const value = now || new Date();
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Europe/Warsaw',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(value);
    const mapParts = {};
    parts.forEach((part) => { mapParts[part.type] = part.value; });
    return mapParts.year + '-' + mapParts.month + '-' + mapParts.day;
  }

  function addDays(iso, days) {
    const bits = iso.split('-').map(Number);
    const value = new Date(Date.UTC(bits[0], bits[1] - 1, bits[2] + days, 12));
    return value.toISOString().slice(0, 10);
  }

  function labelDate(iso) {
    const bits = iso.split('-').map(Number);
    return new Intl.DateTimeFormat('en-GB', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC',
    }).format(new Date(Date.UTC(bits[0], bits[1] - 1, bits[2], 12)));
  }

  function readStore() {
    try {
      const value = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
      if (value.schema_version !== STORE_VERSION || !Array.isArray(value.plans)) throw new Error('schema');
      return value;
    } catch {
      return {schema_version: STORE_VERSION, plans: []};
    }
  }

  function writeStore(store) {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
    renderCalendar();
    renderAgenda();
  }

  async function switchMode(mode) {
    const planner = mode === 'planner';
    $$('.rescue-only').forEach((node) => node.classList.toggle('hidden', planner));
    surface.classList.toggle('hidden', !planner);
    rescueBtn.classList.toggle('active', !planner);
    plannerBtn.classList.toggle('active', planner);
    localStorage.setItem('unstuck-mode', planner ? 'planner' : 'rescue');
    if (planner) {
      await ensureLoaded();
      setTimeout(() => map && map.invalidateSize(), 20);
    }
  }

  rescueBtn.addEventListener('click', () => switchMode('rescue'));
  plannerBtn.addEventListener('click', () => switchMode('planner'));

  function coverageState(date) {
    const coverage = catalog && catalog.coverage ? catalog.coverage : {};
    if (!coverage.event_sources_loaded_from || !coverage.event_sources_loaded_through) return 'not_loaded';
    if (date < coverage.event_sources_loaded_from || date > coverage.event_sources_loaded_through) return 'not_loaded';
    return (catalog.event_dates || []).includes(date) ? 'loaded_with_events' : 'loaded_no_events';
  }

  function renderCalendar() {
    const selected = $('#plannerDate').value || warsawDate();
    if (!calendarMonth) calendarMonth = selected.slice(0, 7);
    const ym = calendarMonth.split('-').map(Number);
    const first = new Date(Date.UTC(ym[0], ym[1] - 1, 1, 12));
    $('#plannerMonthLabel').textContent = new Intl.DateTimeFormat('en-GB', {
      month: 'long', year: 'numeric', timeZone: 'UTC'
    }).format(first);
    const offset = (first.getUTCDay() + 6) % 7;
    const gridStart = new Date(Date.UTC(ym[0], ym[1] - 1, 1 - offset, 12));
    const events = new Set(catalog ? catalog.event_dates || [] : []);
    const saved = new Set(readStore().plans.map((row) => row.date));
    const today = warsawDate();
    const cells = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((x) => '<div class="weekday">' + x + '</div>');
    for (let i = 0; i < 42; i += 1) {
      const d = new Date(gridStart.getTime() + i * 86400000);
      const iso = d.toISOString().slice(0, 10);
      const classes = ['planner-day'];
      if (d.getUTCMonth() !== ym[1] - 1) classes.push('outside');
      if (iso === selected) classes.push('selected');
      if (iso === today) classes.push('today');
      if (events.has(iso)) classes.push('has-event');
      if (saved.has(iso)) classes.push('has-saved');
      cells.push('<button type="button" class="' + classes.join(' ') + '" data-date="' + iso + '">' + d.getUTCDate() + '</button>');
    }
    $('#plannerCalendar').innerHTML = cells.join('');
    $$('.planner-day').forEach((button) => button.addEventListener('click', () => selectDate(button.dataset.date)));
  }

  async function selectDate(iso) {
    $('#plannerDate').value = iso;
    localStorage.setItem(LAST_DATE_KEY, iso);
    calendarMonth = iso.slice(0, 7);
    renderCalendar();
    renderAgenda();
    await loadDateCatalog(iso);
  }

  $('#plannerPrevMonth').addEventListener('click', () => {
    const p = calendarMonth.split('-').map(Number);
    calendarMonth = new Date(Date.UTC(p[0], p[1] - 2, 1, 12)).toISOString().slice(0, 7);
    renderCalendar();
  });
  $('#plannerNextMonth').addEventListener('click', () => {
    const p = calendarMonth.split('-').map(Number);
    calendarMonth = new Date(Date.UTC(p[0], p[1], 1, 12)).toISOString().slice(0, 7);
    renderCalendar();
  });

  $$('[data-planner-quick]').forEach((button) => button.addEventListener('click', async () => {
    const today = warsawDate();
    let target = today;
    if (button.dataset.plannerQuick === 'tomorrow') target = addDays(today, 1);
    if (button.dataset.plannerQuick === 'weekend') {
      const weekday = new Intl.DateTimeFormat('en-US', {weekday: 'short', timeZone: 'Europe/Warsaw'}).format(new Date());
      const wait = {Mon:5,Tue:4,Wed:3,Thu:2,Fri:1,Sat:0,Sun:0}[weekday] || 0;
      target = addDays(today, wait);
    }
    await selectDate(target);
  }));

  function renderAgenda() {
    const date = $('#plannerDate').value;
    const store = readStore();
    const same = store.plans.filter((row) => row.date === date);
    const other = store.plans.find((row) => row.date !== date);
    let html = '';
    same.forEach((row) => {
      html += '<div class="saved-plan-row" data-saved-id="' + esc(row.id) + '"><div><strong>' +
        esc(row.title) + '</strong><span>Saved locally · ' + row.plan.items.length + ' stops</span></div>' +
        '<div class="saved-plan-row-actions"><button type="button" data-saved-action="load">Load</button>' +
        '<button type="button" data-saved-action="delete">Delete</button></div></div>';
    });
    if (!same.length && other) {
      html = '<div class="saved-plan-row" data-saved-id="' + esc(other.id) + '"><div><strong>Copy settings from ' +
        esc(labelDate(other.date)) + '</strong><span>Fixed events are not repeated automatically.</span></div>' +
        '<div class="saved-plan-row-actions"><button type="button" data-saved-action="copy">Copy here</button></div></div>';
    }
    $('#plannerAgenda').innerHTML = html;
    $$('[data-saved-action]').forEach((button) => button.addEventListener('click', async () => {
      const box = button.closest('[data-saved-id]');
      const row = readStore().plans.find((x) => x.id === box.dataset.savedId);
      if (!row) return;
      if (button.dataset.savedAction === 'delete') {
        const storeNow = readStore();
        storeNow.plans = storeNow.plans.filter((x) => x.id !== row.id);
        writeStore(storeNow);
      } else if (button.dataset.savedAction === 'load') {
        currentBrief = structuredClone(row.brief);
        plans = [structuredClone(row.plan)];
        selectedPlan = 0;
        lockedIds = new Set(row.plan.locked_ids || []);
        excludedIds = new Set(currentBrief.excluded_ids || []);
        fillForm(currentBrief);
        renderResult({plans: plans, planned_activity_count: row.plan.items.length, taste_status: row.plan.taste_status});
        showNote('Loaded from this browser. Rebuild the day to re-check source data.');
      } else {
        const flexibleLocks = (row.plan.locked_ids || []).filter((id) => {
          const item = row.plan.items.find((x) => x.activity_id === id);
          return item && item.kind !== 'event';
        });
        const copied = Object.assign({}, row.brief, {
          date: date,
          must_include_ids: flexibleLocks,
          locked_ids: flexibleLocks,
          excluded_ids: [],
        });
        fillForm(copied);
        showNote('Copied to a new date. Fixed events were not repeated; schedule checks run again.');
        await buildDay(copied);
      }
    }));
  }

  function renderMustInclude() {
    const select = $('#plannerMustInclude');
    const keep = select.value;
    const items = (dateCatalog ? dateCatalog.items : []).filter((item) => item.schedulable && item.date_status !== 'closed');
    select.innerHTML = '<option value="">None</option>' + items.map((item) =>
      '<option value="' + esc(item.id) + '">' + esc(item.title) + '</option>'
    ).join('');
    if (items.some((item) => item.id === keep)) select.value = keep;
  }

  function formatItemWhen(item) {
    if (item.kind === 'event') {
      if (!item.start_time) return 'Session time not loaded';
      if (item.flexible_visit_window && item.end_time) return item.start_time + '–' + item.end_time + ' · flexible';
      return item.start_time + (item.end_status === 'unknown' ? ' · end unknown' : item.end_time ? '–' + item.end_time : '');
    }
    return item.date_status === 'closed' ? 'Closed this date' : String(item.duration_minutes_estimate || 75) + ' min visit';
  }

  function formatCatalogPrice(price) {
    if (!price || price.min == null || price.max == null) return 'Price unknown';
    const people = Number($('#plannerPeople').value || 2);
    let min = Number(price.min), max = Number(price.max);
    if (price.basis === 'per_person') { min *= people; max *= people; }
    return Math.round(min) + (min === max ? '' : '–' + Math.round(max)) + ' ' + (price.currency || 'PLN');
  }

  function renderExplore() {
    if (!dateCatalog) return;
    const state = coverageState($('#plannerDate').value);
    const events = dateCatalog.items.filter((x) => x.kind === 'event').length;
    $('#plannerExploreMeta').textContent = state === 'not_loaded'
      ? 'Event data not loaded for this date'
      : events ? String(events) + ' event record' + (events === 1 ? '' : 's') + ' from selected sources'
        : 'No event records in selected loaded sources for this date';
    const order = {event:0, attraction:1, restaurant:2};
    const rows = dateCatalog.items.slice().sort((a,b) =>
      (order[a.kind] ?? 9) - (order[b.kind] ?? 9) || a.title.localeCompare(b.title)
    ).slice(0, 40);
    $('#plannerExploreList').innerHTML = rows.map((item) => {
      const disabled = !item.schedulable || item.date_status === 'closed';
      return '<article class="explore-card' + (disabled ? ' unschedulable' : '') + '" data-explore-id="' + esc(item.id) + '">' +
        '<div class="explore-card-head"><div><h3>' + esc(item.title) + '</h3><p>' + esc(item.venue && item.venue.name) + '</p></div>' +
        '<span class="timeline-chip">' + esc(item.category.replaceAll('_',' ')) + '</span></div>' +
        '<p>' + esc(item.description) + '</p><div class="explore-card-meta"><span class="timeline-chip">' + esc(formatItemWhen(item)) +
        '</span><span class="timeline-chip' + (item.price && item.price.status === 'unknown' ? ' unknown' : '') + '">' +
        esc(formatCatalogPrice(item.price)) + '</span>' +
        (item.kind === 'event' && item.availability === 'unknown' ? '<span class="timeline-chip unknown">availability unknown</span>' : '') +
        (!item.schedulable ? '<span class="timeline-chip unknown">' + esc(item.unschedulable_reason) + '</span>' : '') +
        '</div><div class="explore-card-actions"><button type="button" data-explore-action="add"' + (disabled ? ' disabled' : '') +
        '>Add to plan</button>' + (item.info_url ? '<a href="' + esc(item.info_url) + '" target="_blank" rel="noreferrer">Details ↗</a>' : '') +
        '</div></article>';
    }).join('') || '<div class="planner-empty"><span>No loaded items for this date.</span></div>';
    $$('[data-explore-action="add"]').forEach((button) => button.addEventListener('click', async () => {
      const id = button.closest('[data-explore-id]').dataset.exploreId;
      $('#plannerMustInclude').value = id;
      switchPlannerView('plan');
      await buildDay();
    }));
    renderMustInclude();
  }

  async function loadDateCatalog(date) {
    dateCatalog = await request('/api/planner/catalog?date=' + encodeURIComponent(date));
    renderExplore();
    const state = coverageState(date);
    $('#plannerCoverageStatus').textContent = state === 'not_loaded'
      ? 'Event data not loaded for this date'
      : state === 'loaded_with_events' ? 'Selected event sources loaded'
        : 'No events in selected loaded sources';
  }

  async function resolveLocation(input, existing) {
    if (existing && existing.lat != null && existing.lon != null) return existing;
    const value = input.value.trim();
    const saved = origins.find((row) =>
      String(row.label || '').toLowerCase() === value.toLowerCase() ||
      String(row.id || '').toLowerCase() === value.toLowerCase()
    );
    if (saved) return {lat:Number(saved.lat), lon:Number(saved.lon), label:saved.label};
    const found = await post('/api/geocode', {address:value});
    input.value = found.label;
    return {lat:Number(found.lat), lon:Number(found.lon), label:found.label};
  }

  $('#plannerOrigin').addEventListener('input', () => { originCoords = null; });
  $('#plannerReturnOrigin').addEventListener('input', () => { returnCoords = null; });
  $('#plannerReturnRequired').addEventListener('change', () => {
    $('#plannerReturnWrap').classList.toggle('hidden', !$('#plannerReturnRequired').checked);
  });
  $('#plannerDate').addEventListener('change', () => selectDate($('#plannerDate').value));

  $('#plannerCurrentLocation').addEventListener('click', () => {
    const status = $('#plannerOriginStatus');
    if (!navigator.geolocation) { status.textContent = 'Geolocation is unavailable.'; return; }
    status.textContent = 'Waiting for location permission…';
    navigator.geolocation.getCurrentPosition(async (position) => {
      const lat = Number(position.coords.latitude), lon = Number(position.coords.longitude);
      if (!(lat >= 52.05 && lat <= 52.40 && lon >= 20.75 && lon <= 21.35)) {
        status.textContent = 'Current location is outside Warsaw only beta.';
        return;
      }
      originCoords = {lat:lat, lon:lon, label:'Current location'};
      $('#plannerOrigin').value = 'Current location';
      try {
        const found = await post('/api/reverse-geocode', {lat:lat, lon:lon});
        if (found.available && found.label) {
          $('#plannerOrigin').value = found.label;
          originCoords.label = found.label;
          status.textContent = 'Address filled in · routing still uses exact GPS position.';
        }
      } catch {
        status.textContent = 'GPS ready · address lookup unavailable.';
      }
    }, () => { status.textContent = 'Current location could not be read.'; }, {enableHighAccuracy:true, timeout:12000, maximumAge:30000});
  });

  async function formBrief() {
    originCoords = await resolveLocation($('#plannerOrigin'), originCoords);
    const returnRequired = $('#plannerReturnRequired').checked;
    if (returnRequired) {
      if (!$('#plannerReturnOrigin').value.trim()) $('#plannerReturnOrigin').value = $('#plannerOrigin').value;
      returnCoords = $('#plannerReturnOrigin').value.trim() === $('#plannerOrigin').value.trim()
        ? Object.assign({}, originCoords)
        : await resolveLocation($('#plannerReturnOrigin'), returnCoords);
    }
    const must = $('#plannerMustInclude').value ? [$('#plannerMustInclude').value] : [];
    return {
      date: $('#plannerDate').value,
      start_time: $('#plannerStartTime').value,
      end_time: $('#plannerEndTime').value,
      origin: $('#plannerOrigin').value.trim(),
      origin_lat: originCoords.lat,
      origin_lon: originCoords.lon,
      return_required: returnRequired,
      return_origin: returnRequired ? ($('#plannerReturnOrigin').value.trim() || $('#plannerOrigin').value.trim()) : '',
      return_lat: returnRequired ? returnCoords.lat : originCoords.lat,
      return_lon: returnRequired ? returnCoords.lon : originCoords.lon,
      people: Number($('#plannerPeople').value),
      budget_total: Number($('#plannerBudget').value),
      activity_count: Number($('#plannerActivityCount').value),
      pace: $('#plannerPace').value,
      travel_mode: $('#plannerTravelMode').value,
      event_buffer_minutes: Number($('#plannerEventBuffer').value),
      include_meal: $('#plannerIncludeMeal').checked,
      categories: [],
      interests: $$('.planner-interest-fieldset input:checked').map((input) => input.value),
      taste_refs: $('#plannerTasteRefs').value.split(',').map((x) => x.trim()).filter(Boolean),
      must_include_ids: Array.from(new Set(must.concat(Array.from(lockedIds)))),
      locked_ids: Array.from(lockedIds),
      excluded_ids: Array.from(excludedIds),
    };
  }

  function fillForm(brief) {
    if (!brief) return;
    $('#plannerDate').value = brief.date;
    $('#plannerStartTime').value = brief.start_time;
    $('#plannerEndTime').value = brief.end_time;
    $('#plannerOrigin').value = brief.origin;
    $('#plannerReturnRequired').checked = Boolean(brief.return_required);
    $('#plannerReturnWrap').classList.toggle('hidden', !brief.return_required);
    $('#plannerReturnOrigin').value = brief.return_origin || brief.origin;
    $('#plannerPeople').value = brief.people;
    $('#plannerBudget').value = brief.budget_total;
    $('#plannerActivityCount').value = brief.activity_count;
    $('#plannerPace').value = brief.pace;
    $('#plannerTravelMode').value = brief.travel_mode;
    $('#plannerEventBuffer').value = String(brief.event_buffer_minutes == null ? 15 : brief.event_buffer_minutes);
    $('#plannerIncludeMeal').checked = Boolean(brief.include_meal);
    $('#plannerTasteRefs').value = (brief.taste_refs || []).join(', ');
    $$('.planner-interest-fieldset input').forEach((input) => { input.checked = (brief.interests || []).includes(input.value); });
    lockedIds = new Set(brief.locked_ids || []);
    excludedIds = new Set(brief.excluded_ids || []);
    originCoords = brief.origin_lat != null ? {lat:Number(brief.origin_lat), lon:Number(brief.origin_lon), label:brief.origin} : null;
    returnCoords = brief.return_lat != null ? {lat:Number(brief.return_lat), lon:Number(brief.return_lon), label:brief.return_origin} : null;
    calendarMonth = brief.date.slice(0, 7);
    renderCalendar();
    renderAgenda();
  }

  async function buildDay(explicit) {
    const serial = ++routeSerial; // Invalidate any previous route or generation response.
    const error = $('#plannerFormError');
    error.classList.add('hidden');
    try {
      const brief = explicit || await formBrief();
      if (serial !== routeSerial) return;
      currentBrief = brief;
      const result = await post('/api/planner/generate', brief);
      if (serial !== routeSerial) return;
      plans = result.plans || [];
      selectedPlan = 0;
      renderResult(result);
      if (plans.length) await checkRoutes();
    } catch (err) {
      if (serial !== routeSerial) return;
      error.textContent = err.message;
      error.classList.remove('hidden');
    }
  }

  $('#plannerForm').addEventListener('submit', (event) => {
    event.preventDefault();
    buildDay();
  });

  function costLabel(plan) {
    if (plan.known_cost_min == null || plan.known_cost_max == null) return 'Known cost —';
    const base = plan.known_cost_min === plan.known_cost_max
      ? Math.round(plan.known_cost_max) + ' ' + plan.currency
      : Math.round(plan.known_cost_min) + '–' + Math.round(plan.known_cost_max) + ' ' + plan.currency;
    return plan.unknown_cost_components ? base + ' + unknown' : base;
  }

  function renderTimeline(plan) {
    let html = '<div class="plan-summary-bar">' +
      '<div><strong>' + plan.items.length + ' stops</strong><span>' + esc(labelDate(plan.date)) + '</span></div>' +
      '<div><strong>' + esc(costLabel(plan)) + '</strong><span>budget ' + esc(plan.budget_total) + ' PLN</span></div>' +
      '<div><strong>' + esc(plan.total_travel_minutes) + ' min</strong><span>travel · ' + esc(plan.route_status) + '</span></div>' +
      '<div><span class="plan-feasibility ' + esc(plan.feasibility) + '">' + esc(plan.feasibility.replaceAll('_',' ')) + '</span>' +
      '<span>' + plan.unknown_cost_components + ' unknown cost component' + (plan.unknown_cost_components === 1 ? '' : 's') + '</span></div></div>';

    plan.items.forEach((item, index) => {
      const leg = plan.travel_legs[index];
      if (leg) {
        html += '<div class="timeline-leg"><div class="timeline-time">' + esc(leg.depart) + '</div><div class="timeline-body"><strong>' +
          esc(leg.minutes) + ' min ' + esc(leg.mode) + '</strong> · ' + esc(leg.from) + ' → ' + esc(leg.to) +
          (leg.wait_minutes ? ' · ' + esc(leg.wait_minutes) + ' min buffer' : '') +
          '<div class="timeline-meta"><span class="timeline-chip">' + esc(leg.status) + '</span>' +
          (leg.scheduled ? '<span class="timeline-chip">scheduled · not realtime</span>' : '') + '</div></div></div>';
      }
      html += '<article class="timeline-activity" data-plan-item="' + esc(item.activity_id) + '"><div class="timeline-time">' +
        esc(item.display_start) + '<br><span>' + esc(item.display_end) + '</span></div><div class="timeline-body"><h3>' +
        (index + 1) + '. ' + esc(item.title) + '</h3><p>' + esc(item.venue && item.venue.name) + ' · ' + esc(item.venue && item.venue.address) +
        '</p><div class="timeline-meta"><span class="timeline-chip">' + esc(item.category.replaceAll('_',' ')) + '</span>' +
        '<span class="timeline-chip">' + esc(item.duration_minutes) + ' min' + (item.duration_status === 'estimate' ? ' planned' : '') + '</span>' +
        '<span class="timeline-chip' + (item.price && item.price.status === 'unknown' ? ' unknown' : '') + '">' +
        esc(item.price && item.price.min != null ? Math.round(item.price.min) + '–' + Math.round(item.price.max) + ' ' + item.price.currency : 'price unknown') +
        '</span>' + (item.kind === 'restaurant' && Number.isInteger(item.taste_rank) ? '<span class="timeline-chip">Qloo #'+esc(item.taste_rank)+' (matched shortlist)</span>' : '') +
        (item.kind === 'event' && item.availability === 'unknown' ? '<span class="timeline-chip unknown">availability unknown</span>' : '') +
        (lockedIds.has(item.activity_id) ? '<span class="timeline-chip">locked</span>' : '') + '</div>' +
        (item.checks && item.checks.length ? '<ul class="timeline-checks">' + item.checks.map((x) => '<li>' + esc(x) + '</li>').join('') + '</ul>' : '') +
        '<div class="timeline-actions"><button type="button" data-item-action="lock">' + (lockedIds.has(item.activity_id) ? 'Unlock' : 'Lock') +
        '</button><button type="button" data-item-action="replace">Replace</button><button type="button" data-item-action="remove">Remove</button>' +
        '<button type="button" data-item-action="ics">.ics</button>' +
        (item.info_url ? '<a href="' + esc(item.info_url) + '" target="_blank" rel="noreferrer">Details ↗</a>' : '') +
        '</div></div></article>';
    });

    const back = (plan.travel_legs || []).find((leg) => leg.return_leg);
    if (back) {
      html += '<div class="timeline-leg"><div class="timeline-time">' + esc(back.depart) + '</div><div class="timeline-body"><strong>' +
        esc(back.minutes) + ' min return</strong> · ' + esc(back.from) + ' → ' + esc(back.to) +
        '<div class="timeline-meta"><span class="timeline-chip">' + esc(back.status) + '</span>' +
        (back.scheduled ? '<span class="timeline-chip">scheduled · not realtime</span>' : '') + '</div></div></div>';
    }
    if (plan.total_idle_minutes >= 60) {
      html += '<div class="planner-repair-note"><strong>Large gap in this schedule:</strong> about ' +
        esc(plan.total_idle_minutes) + ' min beyond the required event arrival buffer (based on estimated travel). ' +
        'Consider a later start or fewer stops; this is free time, not a scheduled activity.</div>';
    }
    if (plan.checks && plan.checks.length) {
      html += '<div class="planner-repair-note"><strong>Before you rely on this plan:</strong><br>' +
        plan.checks.map(esc).join('<br>') + '</div>';
    }
    if (plan.route_conflicts && plan.route_conflicts.length) {
      html += '<div class="planner-repair-note"><strong>Route conflict:</strong><br>' +
        plan.route_conflicts.map(esc).join('<br>') + '</div>';
    }
    return html;
  }

  function renderSelected() {
    const plan = plans[selectedPlan];
    $('#plannerPlanActions').classList.toggle('hidden', !plan);
    if (!plan) {
      $('#plannerTimeline').innerHTML = '<div class="planner-empty"><strong>No feasible plan.</strong><span>Change one condition or choose another must-do.</span></div>';
      drawMap(null);
      return;
    }
    $('#plannerTimeline').innerHTML = renderTimeline(plan);
    bindTimeline();
    drawMap(plan);
    $$('[data-plan-index]').forEach((button) => button.classList.toggle('active', Number(button.dataset.planIndex) === selectedPlan));
  }

  function studyComparison() {
    return plans[selectedPlan]?.taste_audit?.same_pool_comparison || null;
  }

  function studyAvailable(comparison) {
    return !!(
      comparison?.study_baseline && comparison?.study_with_qloo &&
      comparison.baseline_top_plan_id !== comparison.with_qloo_top_plan_id &&
      comparison.method === 'same_feasible_plan_pool'
    );
  }

  function studyRows() {
    try {
      const rows = JSON.parse(localStorage.getItem(STUDY_STORE_KEY) || '[]');
      return Array.isArray(rows) ? rows.slice(-60) : [];
    } catch (_) { return []; }
  }

  function updateStudyAvailability() {
    const comparison = studyComparison();
    const available = studyAvailable(comparison);
    $('#plannerStudyStart').disabled = !available;
    if (activeStudyTrial && activeStudyTrial.key !== (
      comparison?.baseline_top_plan_id + '|' + comparison?.with_qloo_top_plan_id
    )) activeStudyTrial = null;
    if (!activeStudyTrial) {
      $('#plannerStudyContent').textContent = available
        ? 'Two distinct options from the same feasible-plan pool are ready for a blind trial. A real person must make the choice.'
        : 'No two distinct Qloo-versus-operational options are available for this plan. A non-change is a valid finding; do not fabricate a comparison.';
    }
  }

  function renderBlindCard(preview, label, source) {
    const card = document.createElement('section');
    card.className = 'planner-study-card';
    const heading = document.createElement('strong');
    heading.textContent = 'Option ' + label;
    card.append(heading);
    for (const item of preview.stops || []) {
      const row = document.createElement('p');
      row.textContent = (item.start || '?') + '–' + (item.end || '?') +
        ' · ' + (item.title || 'Unknown activity');
      card.append(row);
    }
    const meta = document.createElement('small');
    meta.textContent = 'Estimated travel: ' + preview.estimated_travel_minutes +
      ' min · known cost ceiling: ' + (preview.known_cost_max == null ? 'unknown' : preview.known_cost_max + ' PLN') +
      ' · unpriced components: ' + (preview.unknown_cost_components || 0) +
      ' · budget cap: ' + preview.budget_total + ' PLN. Opening hours and transit still require verification.';
    card.append(meta);
    const select = document.createElement('button');
    select.type = 'button';
    select.className = 'secondary-button';
    select.textContent = 'Choose option ' + label;
    select.addEventListener('click', () => finishBlindTrial(source));
    card.append(select);
    return card;
  }

  function finishBlindTrial(chosen) {
    if (!activeStudyTrial) return;
    const elapsed = Math.round((performance.now() - activeStudyTrial.started) / 100) / 10;
    const rows = studyRows();
    rows.push({
      trial: rows.length + 1,
      scenario_date: activeStudyTrial.date,
      ranked_restaurant_count: activeStudyTrial.ranked,
      candidate_plan_count: activeStudyTrial.candidateCount,
      shown_first: activeStudyTrial.shownFirst,
      selected: chosen,
      seconds_to_decision: elapsed,
    });
    try {
      localStorage.setItem(STUDY_STORE_KEY, JSON.stringify(rows.slice(-60)));
      $('#plannerStudyContent').textContent = 'Anonymous trial stored on this device. ' +
        rows.length + ' recorded trial(s). Export CSV when actual people have completed the comparisons. ' +
        'A model or automated click is not a human preference result.';
    } catch (_) {
      $('#plannerStudyContent').textContent = 'Browser storage is disabled; this trial was not saved.';
    }
    activeStudyTrial = null;
  }

  $('#plannerStudyStart').addEventListener('click', () => {
    const comparison = studyComparison();
    if (!studyAvailable(comparison)) return;
    $('#plannerEvidence').open = false;
    const swapped = Math.random() < 0.5;
    const options = swapped
      ? [
          {source:'qloo', preview:comparison.study_with_qloo},
          {source:'baseline', preview:comparison.study_baseline},
        ] : [
          {source:'baseline', preview:comparison.study_baseline},
          {source:'qloo', preview:comparison.study_with_qloo},
        ];
    activeStudyTrial = {
      key:comparison.baseline_top_plan_id + '|' + comparison.with_qloo_top_plan_id,
      date:comparison.study_baseline.date,
      ranked:comparison.ranked_restaurant_count || 0,
      candidateCount:comparison.candidate_plan_count || 0,
      shownFirst:options[0].source,
      started:performance.now(),
    };
    const content = $('#plannerStudyContent');
    content.replaceChildren();
    const intro = document.createElement('p');
    intro.textContent = 'Choose which whole plan you would prefer, or neither. The labels deliberately hide the ranking method.';
    content.append(intro);
    const grid = document.createElement('div');
    grid.className = 'planner-study-grid';
    options.forEach((option, index) => grid.append(
      renderBlindCard(option.preview, index === 0 ? 'A' : 'B', option.source)
    ));
    content.append(grid);
    const neither = document.createElement('button');
    neither.type = 'button';
    neither.className = 'secondary-button';
    neither.textContent = 'Neither option';
    neither.addEventListener('click', () => finishBlindTrial('neither'));
    content.append(neither);
  });

  $('#plannerStudyExport').addEventListener('click', () => {
    const rows = studyRows();
    if (!rows.length) {
      $('#plannerStudyContent').textContent = 'There are no real trial responses on this device to export.';
      return;
    }
    const fields = ['trial', 'scenario_date', 'ranked_restaurant_count',
      'candidate_plan_count', 'shown_first', 'selected', 'seconds_to_decision'];
    const cell = (value) => '"' + String(value ?? '').replaceAll('"', '""') + '"';
    const csv = [fields.map(cell).join(','), ...rows.map(row =>
      fields.map(key => cell(row[key])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'}));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'unstuck-anonymous-preference-trials.csv';
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });

  function renderEvidence() {
    updateStudyAvailability();
    const body = $('#plannerEvidenceBody');
    if (!catalog) return;
    const coverage = catalog.coverage || {};
    const plan = plans[selectedPlan];
    const used = new Map();
    (plan && plan.items || []).forEach((item) => {
      if (item.source && item.source.url) used.set(item.source.url, item.source);
    });
    body.innerHTML = '<p><strong>Event coverage:</strong> ' + esc(coverage.event_sources_loaded_from) + ' → ' +
      esc(coverage.event_sources_loaded_through) + '. ' + esc(coverage.scope) + (coverage.last_manual_refresh ? ' Last manual event refresh: ' + esc(coverage.last_manual_refresh) + '.' : '') + '</p>' +
      '<p><strong>No-results semantics:</strong> ' + esc(coverage.no_results_meaning) + '</p>' +
      '<p><strong>Routing:</strong> initial plans use estimates; selected plans are checked leg by leg. Warsaw transit is scheduled, not realtime.</p>' +
      '<p><strong>Taste:</strong> ' + esc(plan?.taste_note || (plan?.taste_status === 'not_requested' ? 'No taste matching requested.' : 'Taste coverage unavailable.')) + '</p>' +
      (plan?.taste_audit?.candidate_count != null
        ? '<p><strong>Actual Qloo coverage:</strong> ' + esc(plan.taste_audit.ranked_count || 0) + ' ranked / ' +
          esc(plan.taste_audit.resolved_count || 0) + ' resolved / ' +
          esc(plan.taste_audit.candidate_count) + ' considered; ' +
          esc(plan.taste_audit.recognized_signals?.length || 0) + ' taste signal(s) recognized. ' +
          (plan.taste_audit.insights_called ? 'Insights API called.' : 'Insights API not called.') +
          '</p>' : '') +
      (plan?.taste_audit?.resolved_candidates?.length
        ? '<p><strong>Qloo venue matches:</strong> ' +
          plan.taste_audit.resolved_candidates.map(row => esc(row.name || row.place_id)).join(', ') +
          '. These are exact catalog identities used in this request, not inferred preferences.</p>'
        : '') +
      (plan?.taste_audit?.same_pool_comparison
        ? '<section class="planner-qloo-comparison"><h4>What did Qloo change?</h4>' +
          '<p><strong>Without taste:</strong> ' + esc(plan.taste_audit.same_pool_comparison.baseline_restaurant || 'no restaurant') + '</p>' +
          '<p><strong>With Qloo:</strong> ' + esc(plan.taste_audit.same_pool_comparison.with_qloo_restaurant || 'no restaurant') + '</p>' +
          '<p><strong>Top plan changed:</strong> ' + (plan.taste_audit.same_pool_comparison.top_plan_changed ? 'Yes' : 'No — the available taste signal did not change the top plan.') + '</p>' +
          '<p><strong>Same feasibility pool:</strong> ' + esc(plan.taste_audit.same_pool_comparison.candidate_plan_count) +
          ' generated schedules, before detailed route checks. This demonstrates a ranking difference, not user preference or venue availability.</p></section>'
        : '') +
      (plan?.taste_audit?.recognized_signals?.length ? '<p><strong>Qloo recognized:</strong> ' + plan.taste_audit.recognized_signals.map(s => esc(s.name)).join(', ') + '</p>' : '') +
      (plan?.taste_audit?.unresolved_signals?.length ? '<p><strong>Skipped:</strong> ' + plan.taste_audit.unresolved_signals.map(s => esc(s.input)).join(', ') + '</p>' : '') +
      (used.size ? '<p><strong>Used sources:</strong><br>' + Array.from(used.values()).map((source) =>
        '<a href="' + esc(source.url) + '" target="_blank" rel="noreferrer">' + esc(source.name || source.url) + '</a>' +
        (source.checked_at ? ' · checked ' + esc(source.checked_at) : '')
      ).join('<br>') + '</p>' : '') +
      '<p><strong>Saved plans:</strong> browser localStorage only; no account sync.</p>';
    $('#plannerEvidence').classList.remove('hidden');
  }

  function renderResult(result) {
    $('#plannerResultsMeta').textContent = result.explanation ||
      (plans.length ? plans.length + ' variant' + (plans.length === 1 ? '' : 's') + ' · ' + (result.planned_activity_count || plans[0].items.length) + ' stops' : 'No feasible plan');
    $('#plannerTasteStatus').textContent = result.taste_status === 'live_restaurants'
      ? 'Live Qloo · ' + esc(result.taste_audit?.ranked_count || 0) + '/' +
          esc(result.taste_audit?.candidate_count || 0) + ' restaurants ranked'
      : result.taste_status === 'not_requested' ? 'Taste not requested'
      : result.taste_status === 'not_live' ? 'Taste matching not live yet'
      : result.taste_status === 'insufficient_coverage' ? 'Taste coverage too limited'
      : 'Taste unavailable · operational plan';
    const tabs = $('#plannerVariantTabs');
    if (plans.length > 1) {
      tabs.classList.remove('hidden');
      tabs.innerHTML = plans.map((plan, index) =>
        '<button type="button" data-plan-index="' + index + '" class="' + (index === selectedPlan ? 'active' : '') + '">Option ' +
        (index + 1) + ' · ' + esc(plan.feasibility.replaceAll('_',' ')) + '</button>'
      ).join('');
      $$('[data-plan-index]').forEach((button) => button.addEventListener('click', async () => {
        selectedPlan = Number(button.dataset.planIndex);
        renderSelected();
        await checkRoutes();
      }));
    } else {
      tabs.classList.add('hidden');
      tabs.innerHTML = '';
    }
    renderSelected();
    renderEvidence();
  }

  function bindTimeline() {
    $$('[data-plan-item] [data-item-action]').forEach((button) => button.addEventListener('click', async () => {
      const id = button.closest('[data-plan-item]').dataset.planItem;
      const action = button.dataset.itemAction;
      if (action === 'ics') { await downloadIcs(id); return; }
      if (action === 'lock') {
        if (lockedIds.has(id)) lockedIds.delete(id); else lockedIds.add(id);
        currentBrief.locked_ids = Array.from(lockedIds);
        currentBrief.must_include_ids = Array.from(new Set((currentBrief.must_include_ids || []).concat(Array.from(lockedIds))));
        await buildDay(currentBrief);
        return;
      }
      if (action === 'replace') { await repair(id); return; }
      if (action === 'remove') {
        if (lockedIds.has(id)) { showNote('Unlock this stop before removing it.'); return; }
        excludedIds.add(id);
        currentBrief.activity_count = Math.max(1, Number(currentBrief.activity_count) - 1);
        currentBrief.excluded_ids = Array.from(excludedIds);
        $('#plannerActivityCount').value = String(currentBrief.activity_count);
        await buildDay(currentBrief);
      }
    }));
  }

  async function repair(id) {
    const plan = plans[selectedPlan];
    if (!plan || !currentBrief) return null;
    const serial = ++routeSerial; // A new repair supersedes every previous route check.
    try {
      const result = await post('/api/planner/repair', {
        // Keep exclusions from all prior repairs; the UI's manual exclusions
        // may lag until the server returns its patched brief.
        brief: Object.assign({}, currentBrief, {
          locked_ids:Array.from(new Set([...(currentBrief?.locked_ids || []), ...lockedIds])),
          excluded_ids:Array.from(new Set([...(currentBrief?.excluded_ids || []), ...excludedIds])),
        }),
        plan: plan,
        removed_id: id,
      });
      if (serial !== routeSerial) return null;
      plans = result.plans || [];
      selectedPlan = 0;
      if (result.brief) {
        currentBrief = result.brief;
        lockedIds = new Set(result.brief.locked_ids || []);
        excludedIds = new Set(result.brief.excluded_ids || []);
      }
      renderResult(result);
      const info = plans[0] && plans[0].repair;
      if (info) {
        const shifted = (info.shifted || []).filter(x => x.minutes !== 0);
        const changes = shifted.length ? ' Shifted: ' + shifted.map(x => x.activity_id + ' ' + (x.minutes > 0 ? '+' : '') + x.minutes + ' min').join(', ') + '.' : ' No kept stop changed start time.';
        showNote('Repair kept ' + info.kept_ids.length + ' existing stop(s), replaced ' + info.removed + ' with ' + info.added_ids.join(', ') + '. ' + shifted.length + ' time shift(s).' + changes);
      }
      if (plans.length) await checkRoutes();
      return result;
    } catch (err) {
      if (serial === routeSerial) showNote(err.message);
      return null;
    }
  }

  function showNote(text) {
    $('#plannerRepairNote').textContent = text;
    $('#plannerRepairNote').classList.remove('hidden');
  }

  async function checkRoutes() {
    if (!currentBrief || !plans[selectedPlan]) return;
    const serial = ++routeSerial;
    const startIndex = selectedPlan;
    const lastIndex = Math.min(plans.length, startIndex + 3); // Hard cap on route tool calls.
    const failures = [];
    let lastChecked = startIndex;

    for (let index = startIndex; index < lastIndex; index++) {
      if (serial !== routeSerial) return;
      const candidate = plans[index];
      if (!candidate) break;
      $('#plannerResultsMeta').textContent = 'Checking travel for option ' +
        (index + 1) + ' of ' + plans.length + ' (at most 3 options)…';
      try {
        let checked = candidate;
        if (candidate.route_status !== 'checked') {
          const result = await post('/api/planner/route-check', {brief:currentBrief, plan:candidate});
          if (serial !== routeSerial) return;
          checked = result.plan;
          plans[index] = checked;
        }
        lastChecked = index;
        if (checked.route_status === 'checked' && checked.feasibility !== 'conflict') {
          selectedPlan = index;
          renderSelected();
          renderEvidence();
          $('#plannerResultsMeta').textContent = (index > startIndex
            ? 'Previous route conflicted · automatically validated option ' + (index + 1) + '. '
            : '') + 'Travel checked segment by segment · scheduled transit is not realtime';
          if (index > startIndex) showNote(
            'The previous ' + (index - startIndex) + ' option(s) conflicted with checked travel. ' +
            'Unstuck selected the next route-checked plan without changing your locked events or limits.'
          );
          return;
        }
        failures.push('Option ' + (index + 1) + ': ' +
          ((checked.route_conflicts || []).join('; ') || 'route conflicts with the selected plan.'));
      } catch (err) {
        if (serial !== routeSerial) return;
        // A failed route provider cannot establish that an alternative is feasible.
        // Do not claim success, silently skip constraints or loop indefinitely.
        selectedPlan = index;
        renderSelected();
        renderEvidence();
        $('#plannerResultsMeta').textContent = 'Detailed routing unavailable · keeping estimates';
        showNote('Travel verification stopped: ' + err.message + '. No route was confirmed.');
        return;
      }
    }

    if (serial !== routeSerial) return;
    selectedPlan = lastChecked;
    renderSelected();
    renderEvidence();
    $('#plannerResultsMeta').textContent = 'No route-verified option in ' +
      (lastChecked - startIndex + 1) + ' checked alternative(s)';
    showNote('Route verification could not find a feasible option within the 3-attempt limit. ' +
      failures.join(' ') + ' Edit your constraints or select another variant; no successful route is claimed.');
  }

  function savePlan() {
    const plan = plans[selectedPlan];
    if (!plan || !currentBrief) return;
    if (plan.feasibility === 'conflict') {
      showNote('This plan has a checked route conflict and cannot be saved as a workable itinerary.');
      return;
    }
    const store = readStore();
    const id = plan.id + ':' + plan.date;
    const row = {
      schema_version: STORE_VERSION,
      id: id,
      saved_at: new Date().toISOString(),
      date: plan.date,
      title: plan.items.map((item) => item.title).join(' → '),
      brief: currentBrief,
      plan: plan,
    };
    const index = store.plans.findIndex((x) => x.id === id);
    if (index >= 0) store.plans[index] = row; else store.plans.unshift(row);
    store.plans = store.plans.slice(0, 40);
    writeStore(store);
    showNote('Saved locally in this browser. There is no account sync yet.');
  }

  async function downloadIcs(activityId) {
    const plan = plans[selectedPlan];
    if (!plan) return;
    if (plan.feasibility === 'conflict') {
      showNote('This plan has a checked route conflict; fix it before exporting an itinerary.');
      return;
    }
    const response = await fetch('/api/planner/ics', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({plan:plan, activity_id:activityId || undefined}),
    });
    if (!response.ok) { showNote('ICS export failed (' + response.status + ').'); return; }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = activityId ? 'unstuck-activity.ics' : 'unstuck-' + plan.date + '.ics';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  $('#plannerSavePlan').addEventListener('click', savePlan);
  $('#plannerExportIcs').addEventListener('click', () => downloadIcs(''));

  function initMap() {
    if (map || !window.L) return;
    map = L.map('plannerMap', {zoomControl:true, attributionControl:true}).setView([52.2297,21.0122],12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom:19, attribution:'&copy; OpenStreetMap contributors'
    }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
    routeLayer = L.layerGroup().addTo(map);
  }

  function drawMap(plan) {
    initMap();
    if (!map) return;
    markerLayer.clearLayers();
    routeLayer.clearLayers();
    if (!plan) { map.setView([52.2297,21.0122],12); return; }
    const points = [];
    plan.items.forEach((item, index) => {
      const lat = Number(item.venue && item.venue.lat), lon = Number(item.venue && item.venue.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      points.push([lat,lon]);
      L.marker([lat,lon], {
        icon:L.divIcon({className:'planner-stop-marker',html:'<span>' + (index + 1) + '</span>',iconSize:[28,28],iconAnchor:[14,14]})
      }).bindPopup('<strong>' + esc(item.title) + '</strong><br>' + esc(item.display_start) + '–' + esc(item.display_end)).addTo(markerLayer);
    });
    (plan.travel_legs || []).forEach((leg) => {
      const geometries = [];
      if (Array.isArray(leg.geometry)) geometries.push(leg.geometry);
      (leg.legs || []).forEach((inner) => { if (Array.isArray(inner.geometry)) geometries.push(inner.geometry); });
      geometries.forEach((geometry) => {
        if (geometry.length > 1) {
          L.polyline(geometry, {weight:4,opacity:.72}).addTo(routeLayer);
          geometry.forEach((point) => points.push(point));
        }
      });
    });
    if (points.length) map.fitBounds(L.latLngBounds(points), {padding:[28,28],maxZoom:14});
    setTimeout(() => map.invalidateSize(), 20);
  }

  function switchPlannerView(view) {
    surface.dataset.mobileView = view;
    $$('[data-planner-view]').forEach((button) => button.classList.toggle('active', button.dataset.plannerView === view));
    if (view === 'map') setTimeout(() => map && map.invalidateSize(), 20);
  }
  $$('[data-planner-view]').forEach((button) => button.addEventListener('click', () => switchPlannerView(button.dataset.plannerView)));

  async function loadDemoDay() {
    await selectDate('2026-10-17');
    const central = origins.find((row) => row.id === 'warsaw:srodmiescie:warszawa-centralna') || origins[0];
    const demo = {
      date:'2026-10-17', start_time:'10:00', end_time:'22:30',
      origin:central.label, origin_lat:Number(central.lat), origin_lon:Number(central.lon),
      return_required:true, return_origin:central.label, return_lat:Number(central.lat), return_lon:Number(central.lon),
      people:2, budget_total:500, activity_count:3, pace:'balanced', travel_mode:'transit',
      event_buffer_minutes:15, include_meal:true, categories:[], interests:['art','rock'], taste_refs:['artist: Radiohead'],
      must_include_ids:['event:simple-plan-2026-10-17'], locked_ids:['event:simple-plan-2026-10-17'], excluded_ids:[]
    };
    lockedIds = new Set(demo.locked_ids);
    excludedIds = new Set();
    fillForm(demo);
    $('#plannerMustInclude').value = 'event:simple-plan-2026-10-17';
    showNote('Reproducible demo · 17 Oct 2026 source snapshot (not live event availability). Simple Plan concert stays locked; actual event end and tickets remain unknown.');
    await buildDay(demo);
  }

  $('#plannerDemo').addEventListener('click', loadDemoDay);
  $('#plannerRescueDemo').addEventListener('click', async () => {
    const button = $('#plannerRescueDemo');
    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = 'Rescuing the evening…';
    try {
      await loadDemoDay();
      const original = plans[selectedPlan];
      if (!original?.items?.length) {
        showNote('Demo could not build the original evening within its stated conditions. No rescue was fabricated.');
        return;
      }
      const failed = original.items.find((item) => item.kind === 'restaurant');
      if (!failed) {
        showNote('Demo did not find a restaurant to replace; original evening was left unchanged.');
        return;
      }
      const preservedNames = original.items.filter((item) => item.activity_id !== failed.activity_id)
        .map((item) => item.title);
      const originalNames = original.items.map((item) => item.title);
      // This is explicitly a reported/simulated failure. The app does not know
      // whether the restaurant is really closed or a table is unavailable.
      const result = await repair(failed.activity_id);
      if (!result?.plans?.length) {
        showNote('SIMULATED FAILURE · ' + failed.title + ' was reported unavailable. ' +
          'No alternative fits the existing locks and budget; the concert was not moved.');
        return;
      }
      const repaired = plans[selectedPlan] || result.plans[0];
      const info = result.plans[0].repair || {};
      const actualNames = repaired.items.map((item) => item.title);
      const lockedConcertRetained = repaired.items.some(
        (item) => item.activity_id === 'event:simple-plan-2026-10-17');
      const added = (info.added_ids || []).map(
        (id) => repaired.items.find((item) => item.activity_id === id)?.title || id);
      const timeShifts = (info.shifted || []).filter((item) => item.minutes !== 0);
      const shiftDetail = timeShifts.length
        ? timeShifts.map((item) => item.activity_id + ' ' + (item.minutes > 0 ? '+' : '') +
            item.minutes + ' min').join(', ')
        : 'none';
      const firstOutcome = 'SIMULATED DINNER FAILURE · 17 Oct 2026 (historical scenario; no live closure detected). ' +
        'BEFORE: ' + originalNames.join(' → ') + '. ' +
        'FIRST REPLACEMENT: ' + actualNames.join(' → ') + '. ' +
        'REMOVED: ' + failed.title + '. ADDED: ' + (added.join(', ') || 'none') + '. ' +
        'KEPT: ' + preservedNames.filter((name) => actualNames.includes(name)).join(', ') + '. ' +
        'TIME SHIFTS: ' + shiftDetail + '. ';
      if (!lockedConcertRetained || repaired.feasibility === 'conflict') {
        showNote(firstOutcome + 'Route or lock conflict: no successful second repair is claimed.');
        return;
      }
      // Second *user-reported* failure, not a live closure or booking check.
      // Reuse the actual /api/planner/repair endpoint and the patched excluded_ids.
      // Two attempts are a hard limit: no uncontrolled agent loop.
      const secondFailure = repaired.items.find(item =>
        item.kind === 'restaurant' && item.activity_id !== failed.activity_id);
      if (!secondFailure) {
        showNote(firstOutcome + 'No replacement dinner remained to simulate a second failure.');
        return;
      }
      showNote(firstOutcome + 'FIRST ALTERNATIVE ALSO REPORTED UNAVAILABLE: ' +
        secondFailure.title + '. Looking for one final replacement…');
      const second = await repair(secondFailure.activity_id);
      if (!second?.plans?.length) {
        showNote(firstOutcome + 'SECOND FAILURE: ' + secondFailure.title +
          '. No second feasible replacement exists within the locks and budget. No success is claimed.');
        return;
      }
      const finalPlan = plans[selectedPlan] || second.plans[0];
      const finalNames = finalPlan.items.map(item => item.title);
      const remainingRestaurant = finalPlan.items.find(item => item.kind === 'restaurant');
      const keptConcert = finalPlan.items.some(item =>
        item.activity_id === 'event:simple-plan-2026-10-17');
      const excluded = new Set(currentBrief?.excluded_ids || []);
      const validReplacement = !!remainingRestaurant &&
        !excluded.has(remainingRestaurant.activity_id) &&
        !finalPlan.items.some(item =>
          item.activity_id === failed.activity_id || item.activity_id === secondFailure.activity_id);
      const checkedState = finalPlan.route_status === 'checked' && finalPlan.feasibility !== 'conflict'
        ? 'Travel checked using available routing data (transit is scheduled).'
        : 'Route remains estimated or conflicted; no route validation success is claimed.';
      showNote(firstOutcome +
        'SECOND FAILURE: ' + secondFailure.title + '. ' +
        'AFTER: ' + finalNames.join(' → ') + '. ' +
        'LOCKED CONCERT: ' + (keptConcert ? 'retained' : 'not retained — unusable result') + '. ' +
        'BOTH FAILED RESTAURANTS: ' + (excluded.has(failed.activity_id) && excluded.has(secondFailure.activity_id)
          ? 'excluded' : 'exclusion not confirmed') + '. ' +
        'FINAL SUBSTITUTE: ' + (validReplacement ? remainingRestaurant.title : 'not verified') + '. ' +
        checkedState + ' Ticket inventory, prices and unverified hours still require checking.');
    } catch (err) {
      showNote('Demo could not complete: ' + err.message + '. No success was assumed.');
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  });

  async function ensureLoaded() {
    if (catalog) return;
    const savedDate = localStorage.getItem(LAST_DATE_KEY) || '';
    const today = /^\d{4}-\d{2}-\d{2}$/.test(savedDate) ? savedDate : warsawDate();
    $('#plannerDate').value = today;
    calendarMonth = today.slice(0,7);
    surface.dataset.mobileView = 'plan';
    const loaded = await Promise.all([request('/api/planner/catalog'), request('/api/origins')]);
    catalog = loaded[0];
    origins = loaded[1].origins || [];
    const central = origins.find((row) => row.id === 'warsaw:srodmiescie:warszawa-centralna');
    if (central) {
      $('#plannerOrigin').value = central.label;
      $('#plannerReturnOrigin').value = central.label;
    }
    renderCalendar();
    renderAgenda();
    await loadDateCatalog(today);
    initMap();
  }

  if (localStorage.getItem('unstuck-mode') === 'planner') switchMode('planner');
  else switchMode('rescue');
})();