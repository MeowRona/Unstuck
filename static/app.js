function localDateString(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function localTimeString(value) {
  return `${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`;
}

function localPlanningDefaults(now = new Date()) {
  const start = new Date(now);
  start.setSeconds(0, 0);
  start.setMinutes(Math.ceil(start.getMinutes() / 5) * 5);
  const back = new Date(start.getTime() + 3 * 60 * 60 * 1000);
  return {
    date: localDateString(start),
    start_time: localTimeString(start),
    return_by: localTimeString(back),
  };
}

function judgeDemoEvening(now = new Date()) {
  const demo = new Date(now);
  if (demo.getHours() > 17 || (demo.getHours() === 17 && demo.getMinutes() > 30)) {
    demo.setDate(demo.getDate() + 1);
  }
  return {
    date: localDateString(demo),
    start_time: '18:30',
    return_by: '22:00',
  };
}

function makeDefaultBrief() {
  const local = localPlanningDefaults();
  return {
  original_plan: 'Dinner',
  failed_place: '',
  failure_reason: '',
  goal: 'meal',
  city: 'Warsaw',
  date: local.date,
  start_time: local.start_time,
  return_by: local.return_by,
  min_stay_minutes: 75,
  people: 2,
  budget_total: 200,
  currency: 'PLN',
  origin: 'Warszawa Centralna',
  origin_lat: null,
  origin_lon: null,
  travel_mode: 'transit',
  max_one_way_minutes: 20,
  categories: ['restaurant'],
  taste_refs: ['Amelie', 'Radiohead'],
  meal_required: true,
  negotiable_extra_travel_minutes: 10,
  negotiable_stay_reduction_minutes: 15,
  allow_category_change: false,
  };
}

const DEFAULT_BRIEF = makeDefaultBrief();

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

const workspace = $('.workspace');
const firstRun = $('#firstRun');
const searchingState = $('#searchingState');
const resultContent = $('#resultContent');
const cardsEl = $('#cards');
const emptyState = $('#emptyState');
const resultActions = $('#resultActions');
const chooseButton = $('#chooseButton');
const lockCompromiseButton = $('#lockCompromiseButton');
const resultMeta = $('#resultMeta');
const routePanel = $('#routePanel');
const dataStatus = $('#dataStatus');
const editorModal = $('#editorModal');
const editorBackdrop = $('#editorBackdrop');
const editorForm = $('#editorForm');
const editorError = $('#editorError');
const menuButton = $('#menuButton');
const menuPopover = $('#menuPopover');
const themeToggle = $('#themeToggle');
const menuThemeLabel = $('#menuThemeLabel');
const choiceModal = $('#choiceModal');
const choiceBackdrop = $('#choiceBackdrop');
const originInput = $('#originInput');
const originSuggestions = $('#originSuggestions');
const originResolution = $('#originResolution');
const useCurrentLocation = $('#useCurrentLocation');

let draftBrief = structuredClone(DEFAULT_BRIEF);
let sessionId = null;
let activeResult = null;
let selectedIndex = 0;
let requestSerial = 0;
let routeRequestSerial = 0;
let statusInfo = null;
let origins = [];
let editorWheelsReady = false;
let editorReturnFocus = null;
let choiceReturnFocus = null;
let rejectReturnFocus = null;
let aboutReturnFocus = null;
let pendingRejectPlaceId = null;

let map = null;
let tileLayer = null;
let resultLayer = null;
let guideLayer = null;
let actualRouteLayer = null;
let routeBadgeMarker = null;
let markerRefs = [];
let originMarker = null;
let tileErrorCount = 0;

const WHEEL_ROW_HEIGHT = 42;
const durationWheelSetters = new Map();
const timeWheelSetters = new Map();

const ICONS = {
  pin: '<path d="M12 21s6-5.2 6-11a6 6 0 1 0-12 0c0 5.8 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  meal: '<path d="M6 3v7M3.8 3v5.2A2 2 0 0 0 6 10.3a2 2 0 0 0 2.2-2.1V3M6 10.3V21M16 3v18M16 3c2.5 1.2 3.5 4.6 2.5 7H16"/>',
  edit: '<path d="M4 20h4l11-11-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
  coins: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v4c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 10v4c0 1.7 3.1 3 7 3s7-1.3 7-3v-4"/>',
  lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  car: '<path d="m5 11 1.6-4h10.8L19 11M4 11h16v6H4z"/><circle cx="7" cy="17" r="1.5"/><circle cx="17" cy="17" r="1.5"/>',
  hourglass: '<path d="M7 3h10M7 21h10M8 3c0 4 1.5 6 4 8-2.5 2-4 4-4 10M16 3c0 4-1.5 6-4 8 2.5 2 4 4 4 10"/>',
  tag: '<path d="M20 13 13 20l-9-9V4h7l9 9Z"/><circle cx="8.5" cy="8.5" r="1.4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  map: '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z"/><path d="M9 3v15M15 6v15"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  arrow: '<path d="M5 12h14M14 7l5 5-5 5"/>',
  moon: '<path d="M20.5 14.3A8.2 8.2 0 0 1 9.7 3.5 8.7 8.7 0 1 0 20.5 14.3Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  crosshair: '<circle cx="12" cy="12" r="4"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>',
};

function preferredTheme() {
  const saved = localStorage.getItem('unstuck-theme');
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme, {persist = false} = {}) {
  const next = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next;
  if (persist) localStorage.setItem('unstuck-theme', next);
  const dark = next === 'dark';
  if (themeToggle) {
    themeToggle.dataset.iconState = dark ? 'sun' : 'moon';
    themeToggle.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
    themeToggle.title = dark ? 'Light mode' : 'Dark mode';
    const slot = themeToggle.querySelector('[data-icon]');
    if (slot) {
      slot.dataset.icon = dark ? 'sun' : 'moon';
      slot.innerHTML = iconSvg(slot.dataset.icon);
    }
  }
  if (menuThemeLabel) menuThemeLabel.textContent = dark ? 'Light mode' : 'Dark mode';
  setTimeout(() => map?.invalidateSize(false), 0);
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', {persist: true});
}

function iconSvg(name) {
  return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.info}</svg>`;
}

function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach(node => {
    node.innerHTML = iconSvg(node.dataset.icon);
  });
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function googleMapsUrl(card) {
  if (!card.google_place_id) return '';
  const params = new URLSearchParams({
    api: '1',
    query: [card.name, card.address].filter(Boolean).join(', '),
    query_place_id: card.google_place_id,
  });
  return `https://www.google.com/maps/search/?${params.toString()}`;
}

function starRatingHtml(rating) {
  const numeric = Math.max(0, Math.min(5, Number(rating) || 0));
  const width = `${(numeric / 5) * 100}%`;
  return `<span class="google-stars" aria-hidden="true"><span class="google-stars-base">★★★★★</span><span class="google-stars-fill" style="width:${width}">★★★★★</span></span>`;
}

function compactReviewCount(value) {
  const count = Number(value) || 0;
  if (count >= 1000) return `${(count / 1000).toFixed(count >= 10000 ? 0 : 1).replace('.0', '')}k`;
  return String(count);
}

async function hydrateGooglePlaceMedia(cards) {
  const targets = cards.filter(card => card.google_place_id);
  await Promise.all(targets.map(async card => {
    const placeId = card.google_place_id;
    const thumb = document.querySelector(`.venue-thumb[data-google-place-id="${CSS.escape(placeId)}"]`);
    const ratingEl = document.querySelector(`.google-rating-card[data-google-place-id="${CSS.escape(placeId)}"]`);
    if (!thumb || !ratingEl) return;
    try {
      const payload = await fetchJson(`/api/place-media?place_id=${encodeURIComponent(placeId)}`);
      const mapsUri = payload.google_maps_uri || googleMapsUrl(card);
      ratingEl.href = mapsUri;
      if (!payload.available) return;

      if (payload.rating != null) {
        const rating = Number(payload.rating);
        ratingEl.classList.add('loaded');
        ratingEl.setAttribute('aria-label', `${rating.toFixed(1)} out of 5 on Google Maps, ${payload.user_rating_count || 0} reviews`);
        ratingEl.innerHTML = `${starRatingHtml(rating)}<span class="google-rating-number">${rating.toFixed(1)}</span><span class="google-review-count">(${compactReviewCount(payload.user_rating_count)})</span><span class="google-source">Google Maps</span>`;
      }

      if (payload.photo?.uri) {
        thumb.classList.add('has-google-photo');
        thumb.style.backgroundImage = `url("${String(payload.photo.uri).replace(/"/g, '%22')}")`;
        thumb.setAttribute('aria-label', `Google Maps place photo for ${card.name}`);
        const authors = Array.isArray(payload.photo.author_attributions) ? payload.photo.author_attributions : [];
        if (authors.length) {
          const attribution = thumb.querySelector('.google-photo-attribution');
          const first = authors[0] || {};
          const displayName = escapeHtml(first.displayName || 'photo contributor');
          const authorUri = first.uri ? String(first.uri) : '';
          attribution.innerHTML = authorUri
            ? `Photo: <a href="${escapeHtml(authorUri)}" target="_blank" rel="noreferrer">${displayName}</a> · Google Maps`
            : `Photo: ${displayName} · Google Maps`;
          attribution.classList.remove('hidden');
        }
      }
    } catch {
      // Keep the honest fallback and direct Google Maps link if Places is unavailable.
    }
  }));
}

function titleCase(value) {
  return String(value || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase());
}

function peoplePhrase(count) {
  const words = {1: 'one', 2: 'two', 3: 'three', 4: 'four'};
  return words[count] || String(count);
}

function planTitle(brief) {
  const noun = brief.goal === 'meal' ? 'Dinner' : brief.goal === 'coffee' ? 'Coffee' : brief.goal === 'culture' ? 'Culture' : 'Plan';
  return `${noun} for ${peoplePhrase(Number(brief.people))}.`;
}

function tasteSummary(brief) {
  const refs = brief.taste_refs || [];
  if (!refs.length) return 'Not set';
  if (refs.length === 1) return refs[0];
  return `${refs[0]} + ${refs[1]}${refs.length > 2 ? ` +${refs.length - 2}` : ''}`;
}

function updateSummary(brief) {
  $('#summaryPlanTitle').textContent = planTitle(brief);
  $('#summaryBudget').textContent = `${Number(brief.budget_total).toFixed(Number(brief.budget_total) % 1 ? 2 : 0)} ${brief.currency || 'PLN'}`;
  $('#summaryReturn').textContent = brief.return_by;
  $('#summaryTravel').textContent = `${brief.max_one_way_minutes} min`;
  $('#summaryStay').textContent = `${brief.min_stay_minutes} min`;
  $('#summaryTaste').textContent = tasteSummary(brief);

  const travelChip = $('[data-edit-target="travel"]');
  const stayChip = $('[data-edit-target="stay"]');
  const extraTravel = Number(brief.negotiable_extra_travel_minutes || 0);
  const shorterStay = Number(brief.negotiable_stay_reduction_minutes || 0);
  travelChip.classList.toggle('flexible', extraTravel > 0);
  stayChip.classList.toggle('flexible', shorterStay > 0);
  $('#summaryTravelWrap').title = extraTravel > 0 ? `May extend by up to ${extraTravel} min if strict search fails` : 'Locked at this travel limit';
  $('#summaryStayWrap').title = shorterStay > 0 ? `May shorten by up to ${shorterStay} min if strict search fails` : 'Locked at this minimum stay';
  const travelState = $('#travelChipState');
  const stayState = $('#stayChipState');
  travelState.dataset.icon = extraTravel > 0 ? 'edit' : 'lock';
  stayState.dataset.icon = shorterStay > 0 ? 'edit' : 'lock';
  travelState.innerHTML = iconSvg(travelState.dataset.icon);
  stayState.innerHTML = iconSvg(stayState.dataset.icon);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function showSearching() {
  firstRun.classList.add('hidden');
  resultContent.classList.add('hidden');
  searchingState.classList.remove('hidden');
}

function showRequestError(message) {
  searchingState.classList.add('hidden');
  resultContent.classList.remove('hidden');
  cardsEl.innerHTML = '';
  resultActions.classList.add('hidden');
  emptyState.classList.remove('hidden');
  emptyState.innerHTML = `<h3>That search could not be completed.</h3><p>${escapeHtml(message)}</p><button class="secondary-button" type="button" id="retryEdit">Edit the plan</button>`;
  $('#retryEdit')?.addEventListener('click', () => openEditor('plan'));
}

async function runLatest(path, body) {
  const serial = ++requestSerial;
  showSearching();
  try {
    const payload = await fetchJson(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (serial !== requestSerial) return null;
    sessionId = payload.session_id;
    renderResult(payload);
    return payload;
  } catch (error) {
    if (serial !== requestSerial) return null;
    showRequestError(error.message);
    return null;
  }
}

function originCoords(name) {
  const match = origins.find(row => row.label === name || row.id === name);
  if (match && Number.isFinite(Number(match.lat)) && Number.isFinite(Number(match.lon))) return [Number(match.lat), Number(match.lon)];
  const fallbacks = {
    'Warsaw Central': [52.2297, 21.0122],
    'Warszawa Centralna': [52.2289, 21.0034],
    'Old Town': [52.2497, 21.0122],
    'Rondo Daszynskiego': [52.2306, 20.9847],
  };
  return fallbacks[name] || [52.2297, 21.0122];
}

function hasFiniteCoordinates(lat, lon) {
  return lat !== null && lat !== undefined && lat !== ''
    && lon !== null && lon !== undefined && lon !== ''
    && Number.isFinite(Number(lat))
    && Number.isFinite(Number(lon));
}

function briefOriginCoords(brief) {
  if (hasFiniteCoordinates(brief?.origin_lat, brief?.origin_lon)) {
    return [Number(brief.origin_lat), Number(brief.origin_lon)];
  }
  return originCoords(brief?.origin || 'Warszawa Centralna');
}

function initMap() {
  if (!window.L) {
    $('#mapFallback').classList.remove('hidden');
    return;
  }
  map = L.map('map', {zoomControl: true, attributionControl: true, preferCanvas: true}).setView([52.2297, 21.0122], 12);
  map.attributionControl.setPrefix(false);
  tileLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
  }).addTo(map);
  tileLayer.on('tileload', () => {
    tileErrorCount = 0;
    $('#mapFallback').classList.add('hidden');
  });
  tileLayer.on('tileerror', () => {
    tileErrorCount += 1;
    if (tileErrorCount >= 6) $('#mapFallback').classList.remove('hidden');
  });
  resultLayer = L.layerGroup().addTo(map);
  guideLayer = L.layerGroup().addTo(map);
  actualRouteLayer = L.layerGroup().addTo(map);
}

function placeIcon(letter, selected) {
  return L.divIcon({
    className: `place-marker${selected ? ' selected' : ''}`,
    html: `<div class="place-marker-inner"><span>${letter}</span></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 29],
  });
}

function originIcon() {
  return L.divIcon({className: 'origin-marker', html: '<div class="origin-marker-inner"></div>', iconSize: [34,34], iconAnchor: [17,17]});
}

function validCardLocation(card) {
  return card?.location && Number.isFinite(Number(card.location.lat)) && Number.isFinite(Number(card.location.lon));
}

function refreshGuideLine() {
  if (!map || !activeResult || !activeResult.cards?.length) return;
  guideLayer.clearLayers();
  const card = activeResult.cards[selectedIndex];
  if (!validCardLocation(card)) return;
  const from = briefOriginCoords(activeResult.brief);
  const to = [Number(card.location.lat), Number(card.location.lon)];
  L.polyline([from, to], {color: '#275de8', weight: 3, opacity: .76, dashArray: '7 8', lineCap: 'round'}).addTo(guideLayer);
  $('#mapGuideLabel').textContent = 'Approx. straight-line guide · not a routed journey';
}

function renderMap(result, fitView = true) {
  if (!map || !resultLayer) return;
  resultLayer.clearLayers();
  guideLayer.clearLayers();
  markerRefs = [];
  originMarker = null;
  const points = [];
  const origin = briefOriginCoords(result.brief);
  originMarker = L.marker(origin, {icon: originIcon(), keyboard: true, title: `Start: ${result.brief.origin}`}).addTo(resultLayer);
  originMarker.bindTooltip(`Start · ${escapeHtml(result.brief.origin)}`, {direction: 'top'});
  points.push(origin);

  result.cards.forEach((card, index) => {
    if (!validCardLocation(card)) return;
    const coords = [Number(card.location.lat), Number(card.location.lon)];
    const marker = L.marker(coords, {icon: placeIcon(String.fromCharCode(65 + index), index === selectedIndex), keyboard: true, title: card.name}).addTo(resultLayer);
    marker.on('click', () => selectCard(index, {fromMap: true}));
    marker.bindTooltip(`${String.fromCharCode(65 + index)} · ${escapeHtml(card.name)}`, {direction: 'top'});
    markerRefs[index] = marker;
    points.push(coords);
  });

  refreshGuideLine();
  if (fitView && points.length > 1) {
    map.fitBounds(L.latLngBounds(points), {padding: [44, 44], maxZoom: 14, animate: false});
  } else if (fitView) {
    map.setView(origin, 13, {animate: false});
  }
  setTimeout(() => map.invalidateSize(false), 0);
}

function updateMarkerSelection() {
  markerRefs.forEach((marker, index) => {
    if (!marker) return;
    marker.setIcon(placeIcon(String.fromCharCode(65 + index), index === selectedIndex));
  });
  refreshGuideLine();
}

function formatMoney(card) {
  const cost = card.cost || {};
  if (cost.min == null || cost.max == null) return 'Unknown';
  const min = Number(cost.min);
  const max = Number(cost.max);
  return min === max ? `${max.toFixed(0)} ${cost.currency}` : `${min.toFixed(0)}–${max.toFixed(0)} ${cost.currency}`;
}

function changeBadge(card) {
  const changes = card.change || [];
  if (!changes.length) {
    return card.feasibility_status === 'confirmed'
      ? '<span class="change-badge none">No compromise</span>'
      : '<span class="change-badge checking">No detected compromise · verify facts</span>';
  }
  const labels = changes.map(change => {
    if (change.field === 'one-way travel') return `+${change.delta || 0} min travel`;
    if (change.field === 'minimum stay') return `−${change.delta || 0} min stay`;
    if (change.field === 'category') return 'Category change';
    return titleCase(change.field);
  });
  return `<span class="change-badge">${escapeHtml(labels.join(' · '))}</span>`;
}

function sourceLink(label, source) {
  if (!source) return '';
  const status = source.status ? ` · ${source.status}` : '';
  const checked = source.checked_at ? ` · checked ${source.checked_at}` : '';
  const anchor = source.url ? ` · <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">source</a>` : '';
  return `<div><strong>${escapeHtml(label)}</strong>${escapeHtml(status)}${escapeHtml(checked)}${anchor}</div>`;
}

function travelSourceHtml(card) {
  const timing = card.timing || {};
  if (timing.travel_is_estimate) {
    return '<div><strong>Travel</strong> · conservative search estimate; outbound and return routes are not checked yet.</div>';
  }
  const checked = timing.travel_checked_at ? ` · checked ${escapeHtml(timing.travel_checked_at)}` : '';
  const source = timing.travel_source ? escapeHtml(timing.travel_source) : 'checked route';
  const link = timing.travel_source_url ? ` · <a href="${escapeHtml(timing.travel_source_url)}" target="_blank" rel="noreferrer">source</a>` : '';
  const freshness = timing.travel_realtime ? 'realtime' : (activeResult?.brief?.travel_mode === 'transit' ? 'scheduled, not realtime' : 'street route, not realtime');
  return `<div><strong>Travel</strong> · ${source} · ${freshness}${checked}${link}</div>`;
}

function tasteTags(card) {
  const evidence = Array.isArray(card.taste?.evidence) ? card.taste.evidence.slice(0, 3) : [];
  const source = card.taste?.source;
  const tags = [];
  if (source === 'fixture') tags.push('<span class="taste-tag">Taste preview · Qloo pending</span>');
  else if (source === 'qloo') tags.push('<span class="taste-tag">Live Qloo signal</span>');
  else tags.push('<span class="taste-tag">Feasibility only</span>');
  evidence.forEach(item => tags.push(`<span class="taste-tag">${escapeHtml(item)}</span>`));
  if (card.needs_checking?.length) tags.push(`<span class="taste-tag needs-chip">${card.needs_checking.length} item${card.needs_checking.length === 1 ? '' : 's'} to check</span>`);
  return tags.join('');
}

function constraintStatusHtml(card) {
  const checks = Array.isArray(card.constraint_checks) ? card.constraint_checks : [];
  if (!checks.length) return '';
  const labels = {kept: 'Kept', changed: 'Changed', unknown: 'Check'};
  return `<div class="constraint-status-row" aria-label="Condition status">${checks.map(check =>
    `<span class="constraint-chip ${escapeHtml(check.status)}" title="${escapeHtml(check.detail || '')}"><b>${labels[check.status] || 'Check'}</b> ${escapeHtml(check.label)}</span>`
  ).join('')}</div>`;
}

function cardHtml(card, index, brief) {
  const letter = String.fromCharCode(65 + index);
  const stayDelta = Math.max(0, Number(brief.min_stay_minutes) - Number(card.timing.stay_minutes));
  const subline = `${titleCase(card.category)} · ${card.feasibility_status === 'confirmed' ? 'conditions confirmed with current data' : 'some facts need verification'} · ${card.address || 'Warsaw'}`;
  const needs = (card.needs_checking || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const mapsUrl = googleMapsUrl(card);
  const googlePlaceAttrs = card.google_place_id ? ` data-google-place-id="${escapeHtml(card.google_place_id)}"` : '';
  const timing = card.timing || {};
  const travelStrong = timing.travel_is_estimate
    ? `${timing.travel_one_way_minutes} min`
    : `${timing.travel_one_way_minutes} min out`;
  const travelCaption = timing.travel_is_estimate
    ? 'one-way · search estimate'
    : `back ${timing.travel_return_minutes} min · ${brief.travel_mode === 'transit' ? 'scheduled route' : 'street route'}`;
  return `<article class="recommendation-card${index === selectedIndex ? ' selected' : ''}" data-card-index="${index}" tabindex="0" aria-label="Option ${letter}: ${escapeHtml(card.name)}">
    <div class="venue-thumb${card.google_place_id ? ' google-backed' : ''}" data-category="${escapeHtml(card.category)}"${googlePlaceAttrs} role="img" aria-label="Neutral image fallback; no verified photo for ${escapeHtml(card.name)}">
      <div class="card-letter"><span>${letter}</span></div>
      ${card.google_place_id ? `<a class="google-rating-card" data-google-place-id="${escapeHtml(card.google_place_id)}" href="${escapeHtml(mapsUrl)}" target="_blank" rel="noreferrer" aria-label="Open ${escapeHtml(card.name)} in Google Maps"><span class="google-maps-fallback">Google Maps ↗</span></a><div class="google-photo-attribution hidden"></div>` : ''}
    </div>
    <div class="card-body">
      <div class="card-heading">
        <div class="card-title"><h3>${escapeHtml(card.name)}</h3><div class="card-subline">${escapeHtml(subline)}</div></div>
        ${changeBadge(card)}
      </div>
      <div class="why-block"><strong>Why it fits</strong><p>${escapeHtml(card.why_this_fits)}</p></div>
      ${constraintStatusHtml(card)}
      <div class="metrics-row">
        <div class="metric">${iconSvg('coins')}<div class="metric-copy"><strong>${escapeHtml(formatMoney(card))}</strong><span>${card.cost?.source?.status === 'confirmed' || card.cost?.source?.status === 'fixture' ? 'total estimate' : 'price not verified'} · ${card.cost.for_people} people</span></div></div>
        <div class="metric route-time-metric">${iconSvg('car')}<div class="metric-copy"><strong>${escapeHtml(travelStrong)}</strong><span>${escapeHtml(travelCaption)}</span></div></div>
        <div class="metric">${iconSvg('hourglass')}<div class="metric-copy"><strong>${card.timing.stay_minutes} min${stayDelta ? `<span class="metric-delta">−${stayDelta}</span>` : ''}</strong><span>stay</span></div></div>
      </div>
      <div class="taste-row"><strong>Taste profile</strong>${tasteTags(card)}</div>
      <div class="card-footer-line">
        <button type="button" class="sources-toggle" data-card-index="${index}">Sources & assumptions</button>
        ${card.google_place_id ? `<span>·</span><a href="${escapeHtml(mapsUrl)}" target="_blank" rel="noreferrer">Google Maps</a>` : ''}
        <span>·</span>
        <button type="button" class="reject-inline" data-place-id="${escapeHtml(card.id)}">Not for me</button>
      </div>
      <div class="card-source-panel hidden" data-source-panel="${index}">
        ${sourceLink('Price', card.cost?.source)}
        ${sourceLink('Hours', card.hours_source)}
        ${card.location_source?.url ? `<div><strong>Location</strong> · <a href="${escapeHtml(card.location_source.url)}" target="_blank" rel="noreferrer">source</a>${card.location_source.checked_at ? ` · checked ${escapeHtml(card.location_source.checked_at)}` : ''}</div>` : '<div><strong>Location</strong> · catalog coordinates</div>'}
        ${card.google_place_id ? `<div><strong>Google Maps</strong> · Places API is currently disabled; this link opens the listing without loading paid Places data. · <a href="${escapeHtml(mapsUrl)}" target="_blank" rel="noreferrer">open listing</a></div>` : ''}
        ${travelSourceHtml(card)}
        ${needs ? `<div><strong>Needs checking</strong><ul>${needs}</ul></div>` : '<div><strong>Needs checking</strong> · nothing material flagged by the current data status.</div>'}
      </div>
    </div>
  </article>`;
}


function bindResultCardEvents() {
  $$('.recommendation-card').forEach(card => {
    const index = Number(card.dataset.cardIndex);
    card.addEventListener('click', event => {
      if (event.target.closest('button,a')) return;
      selectCard(index);
    });
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectCard(index);
      }
    });
  });
  $$('.sources-toggle').forEach(button => button.addEventListener('click', event => {
    event.stopPropagation();
    const panel = document.querySelector(`[data-source-panel="${button.dataset.cardIndex}"]`);
    panel?.classList.toggle('hidden');
  }));
  $('.reject-inline').forEach(button => button.addEventListener('click', event => {
    event.stopPropagation();
    if (!sessionId) return;
    openReject(button.dataset.placeId);
  }));
}

function selectCard(index, {fromMap = false} = {}) {
  if (!activeResult?.cards?.[index]) return;
  selectedIndex = index;
  $$('.recommendation-card').forEach((card, cardIndex) => card.classList.toggle('selected', cardIndex === index));
  updateMarkerSelection();
  updateResultActions();
  loadSelectedRoute();
  if (fromMap) {
    const card = document.querySelector(`[data-card-index="${index}"]`);
    card?.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest'});
  }
}

function selectedCompromise() {
  const card = activeResult?.cards?.[selectedIndex];
  if (!card) return null;
  return (card.change || [])[0] || null;
}

function updateResultActions() {
  const card = activeResult?.cards?.[selectedIndex];
  if (!card) {
    resultActions.classList.add('hidden');
    return;
  }
  resultActions.classList.remove('hidden');
  chooseButton.innerHTML = `<span class="action-button-icon">${iconSvg('check')}</span><span class="action-button-copy"><strong>Choose this plan</strong><small>${escapeHtml(card.name)}</small></span>`;
  const change = selectedCompromise();
  if (!change) {
    lockCompromiseButton.disabled = true;
    lockCompromiseButton.innerHTML = card.feasibility_status === 'confirmed'
      ? `<span class="action-button-icon">${iconSvg('lock')}</span><span class="action-button-copy"><strong>Checked conditions kept</strong><small>No compromise to undo</small></span>`
      : `<span class="action-button-icon">${iconSvg('info')}</span><span class="action-button-copy"><strong>No compromise detected</strong><small>Some facts still need verification</small></span>`;
  } else if (change.field === 'one-way travel') {
    lockCompromiseButton.disabled = false;
    lockCompromiseButton.innerHTML = `<span class="action-button-icon">${iconSvg('car')}</span><span class="action-button-copy"><strong>Keep travel at ${activeResult.brief.max_one_way_minutes} min</strong><small>Re-run without extra travel</small></span>`;
  } else if (change.field === 'minimum stay') {
    lockCompromiseButton.disabled = false;
    lockCompromiseButton.innerHTML = `<span class="action-button-icon">${iconSvg('hourglass')}</span><span class="action-button-copy"><strong>Keep stay at ${activeResult.brief.min_stay_minutes} min</strong><small>Re-run without shorter stay</small></span>`;
  } else if (change.field === 'category') {
    lockCompromiseButton.disabled = false;
    lockCompromiseButton.innerHTML = `<span class="action-button-icon">${iconSvg('tag')}</span><span class="action-button-copy"><strong>Keep original category</strong><small>Re-run without category change</small></span>`;
  } else {
    lockCompromiseButton.disabled = true;
    lockCompromiseButton.innerHTML = `<span class="action-button-icon">${iconSvg('info')}</span><span class="action-button-copy"><strong>No editable compromise</strong><small>Review the condition status above</small></span>`;
  }
}

function routeColor(routeType, color) {
  if (color && /^[0-9a-f]{6}$/i.test(color)) return `#${color}`;
  if (routeType === 0) return '#b60000';
  if (routeType === 1 || routeType === 2) return '#3159a6';
  return '#5c4aa6';
}

function clearActualRoute() {
  actualRouteLayer?.clearLayers();
  if (routeBadgeMarker && map) {
    map.removeLayer(routeBadgeMarker);
    routeBadgeMarker = null;
  }
}

function routeStepHtml(leg) {
  if (leg.type === 'walk') {
    return `<div class="route-step walk"><div class="route-step-dot">${iconSvg('pin')}</div><div><strong>Walk ${escapeHtml(leg.duration_minutes)} min</strong><span>${escapeHtml(leg.from)} → ${escapeHtml(leg.to)}</span></div></div>`;
  }
  if (leg.type === 'transfer') {
    return `<div class="route-step transfer"><div class="route-step-dot">${iconSvg('arrow')}</div><div><strong>Transfer at ${escapeHtml(leg.from)} · ${escapeHtml(leg.duration_minutes)} min</strong><span>Platform/stop change inside the same interchange</span></div></div>`;
  }
  const color = routeColor(leg.route_type, leg.color);
  const intermediate = Array.isArray(leg.intermediate_stops) ? leg.intermediate_stops : [];
  const stopNames = [leg.from, ...intermediate, leg.to].filter(Boolean);
  return `<div class="route-step transit"><div class="route-line-badge" style="--route-color:${color}">${escapeHtml(leg.route)}</div><div><strong>${escapeHtml(leg.departure)} → ${escapeHtml(leg.arrival)} · ${escapeHtml(leg.stop_count)} stop${Number(leg.stop_count) === 1 ? '' : 's'}</strong><span>${escapeHtml(leg.from)} → ${escapeHtml(leg.to)}${leg.headsign ? ` · toward ${escapeHtml(leg.headsign)}` : ''}</span>${stopNames.length > 2 ? `<details class="route-stop-details"><summary>Show stops</summary><div>${stopNames.map(name => `<span>${escapeHtml(name)}</span>`).join('')}</div></details>` : ''}</div></div>`;
}

function renderActualRoute(route) {
  clearActualRoute();
  guideLayer?.clearLayers();
  const card = activeResult?.cards?.[selectedIndex];
  if (card) card._actualRoute = route;
  const points = [];
  if (route.mode === 'walk') {
    if (route.geometry?.length) {
      L.polyline(route.geometry, {color: '#275de8', weight: 5, opacity: .9, lineCap: 'round'}).addTo(actualRouteLayer);
      points.push(...route.geometry);
    }
    routePanel.innerHTML = `<div class="route-panel-head"><div><strong>${escapeHtml(route.duration_minutes)} min walk · ${escapeHtml(route.distance_km)} km</strong><span>Shortest street route from Valhalla / OpenStreetMap</span></div><span class="route-source-badge">street route</span></div>`;
  } else {
    const legs = route.legs || [];
    legs.forEach(leg => {
      const geometry = leg.geometry || [];
      if (geometry.length < 2) return;
      const style = leg.type === 'transit'
        ? {color: routeColor(leg.route_type, leg.color), weight: 6, opacity: .9, lineCap: 'round'}
        : {color: '#51627e', weight: 3, opacity: .74, dashArray: '4 7', lineCap: 'round'};
      L.polyline(geometry, style).addTo(actualRouteLayer);
      points.push(...geometry);
    });
    routePanel.innerHTML = `<div class="route-panel-head"><div><strong>${escapeHtml(route.duration_minutes)} min · ${escapeHtml(route.summary || 'Public transport')}</strong><span>Leave ${escapeHtml(route.departure)} · arrive ${escapeHtml(route.arrival)} · ${escapeHtml(route.transfers)} transfer${Number(route.transfers) === 1 ? '' : 's'} · scheduled, not realtime</span></div><span class="route-source-badge">schedule</span></div><div class="route-steps">${legs.map(routeStepHtml).join('')}</div><div class="route-attribution">Schedule: ZTM Warszawa · GTFS: Mikołaj Kuranowski · route shapes: © OpenStreetMap contributors</div>`;
  }
  routePanel.classList.remove('hidden');
  const allowedTravel = Number(activeResult?.brief?.max_one_way_minutes || 0) + Number(activeResult?.brief?.negotiable_extra_travel_minutes || 0);
  if (Number(route.duration_minutes) > allowedTravel) {
    routePanel.classList.add('route-conflict');
    routePanel.insertAdjacentHTML('afterbegin', `<div class="route-warning"><strong>Route check changed the answer.</strong><span>The detailed route is ${escapeHtml(route.duration_minutes)} min, above the currently allowed ${escapeHtml(allowedTravel)} min. Treat this option as provisional and adjust travel tolerance or choose another card.</span></div>`);
  } else {
    routePanel.classList.remove('route-conflict');
  }
  if (points.length && map) {
    const midpoint = points[Math.floor(points.length / 2)];
    routeBadgeMarker = L.marker(midpoint, {
      interactive: false,
      icon: L.divIcon({
        className: 'route-time-marker',
        html: `<div>${escapeHtml(route.duration_minutes)} min${route.mode === 'transit' && route.summary ? ` · ${escapeHtml(route.summary)}` : ''}</div>`,
        iconSize: [150, 34],
        iconAnchor: [75, 17],
      }),
    }).addTo(map);
  }
  const metric = document.querySelector(`[data-card-index="${selectedIndex}"] .route-time-metric .metric-copy`);
  if (metric) metric.innerHTML = `<strong>${escapeHtml(route.duration_minutes)} min</strong><span>${route.mode === 'transit' ? 'scheduled route' : 'street route'}</span>`;
  $('#mapGuideLabel').textContent = route.mode === 'transit'
    ? 'Scheduled WTP route · walking legs use OSM streets'
    : 'Shortest pedestrian route · OpenStreetMap streets';
}

async function loadSelectedRoute() {
  const card = activeResult?.cards?.[selectedIndex];
  if (!card || !validCardLocation(card)) {
    routePanel.classList.add('hidden');
    clearActualRoute();
    return;
  }
  const serial = ++routeRequestSerial;
  routePanel.classList.remove('hidden');
  routePanel.innerHTML = `<div class="route-loading"><span class="mini-spinner"></span><span>Building ${activeResult.brief.travel_mode === 'walk' ? 'street' : 'scheduled public-transport'} route…</span></div>`;
  const origin = briefOriginCoords(activeResult.brief);
  try {
    const route = await fetchJson('/api/route', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        origin_lat: origin[0],
        origin_lon: origin[1],
        destination_lat: Number(card.location.lat),
        destination_lon: Number(card.location.lon),
        mode: activeResult.brief.travel_mode,
        date: activeResult.brief.date,
        start_time: activeResult.brief.start_time,
      }),
    });
    if (serial !== routeRequestSerial) return;
    renderActualRoute(route);
  } catch (error) {
    if (serial !== routeRequestSerial) return;
    clearActualRoute();
    refreshGuideLine();
    routePanel.innerHTML = `<div class="route-panel-head route-unavailable"><div><strong>Detailed route unavailable</strong><span>${escapeHtml(error.message)} · the card still shows the conservative search estimate.</span></div></div>`;
  }
}

function renderFooter(result) {
  const mode = result.provider_mode;
  $('#footerSources').innerHTML = mode === 'live'
    ? '<strong>Sources:</strong> public listings · live Qloo taste signal'
    : mode === 'fixture'
      ? '<strong>Sources:</strong> public listings · taste preview only (Qloo API not connected)'
      : '<strong>Sources:</strong> public listings · no-taste baseline';
  $('#footerMethod').innerHTML = mode === 'live'
    ? '<strong>Method:</strong> hard constraints first · smallest allowed changes · then live Qloo taste ranking'
    : '<strong>Method:</strong> hard constraints first · smallest allowed changes · live Qloo taste ranking activates after API connection';
  const needs = result.cards.reduce((sum, card) => sum + (card.needs_checking?.length || 0), 0);
  $('#footerNeeds').textContent = needs ? `Needs checking: ${needs} flagged fact${needs === 1 ? '' : 's'}` : 'Needs checking: none flagged by current data';
}

function renderResult(result) {
  searchingState.classList.add('hidden');
  firstRun.classList.add('hidden');
  resultContent.classList.remove('hidden');
  activeResult = result;
  draftBrief = structuredClone(result.brief);
  selectedIndex = 0;
  updateSummary(result.brief);
  const confirmedCount = result.cards.filter(card => card.feasibility_status === 'confirmed').length;
  const checkCount = result.cards.length - confirmedCount;
  const rejectedCount = Number(result.rejected_ids?.length || 0);
  const depthCopy = rejectedCount > 0 ? ` · deeper alternatives after ${rejectedCount} rejection${rejectedCount === 1 ? '' : 's'} · taste fit may be looser` : '';
  resultMeta.innerHTML = `<span>Round ${result.round} · ${escapeHtml(result.strategy_used)} search · ${escapeHtml(result.scope?.candidate_count || 0)} candidates left${depthCopy}</span><span>${confirmedCount ? `${confirmedCount} confirmed` : ''}${confirmedCount && checkCount ? ' · ' : ''}${checkCount ? `${checkCount} needs checking` : ''}</span>`;

  if (result.empty || !result.cards.length) {
    cardsEl.innerHTML = '';
    emptyState.classList.remove('hidden');
    resultActions.classList.add('hidden');
    routePanel.classList.add('hidden');
    clearActualRoute();
    const reasons = (result.empty_explanation || []).map(item => `<li>${escapeHtml(item.reason)}${item.count ? ` (${item.count})` : ''}</li>`).join('');
    emptyState.innerHTML = `<h3>No feasible rescue in the checked pool.</h3><p>Unstuck kept your locked conditions instead of silently breaking them.</p>${reasons ? `<ul>${reasons}</ul>` : ''}<button class="secondary-button" type="button" id="editEmpty">Edit allowed changes</button>`;
    $('#editEmpty')?.addEventListener('click', () => openEditor('travel'));
  } else {
    emptyState.classList.add('hidden');
    cardsEl.innerHTML = result.cards.slice(0, 3).map((card, index) => cardHtml(card, index, result.brief)).join('');
    bindResultCardEvents();
    updateResultActions();
    hydrateGooglePlaceMedia(result.cards.slice(0, 3));
  }
  renderFooter(result);
  renderMap(result, true);
  if (!result.empty && result.cards.length) loadSelectedRoute();
}

function nearestIndex(values, wanted) {
  const numeric = Number(wanted);
  return values.reduce((best, candidate, index) => Math.abs(candidate - numeric) < Math.abs(values[best] - numeric) ? index : best, 0);
}

function wheelMarkup(values, padded = false, unit = '') {
  return `<div class="wheel-fade top"></div><div class="wheel-selection"></div><div class="wheel-picker" role="listbox" tabindex="0"><div class="wheel-spacer" aria-hidden="true"></div>${values.map(value => `<button type="button" class="wheel-option" role="option" data-value="${value}">${padded ? String(value).padStart(2, '0') : value}${unit ? ` <span>${unit}</span>` : ''}</button>`).join('')}<div class="wheel-spacer" aria-hidden="true"></div></div><div class="wheel-fade bottom"></div>`;
}

function bindWheel(picker, values, onSelect, initialValue) {
  let ready = false;
  let suppressScroll = false;
  let suppressTimer = null;
  let paintFrame = null;
  let settleTimer = null;
  const options = () => [...picker.querySelectorAll('.wheel-option')];
  function paintIndex(index) {
    const bounded = Math.max(0, Math.min(values.length - 1, index));
    options().forEach((option, optionIndex) => {
      const selected = optionIndex === bounded;
      option.classList.toggle('selected', selected);
      option.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
    onSelect(values[bounded]);
    return bounded;
  }
  function selectIndex(index, smooth = false) {
    const bounded = paintIndex(index);
    suppressScroll = true;
    if (suppressTimer) clearTimeout(suppressTimer);
    picker.scrollTo({top: bounded * WHEEL_ROW_HEIGHT, behavior: smooth && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto'});
    suppressTimer = setTimeout(() => {
      suppressScroll = false;
    }, smooth ? 320 : 80);
  }
  picker.addEventListener('scroll', () => {
    if (!ready || suppressScroll) return;
    if (paintFrame) cancelAnimationFrame(paintFrame);
    paintFrame = requestAnimationFrame(() => {
      paintIndex(Math.round(picker.scrollTop / WHEEL_ROW_HEIGHT));
    });
    if (settleTimer) clearTimeout(settleTimer);
    settleTimer = setTimeout(() => {
      if (suppressScroll) return;
      const target = Math.max(0, Math.min(values.length - 1, Math.round(picker.scrollTop / WHEEL_ROW_HEIGHT)));
      selectIndex(target, true);
    }, 105);
  });
  options().forEach((option, index) => option.addEventListener('click', () => selectIndex(index, true)));
  picker.addEventListener('keydown', event => {
    if (!['ArrowUp','ArrowDown','PageUp','PageDown','Home','End'].includes(event.key)) return;
    event.preventDefault();
    let index = Math.round(picker.scrollTop / WHEEL_ROW_HEIGHT);
    if (event.key === 'ArrowUp') index -= 1;
    if (event.key === 'ArrowDown') index += 1;
    if (event.key === 'PageUp') index -= 2;
    if (event.key === 'PageDown') index += 2;
    if (event.key === 'Home') index = 0;
    if (event.key === 'End') index = values.length - 1;
    selectIndex(index, true);
  });
  const initialIndex = nearestIndex(values, initialValue);
  selectIndex(initialIndex, false);
  requestAnimationFrame(() => { ready = true; });
  return value => selectIndex(nearestIndex(values, value), false);
}

function ensureEditorWheels() {
  if (editorWheelsReady) return;
  $$('.duration-wheel').forEach(shell => {
    const inputName = shell.dataset.wheelInput;
    const input = editorForm.elements[inputName];
    const values = String(shell.dataset.wheelValues).split(',').map(Number);
    shell.innerHTML = wheelMarkup(values, false, 'min');
    const picker = shell.querySelector('.wheel-picker');
    picker.setAttribute('aria-label', shell.getAttribute('aria-label') || inputName);
    durationWheelSetters.set(inputName, bindWheel(picker, values, value => { input.value = String(value); }, Number(input.value || values[0])));
  });
  $$('.time-wheel').forEach(shell => {
    const inputName = shell.dataset.timeInput;
    const input = editorForm.elements[inputName];
    const minuteStep = Number(shell.dataset.minuteStep || 5);
    const hours = Array.from({length: 24}, (_, index) => index);
    const minutes = Array.from({length: Math.ceil(60 / minuteStep)}, (_, index) => index * minuteStep).filter(value => value < 60);
    shell.innerHTML = `<div class="time-column wheel-shell">${wheelMarkup(hours, true)}</div><div class="time-separator">:</div><div class="time-column wheel-shell">${wheelMarkup(minutes, true)}</div>`;
    const [hourPicker, minutePicker] = shell.querySelectorAll('.wheel-picker');
    hourPicker.setAttribute('aria-label', `${shell.getAttribute('aria-label')} hour`);
    minutePicker.setAttribute('aria-label', `${shell.getAttribute('aria-label')} minute`);
    let hour = 0;
    let minute = 0;
    const write = () => { input.value = `${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}`; };
    const setHour = bindWheel(hourPicker, hours, value => { hour = value; write(); }, 0);
    const setMinute = bindWheel(minutePicker, minutes, value => { minute = value; write(); }, 0);
    timeWheelSetters.set(inputName, value => {
      const [nextHour, nextMinute] = String(value || '00:00').split(':').map(Number);
      hour = nextHour;
      minute = minutes[nearestIndex(minutes, nextMinute)];
      setHour(hour);
      setMinute(minute);
      write();
    });
  });
  editorWheelsReady = true;
}

function foldOriginText(value) {
  return String(value || '')
    .toLocaleLowerCase('pl-PL')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/ł/g, 'l')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function savedOriginMatch(value) {
  const needle = foldOriginText(value);
  return origins.find(row => foldOriginText(row.label) === needle || foldOriginText(row.id) === needle) || null;
}

function applySavedOrigin(row) {
  originInput.value = row.label;
  originInput.dataset.lat = String(row.lat);
  originInput.dataset.lon = String(row.lon);
  originResolution.textContent = `${row.district} · saved point · ready without geocoding`;
}

function useBrowserCurrentLocation() {
  if (!navigator.geolocation) {
    originResolution.textContent = 'This browser does not provide geolocation. Enter an address instead.';
    return;
  }
  useCurrentLocation.disabled = true;
  useCurrentLocation.classList.add('loading');
  originResolution.textContent = 'Waiting for browser location permission…';
  navigator.geolocation.getCurrentPosition(
    async position => {
      const lat = Number(position.coords.latitude);
      const lon = Number(position.coords.longitude);
      useCurrentLocation.disabled = false;
      useCurrentLocation.classList.remove('loading');
      if (!(lat >= 52.05 && lat <= 52.40 && lon >= 20.75 && lon <= 21.35)) {
        delete originInput.dataset.lat;
        delete originInput.dataset.lon;
        originResolution.textContent = 'Current location is outside the Warsaw only beta area. Enter a Warsaw address or landmark.';
        return;
      }
      hideOriginSuggestions();
      originInput.value = 'Current location';
      originInput.dataset.lat = String(lat);
      originInput.dataset.lon = String(lon);
      const accuracy = Math.round(Number(position.coords.accuracy) || 0);
      originResolution.textContent = `GPS ready · ±${accuracy} m · finding nearest mapped address…`;
      const expectedLat = String(lat);
      const expectedLon = String(lon);
      try {
        const resolved = await fetchJson('/api/reverse-geocode', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({lat, lon}),
        });
        if (originInput.dataset.lat !== expectedLat || originInput.dataset.lon !== expectedLon) return;
        if (resolved.available && resolved.label) {
          originInput.value = resolved.label;
          originResolution.textContent = `GPS ready · ±${accuracy} m · nearest mapped address from local OpenStreetMap index · routing uses your exact GPS position`;
        } else {
          originResolution.textContent = `Current location ready · ±${accuracy} m · no nearby mapped address found · routing uses your exact GPS position`;
        }
      } catch {
        if (originInput.dataset.lat === expectedLat && originInput.dataset.lon === expectedLon) {
          originResolution.textContent = `Current location ready · ±${accuracy} m · address lookup unavailable · routing uses your exact GPS position`;
        }
      }
    },
    error => {
      useCurrentLocation.disabled = false;
      useCurrentLocation.classList.remove('loading');
      const messages = {
        1: 'Location permission was denied. You can still enter an address.',
        2: 'Current location is unavailable. You can still enter an address.',
        3: 'Location request timed out. You can still enter an address.',
      };
      originResolution.textContent = messages[error.code] || 'Could not read current location. Enter an address instead.';
    },
    {enableHighAccuracy: true, timeout: 10000, maximumAge: 60000},
  );
}

async function resolveBriefOrigin(brief) {
  if (hasFiniteCoordinates(brief.origin_lat, brief.origin_lon)) return brief;
  const saved = savedOriginMatch(brief.origin);
  if (saved) {
    brief.origin = saved.label;
    brief.origin_lat = Number(saved.lat);
    brief.origin_lon = Number(saved.lon);
    if (originInput && originInput.value === saved.label) applySavedOrigin(saved);
    return brief;
  }
  if (!String(brief.origin || '').trim()) throw new Error('Enter a Warsaw start address or choose a saved landmark.');
  if (originResolution) originResolution.textContent = 'Resolving this exact Warsaw address once…';
  const resolved = await fetchJson('/api/geocode', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({address: brief.origin}),
  });
  brief.origin = resolved.label || brief.origin;
  brief.origin_lat = Number(resolved.lat);
  brief.origin_lon = Number(resolved.lon);
  if (originInput) {
    originInput.value = brief.origin;
    originInput.dataset.lat = String(brief.origin_lat);
    originInput.dataset.lon = String(brief.origin_lon);
  }
  if (originResolution) {
    originResolution.textContent = resolved.local_index
      ? 'Exact address resolved locally from the Warsaw OpenStreetMap address index.'
      : 'Exact address resolved in the Warsaw pilot area · OpenStreetMap/Nominatim';
  }
  return brief;
}

let streetSuggestTimer = null;
let originSuggestionSerial = 0;

function hideOriginSuggestions() {
  originSuggestions.classList.add('hidden');
  originInput.setAttribute('aria-expanded', 'false');
}

function renderOriginSuggestions(savedRows, streets) {
  const items = [
    ...savedRows.map(row => ({kind: 'saved', label: row.label, meta: `${row.district} · saved point`, row})),
    ...streets.map(street => ({kind: 'street', label: street, meta: 'Warsaw street · add a house number'})),
  ].slice(0, 12);
  if (!items.length) {
    hideOriginSuggestions();
    return;
  }
  originSuggestions.innerHTML = items.map((item, index) => `<button type="button" class="origin-suggestion" role="option" data-index="${index}" data-kind="${item.kind}"><span>${escapeHtml(item.label)}</span><small>${escapeHtml(item.meta)}</small></button>`).join('');
  originSuggestions.classList.remove('hidden');
  originInput.setAttribute('aria-expanded', 'true');
  [...originSuggestions.querySelectorAll('.origin-suggestion')].forEach((button, index) => {
    const item = items[index];
    button.addEventListener('mousedown', event => event.preventDefault());
    button.addEventListener('click', () => {
      if (item.kind === 'saved') {
        applySavedOrigin(item.row);
        hideOriginSuggestions();
        originInput.focus();
      } else {
        originInput.value = `${item.label} `;
        delete originInput.dataset.lat;
        delete originInput.dataset.lon;
        originResolution.textContent = 'Street selected · add the house number, then save/search.';
        hideOriginSuggestions();
        originInput.focus();
        originInput.setSelectionRange(originInput.value.length, originInput.value.length);
      }
    });
  });
}

async function updateOriginSuggestions() {
  const query = originInput.value.trim();
  delete originInput.dataset.lat;
  delete originInput.dataset.lon;
  const serial = ++originSuggestionSerial;
  if (query.length < 2) {
    hideOriginSuggestions();
    return;
  }
  const folded = foldOriginText(query);
  const savedRows = origins
    .filter(row => foldOriginText(row.label).includes(folded))
    .sort((a, b) => foldOriginText(a.label).startsWith(folded) === foldOriginText(b.label).startsWith(folded) ? a.label.localeCompare(b.label, 'pl') : (foldOriginText(a.label).startsWith(folded) ? -1 : 1))
    .slice(0, 5);
  let streets = [];
  try {
    const payload = await fetchJson(`/api/streets?q=${encodeURIComponent(query)}`);
    streets = Array.isArray(payload.suggestions) ? payload.suggestions.slice(0, 8) : [];
  } catch {
    streets = [];
  }
  if (serial !== originSuggestionSerial) return;
  renderOriginSuggestions(savedRows, streets);
}

originInput.addEventListener('input', () => {
  delete originInput.dataset.lat;
  delete originInput.dataset.lon;
  originResolution.textContent = 'Searching the local Warsaw street index…';
  if (streetSuggestTimer) clearTimeout(streetSuggestTimer);
  streetSuggestTimer = setTimeout(updateOriginSuggestions, 90);
});
useCurrentLocation.addEventListener('click', useBrowserCurrentLocation);
originInput.addEventListener('keydown', event => {
  const buttons = [...originSuggestions.querySelectorAll('.origin-suggestion')];
  if (!buttons.length || originSuggestions.classList.contains('hidden')) return;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    buttons[0].focus();
  } else if (event.key === 'Escape') {
    hideOriginSuggestions();
  }
});
originSuggestions.addEventListener('keydown', event => {
  const buttons = [...originSuggestions.querySelectorAll('.origin-suggestion')];
  const current = buttons.indexOf(document.activeElement);
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    buttons[Math.min(buttons.length - 1, current + 1)]?.focus();
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    if (current <= 0) originInput.focus();
    else buttons[current - 1]?.focus();
  } else if (event.key === 'Escape') {
    event.preventDefault();
    hideOriginSuggestions();
    originInput.focus();
  }
});
originInput.addEventListener('blur', () => {
  setTimeout(() => {
    if (!originSuggestions.contains(document.activeElement)) hideOriginSuggestions();
    const saved = savedOriginMatch(originInput.value);
    if (saved) applySavedOrigin(saved);
  }, 80);
});

function fillEditor(brief) {
  const fields = ['goal','people','budget_total','date','origin','travel_mode'];
  fields.forEach(name => { if (editorForm.elements[name]) editorForm.elements[name].value = brief[name] ?? ''; });
  originInput.dataset.lat = brief.origin_lat ?? '';
  originInput.dataset.lon = brief.origin_lon ?? '';
  if (brief.origin_lat != null && brief.origin_lon != null) {
    originResolution.textContent = 'Exact start location resolved and will be used for travel/routing.';
  } else {
    originResolution.textContent = 'Saved landmarks work instantly; street autocomplete is local and exact addresses are geocoded only after you submit.';
  }
  editorForm.elements.taste_refs.value = (brief.taste_refs || []).join(', ');
  editorForm.elements.allow_category_change.checked = Boolean(brief.allow_category_change);
  $$('#editorForm input[name="category"]').forEach(input => { input.checked = (brief.categories || []).includes(input.value); });
  timeWheelSetters.get('start_time')?.(brief.start_time);
  timeWheelSetters.get('return_by')?.(brief.return_by);
  durationWheelSetters.get('min_stay_minutes')?.(brief.min_stay_minutes);
  durationWheelSetters.get('max_one_way_minutes')?.(brief.max_one_way_minutes);
  durationWheelSetters.get('negotiable_extra_travel_minutes')?.(brief.negotiable_extra_travel_minutes || 0);
  durationWheelSetters.get('negotiable_stay_reduction_minutes')?.(brief.negotiable_stay_reduction_minutes || 0);
}

function editorPayload() {
  const fd = new FormData(editorForm);
  const goal = String(fd.get('goal'));
  return {
    original_plan: goal === 'meal' ? 'Dinner' : goal === 'coffee' ? 'Coffee and talk' : goal === 'culture' ? 'Culture outing' : 'Outing',
    failed_place: '',
    failure_reason: '',
    goal,
    city: 'Warsaw',
    date: String(fd.get('date')),
    start_time: String(fd.get('start_time')),
    return_by: String(fd.get('return_by')),
    min_stay_minutes: Number(fd.get('min_stay_minutes')),
    people: Number(fd.get('people')),
    budget_total: Number(fd.get('budget_total')),
    currency: 'PLN',
    origin: String(fd.get('origin')),
    origin_lat: originInput.dataset.lat ? Number(originInput.dataset.lat) : null,
    origin_lon: originInput.dataset.lon ? Number(originInput.dataset.lon) : null,
    travel_mode: String(fd.get('travel_mode')),
    max_one_way_minutes: Number(fd.get('max_one_way_minutes')),
    categories: $$('#editorForm input[name="category"]:checked').map(input => input.value),
    taste_refs: String(fd.get('taste_refs') || '').split(',').map(item => item.trim()).filter(Boolean),
    meal_required: goal === 'meal',
    negotiable_extra_travel_minutes: Number(fd.get('negotiable_extra_travel_minutes')),
    negotiable_stay_reduction_minutes: Number(fd.get('negotiable_stay_reduction_minutes')),
    allow_category_change: editorForm.elements.allow_category_change.checked,
  };
}

function validateEditor(brief) {
  if (!brief.date) return 'Choose a date.';
  if (!brief.origin) return 'Choose a start location.';
  if (!brief.categories.length && brief.goal !== 'flexible') return 'Choose at least one preferred category.';
  if (!(brief.people >= 1 && brief.people <= 12)) return 'People must be between 1 and 12.';
  if (!(brief.budget_total > 0)) return 'Budget must be greater than zero.';
  return '';
}

function openEditor(target = 'plan') {
  editorReturnFocus = document.activeElement;
  editorBackdrop.classList.remove('hidden');
  editorModal.classList.remove('hidden');
  editorBackdrop.setAttribute('aria-hidden', 'false');
  ensureEditorWheels();
  fillEditor(activeResult?.brief || draftBrief);
  editorError.classList.add('hidden');
  $$('.editor-section').forEach(section => section.classList.remove('flash'));
  const sectionTarget = target === 'return' || target === 'stay' ? 'budget' : target;
  const section = editorModal.querySelector(`[data-section="${sectionTarget}"]`) || editorModal.querySelector('[data-section="plan"]');
  section.classList.add('flash');
  setTimeout(() => section.classList.remove('flash'), 900);
  section.scrollIntoView({block: 'start'});
  setTimeout(() => {
    const focusable = section.querySelector('input:not([type="hidden"]), select, .wheel-picker');
    focusable?.focus({preventScroll: true});
  }, 0);
}

function closeEditor() {
  editorModal.classList.add('hidden');
  editorBackdrop.classList.add('hidden');
  editorBackdrop.setAttribute('aria-hidden', 'true');
  editorReturnFocus?.focus?.();
}

editorForm.addEventListener('submit', async event => {
  event.preventDefault();
  const nextBrief = editorPayload();
  const error = validateEditor(nextBrief);
  if (error) {
    editorError.textContent = error;
    editorError.classList.remove('hidden');
    return;
  }
  editorError.classList.add('hidden');
  try {
    await resolveBriefOrigin(nextBrief);
  } catch (error) {
    editorError.textContent = error.message;
    editorError.classList.remove('hidden');
    originInput.focus();
    return;
  }
  closeEditor();
  if (sessionId) {
    await runLatest('/api/update', {session_id: sessionId, patch: nextBrief});
  } else {
    draftBrief = nextBrief;
    updateSummary(draftBrief);
  }
});

$('#cancelEditor').addEventListener('click', closeEditor);
$('#closeEditor').addEventListener('click', closeEditor);
editorBackdrop.addEventListener('click', closeEditor);
$('#openFullEditor').addEventListener('click', () => openEditor('plan'));
$('#runCurrentPlan').addEventListener('click', async () => {
  const nextBrief = structuredClone(draftBrief);
  try {
    await resolveBriefOrigin(nextBrief);
  } catch (error) {
    openEditor('budget');
    editorError.textContent = error.message;
    editorError.classList.remove('hidden');
    originInput.focus();
    return;
  }
  draftBrief = nextBrief;
  updateSummary(draftBrief);
  await runLatest('/api/search', draftBrief);
});
$$('.summary-edit').forEach(button => button.addEventListener('click', () => openEditor(button.dataset.editTarget || 'plan')));
themeToggle.addEventListener('click', toggleTheme);

function openChoice() {
  const card = activeResult?.cards?.[selectedIndex];
  if (!card) return;
  const actualRoute = card._actualRoute;
  choiceReturnFocus = document.activeElement;
  $('#choiceTitle').textContent = card.name;
  $('#choiceWhy').textContent = card.why_this_fits;
  $('#choiceSummary').innerHTML = `
    <div><strong>${escapeHtml(formatMoney(card))}</strong><span>estimated total</span></div>
    <div><strong>${actualRoute?.duration_minutes ?? card.timing.travel_one_way_minutes} min</strong><span>${actualRoute ? 'routed outbound' : 'one-way estimate'}</span></div>
    <div><strong>${actualRoute?.arrival ?? card.timing.arrival}</strong><span>arrive at venue</span></div>`;
  choiceBackdrop.classList.remove('hidden');
  choiceModal.classList.remove('hidden');
  choiceBackdrop.setAttribute('aria-hidden', 'false');
  $('#choiceDone').focus();
}

function closeChoice() {
  choiceModal.classList.add('hidden');
  choiceBackdrop.classList.add('hidden');
  choiceBackdrop.setAttribute('aria-hidden', 'true');
  choiceReturnFocus?.focus?.();
}

chooseButton.addEventListener('click', openChoice);
$('#closeChoice').addEventListener('click', closeChoice);
$('#choiceDone').addEventListener('click', closeChoice);
choiceBackdrop.addEventListener('click', closeChoice);

lockCompromiseButton.addEventListener('click', async () => {
  if (!sessionId || lockCompromiseButton.disabled) return;
  const change = selectedCompromise();
  if (!change) return;
  const patch = change.field === 'one-way travel'
    ? {negotiable_extra_travel_minutes: 0}
    : change.field === 'minimum stay'
      ? {negotiable_stay_reduction_minutes: 0}
      : change.field === 'category'
        ? {allow_category_change: false}
        : null;
  if (patch) await runLatest('/api/update', {session_id: sessionId, patch});
});

function positionMenu() {
  const rect = menuButton.getBoundingClientRect();
  menuPopover.style.top = `${rect.bottom + 6}px`;
  menuPopover.style.left = `${Math.max(8, rect.right - 210)}px`;
}

menuButton.addEventListener('click', event => {
  event.stopPropagation();
  const opening = menuPopover.classList.contains('hidden');
  menuPopover.classList.toggle('hidden', !opening);
  menuButton.setAttribute('aria-expanded', opening ? 'true' : 'false');
  if (opening) positionMenu();
});
document.addEventListener('click', event => {
  if (!menuPopover.contains(event.target) && event.target !== menuButton) {
    menuPopover.classList.add('hidden');
    menuButton.setAttribute('aria-expanded', 'false');
  }
});
$$('[data-menu-action]').forEach(button => button.addEventListener('click', () => {
  const action = button.dataset.menuAction;
  menuPopover.classList.add('hidden');
  menuButton.setAttribute('aria-expanded', 'false');
  if (action === 'edit') openEditor('plan');
  if (action === 'demo') loadJudgeDemo();
  if (action === 'theme') toggleTheme();
  if (action === 'reset') resetSession();
}));

async function loadJudgeDemo() {
  const demoTime = judgeDemoEvening();
  draftBrief = {
    ...makeDefaultBrief(),
    date: demoTime.date,
    start_time: demoTime.start_time,
    return_by: demoTime.return_by,
    max_one_way_minutes: 25,
    negotiable_extra_travel_minutes: 10,
    negotiable_stay_reduction_minutes: 15,
  };
  await resolveBriefOrigin(draftBrief);
  updateSummary(draftBrief);
  await runLatest('/api/search', draftBrief);
}

$('#loadJudgeDemo').addEventListener('click', loadJudgeDemo);

function resetSession() {
  requestSerial += 1;
  sessionId = null;
  activeResult = null;
  selectedIndex = 0;
  draftBrief = makeDefaultBrief();
  updateSummary(draftBrief);
  searchingState.classList.add('hidden');
  resultContent.classList.add('hidden');
  firstRun.classList.remove('hidden');
  resultLayer?.clearLayers();
  guideLayer?.clearLayers();
  clearActualRoute();
  routePanel.classList.add('hidden');
  map?.setView([52.2297, 21.0122], 12, {animate: false});
  renderFooter({provider_mode: statusInfo?.provider_mode || 'fixture', cards: []});
}

$('#showList').addEventListener('click', () => {
  workspace.classList.remove('mobile-map');
  $('#showList').classList.add('active');
  $('#showMap').classList.remove('active');
});
$('#showMap').addEventListener('click', () => {
  workspace.classList.add('mobile-map');
  $('#showMap').classList.add('active');
  $('#showList').classList.remove('active');
  setTimeout(() => map?.invalidateSize(false), 0);
});

document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!choiceModal.classList.contains('hidden')) closeChoice();
  else if (!editorModal.classList.contains('hidden')) closeEditor();
  else if (!menuPopover.classList.contains('hidden')) {
    menuPopover.classList.add('hidden');
    menuButton.setAttribute('aria-expanded', 'false');
    menuButton.focus();
  }
});

async function loadStatus() {
  try {
    statusInfo = await fetchJson('/api/health');
    refreshStatusLabel();
    dataStatus.title = statusInfo.provider_mode === 'fixture'
      ? 'Real place facts with deterministic fixture taste. Qloo has not been called.'
      : statusInfo.provider_mode === 'live' ? 'Live Qloo taste ranking is active.' : 'Taste ranking disabled for comparison.';
  } catch {
    dataStatus.textContent = 'Backend unavailable';
  }
}

function refreshStatusLabel() {
  if (!statusInfo) return;
  dataStatus.classList.toggle('live', statusInfo.provider_mode === 'live');
  dataStatus.classList.toggle('baseline', statusInfo.provider_mode === 'baseline');
  const compact = window.matchMedia('(max-width: 760px)').matches;
  if (statusInfo.provider_mode === 'live') dataStatus.textContent = compact ? 'Qloo live' : 'Live · Qloo';
  else if (statusInfo.provider_mode === 'baseline') dataStatus.textContent = compact ? 'Baseline' : 'Baseline · no taste';
  else dataStatus.textContent = compact ? 'Demo' : 'Demo · fixture taste';
}

async function loadOrigins() {
  try {
    const payload = await fetchJson('/api/origins');
    origins = Array.isArray(payload.origins) ? payload.origins : [];
    const streetCount = Number(statusInfo?.street_count || 0);
    const addressCount = Number(statusInfo?.address_count || 0);
    const streetLabel = streetCount ? streetCount.toLocaleString('en-US') : '6k+';
    const addressLabel = addressCount ? addressCount.toLocaleString('en-US') : '125k+';
    $('#originCount').textContent = `${origins.length} saved points + ${streetLabel} streets + ${addressLabel} exact addresses`;
    const defaultOrigin = savedOriginMatch(draftBrief.origin);
    if (defaultOrigin) {
      draftBrief.origin_lat = Number(defaultOrigin.lat);
      draftBrief.origin_lon = Number(defaultOrigin.lon);
    }
  } catch {
    $('#originCount').textContent = 'start-point catalog unavailable';
  }
}

applyTheme(preferredTheme());
hydrateIcons();
updateSummary(draftBrief);
initMap();
renderFooter({provider_mode: 'fixture', cards: []});
window.addEventListener('resize', refreshStatusLabel);
Promise.all([loadStatus(), loadOrigins()]).then(() => {
  if (new URLSearchParams(window.location.search).get('demo') === '1') loadJudgeDemo();
});
