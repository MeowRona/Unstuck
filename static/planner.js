(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const STORE_KEY = 'unstuck-planner-saved-v1';
  const STORE_VERSION = 1;

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
      (order[a.kind] || 9) - (order[b.kind] || 9) || a.title.localeCompare(b.title)
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
    const error = $('#plannerFormError');
    error.classList.add('hidden');
    try {
      const brief = explicit || await formBrief();
      currentBrief = brief;
      const result = await post('/api/planner/generate', brief);
      plans = result.plans || [];
      selectedPlan = 0;
      renderResult(result);
      if (plans.length) await checkRoutes();
    } catch (err) {
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
        '</span>' + (item.kind === 'event' && item.availability === 'unknown' ? '<span class="timeline-chip unknown">availability unknown</span>' : '') +
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

  function renderEvidence() {
    const body = $('#plannerEvidenceBody');
    if (!catalog) return;
    const coverage = catalog.coverage || {};
    const plan = plans[selectedPlan];
    const used = new Map();
    (plan && plan.items || []).forEach((item) => {
      if (item.source && item.source.url) used.set(item.source.url, item.source);
    });
    body.innerHTML = '<p><strong>Event coverage:</strong> ' + esc(coverage.event_sources_loaded_from) + ' → ' +
      esc(coverage.event_sources_loaded_through) + '. ' + esc(coverage.scope) + '</p>' +
      '<p><strong>No-results semantics:</strong> ' + esc(coverage.no_results_meaning) + '</p>' +
      '<p><strong>Routing:</strong> initial plans use estimates; selected plans are checked leg by leg. Warsaw transit is scheduled, not realtime.</p>' +
      '<p><strong>Taste:</strong> ' + ((plan && plan.taste_status === 'not_live') ? 'Qloo was not called. Taste references do not affect ranking yet.' : 'No taste matching requested.') + '</p>' +
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
    $('#plannerTasteStatus').textContent = result.taste_status === 'not_live' ? 'Taste matching not live yet' : 'Taste not requested';
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
    try {
      const result = await post('/api/planner/repair', {
        brief: Object.assign({}, currentBrief, {locked_ids:Array.from(lockedIds), excluded_ids:Array.from(excludedIds)}),
        plan: plan,
        removed_id: id,
      });
      plans = result.plans || [];
      selectedPlan = 0;
      if (result.brief) currentBrief = result.brief;
      renderResult(result);
      const info = plans[0] && plans[0].repair;
      if (info) showNote('Repair kept ' + info.kept_ids.length + ' existing stop(s), removed one, and added ' + info.added_ids.length + '. Locked stops stayed fixed.');
      if (plans.length) await checkRoutes();
    } catch (err) {
      showNote(err.message);
    }
  }

  function showNote(text) {
    $('#plannerRepairNote').textContent = text;
    $('#plannerRepairNote').classList.remove('hidden');
  }

  async function checkRoutes() {
    const plan = plans[selectedPlan];
    if (!plan || !currentBrief || plan.route_status === 'checked') return;
    const serial = ++routeSerial;
    $('#plannerResultsMeta').textContent = 'Checking each travel leg at the correct departure time…';
    try {
      const result = await post('/api/planner/route-check', {brief:currentBrief, plan:plan});
      if (serial !== routeSerial) return;
      plans[selectedPlan] = result.plan;
      renderSelected();
      renderEvidence();
      $('#plannerResultsMeta').textContent = result.plan.feasibility === 'conflict'
        ? 'Checked route found a conflict'
        : 'Travel checked segment by segment · scheduled transit is not realtime';
    } catch (err) {
      if (serial !== routeSerial) return;
      $('#plannerResultsMeta').textContent = 'Detailed routing unavailable · keeping estimates';
      showNote(err.message);
    }
  }

  function savePlan() {
    const plan = plans[selectedPlan];
    if (!plan || !currentBrief) return;
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

  $('#plannerDemo').addEventListener('click', async () => {
    await selectDate('2026-10-17');
    const central = origins.find((row) => row.id === 'warsaw:srodmiescie:warszawa-centralna') || origins[0];
    const demo = {
      date:'2026-10-17', start_time:'10:00', end_time:'22:30',
      origin:central.label, origin_lat:Number(central.lat), origin_lon:Number(central.lon),
      return_required:true, return_origin:central.label, return_lat:Number(central.lat), return_lon:Number(central.lon),
      people:2, budget_total:500, activity_count:3, pace:'balanced', travel_mode:'transit',
      include_meal:true, categories:[], interests:['art','rock'], taste_refs:['Radiohead'],
      must_include_ids:['event:simple-plan-2026-10-17'], locked_ids:['event:simple-plan-2026-10-17'], excluded_ids:[]
    };
    lockedIds = new Set(demo.locked_ids);
    excludedIds = new Set();
    fillForm(demo);
    $('#plannerMustInclude').value = 'event:simple-plan-2026-10-17';
    showNote('Demo day · 17 Oct 2026 · verified source snapshot. Simple Plan is locked; actual event end and ticket availability remain unknown.');
    await buildDay(demo);
  });

  $('#plannerDate').addEventListener('change', () => selectDate($('#plannerDate').value));

  async function ensureLoaded() {
    if (catalog) return;
    const today = warsawDate();
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