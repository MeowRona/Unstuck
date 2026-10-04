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

function makeDefaultBrief() {
  const local = localPlanningDefaults();
  return {
  original_plan: 'Dinner somewhere calm where we can actually talk',
  failed_place: 'Closed Place',
  failure_reason: 'It is closed tonight',
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
const quickStartForm = $('#quickStartForm');
const searchingState = $('#searchingState');
const resultContent = $('#resultContent');
const cardsEl = $('#cards');
const emptyState = $('#emptyState');
const resultActions = $('#resultActions');
const chooseButton = $('#chooseButton');
const lockCompromiseButton = $('#lockCompromiseButton');
const resultMeta = $('#resultMeta');
const dataStatus = $('#dataStatus');
const editorModal = $('#editorModal');
const editorBackdrop = $('#editorBackdrop');
const editorForm = $('#editorForm');
const editorError = $('#editorError');
const menuButton = $('#menuButton');
const menuPopover = $('#menuPopover');
const choiceModal = $('#choiceModal');
const choiceBackdrop = $('#choiceBackdrop');

let draftBrief = structuredClone(DEFAULT_BRIEF);
let sessionId = null;
let activeResult = null;
let selectedIndex = 0;
let requestSerial = 0;
let statusInfo = null;
let origins = [];
let editorWheelsReady = false;
let editorReturnFocus = null;
let choiceReturnFocus = null;

let map = null;
let tileLayer = null;
let resultLayer = null;
let guideLayer = null;
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
};

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

function failureSummary(brief) {
  const reason = String(brief.failure_reason || '').trim();
  if (reason) return reason.endsWith('.') ? reason : `${reason}.`;
  if (brief.failed_place) return `${brief.failed_place} no longer works.`;
  return 'The original plan no longer works.';
}

function tasteSummary(brief) {
  const refs = brief.taste_refs || [];
  if (!refs.length) return 'Not set';
  if (refs.length === 1) return refs[0];
  return `${refs[0]} + ${refs[1]}${refs.length > 2 ? ` +${refs.length - 2}` : ''}`;
}

function updateSummary(brief) {
  $('#summaryPlanTitle').textContent = planTitle(brief);
  $('#summaryFailure').textContent = failureSummary(brief);
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
  const from = originCoords(activeResult.brief.origin);
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
  const origin = originCoords(result.brief.origin);
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
  if (!changes.length) return '<span class="change-badge none">No compromise</span>';
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

function tasteTags(card) {
  const evidence = Array.isArray(card.taste?.evidence) ? card.taste.evidence.slice(0, 3) : [];
  const source = card.taste?.source;
  const tags = [];
  if (source === 'fixture') tags.push('<span class="taste-tag">Fixture taste · Qloo not called</span>');
  else if (source === 'qloo') tags.push('<span class="taste-tag">Qloo taste signal</span>');
  else tags.push('<span class="taste-tag">Feasibility only</span>');
  evidence.forEach(item => tags.push(`<span class="taste-tag">${escapeHtml(item)}</span>`));
  if (card.needs_checking?.length) tags.push(`<span class="taste-tag needs-chip">${card.needs_checking.length} item${card.needs_checking.length === 1 ? '' : 's'} to check</span>`);
  return tags.join('');
}

function cardHtml(card, index, brief) {
  const letter = String.fromCharCode(65 + index);
  const travelDelta = Math.max(0, Number(card.timing.travel_one_way_minutes) - Number(brief.max_one_way_minutes));
  const stayDelta = Math.max(0, Number(brief.min_stay_minutes) - Number(card.timing.stay_minutes));
  const subline = `${titleCase(card.category)} · ${card.feasibility_status === 'confirmed' ? 'current facts checked' : 'needs fact check'} · ${card.address || 'Warsaw'}`;
  const needs = (card.needs_checking || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  const mapsUrl = googleMapsUrl(card);
  const googlePlaceAttrs = card.google_place_id ? ` data-google-place-id="${escapeHtml(card.google_place_id)}"` : '';
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
      <div class="metrics-row">
        <div class="metric">${iconSvg('coins')}<div class="metric-copy"><strong>${escapeHtml(formatMoney(card))}</strong><span>est. total · ${card.cost.for_people} people</span></div></div>
        <div class="metric">${iconSvg('car')}<div class="metric-copy"><strong>${card.timing.travel_one_way_minutes} min${travelDelta ? `<span class="metric-delta">+${travelDelta}</span>` : ''}</strong><span>one-way · estimated</span></div></div>
        <div class="metric">${iconSvg('hourglass')}<div class="metric-copy"><strong>${card.timing.stay_minutes} min${stayDelta ? `<span class="metric-delta">−${stayDelta}</span>` : ''}</strong><span>stay</span></div></div>
      </div>
      <div class="taste-row"><strong>Taste profile</strong>${tasteTags(card)}</div>
      <div class="card-footer-line">
        <button type="button" class="sources-toggle" data-card-index="${index}">Sources & assumptions</button>
        ${card.google_place_id ? `<span>·</span><a href="${escapeHtml(mapsUrl)}" target="_blank" rel="noreferrer">Google Maps</a>` : ''}
        <span>·</span>
        <button type="button" class="reject-inline" data-place-id="${escapeHtml(card.id)}">Reject place</button>
      </div>
      <div class="card-source-panel hidden" data-source-panel="${index}">
        ${sourceLink('Price', card.cost?.source)}
        ${sourceLink('Hours', card.hours_source)}
        ${card.location_source?.url ? `<div><strong>Location</strong> · <a href="${escapeHtml(card.location_source.url)}" target="_blank" rel="noreferrer">source</a>${card.location_source.checked_at ? ` · checked ${escapeHtml(card.location_source.checked_at)}` : ''}</div>` : '<div><strong>Location</strong> · catalog coordinates</div>'}
        ${card.google_place_id ? `<div><strong>Google Maps</strong> · rating/photo load live through Places API only when configured; no Google content is persisted. · <a href="${escapeHtml(mapsUrl)}" target="_blank" rel="noreferrer">open listing</a></div>` : ''}
        <div><strong>Travel</strong> · straight-line-derived estimate; the map guide is not a routed journey.</div>
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
  $$('.reject-inline').forEach(button => button.addEventListener('click', async event => {
    event.stopPropagation();
    if (!sessionId) return;
    await runLatest('/api/reject', {session_id: sessionId, place_id: button.dataset.placeId});
  }));
}

function selectCard(index, {fromMap = false} = {}) {
  if (!activeResult?.cards?.[index]) return;
  selectedIndex = index;
  $$('.recommendation-card').forEach((card, cardIndex) => card.classList.toggle('selected', cardIndex === index));
  updateMarkerSelection();
  updateResultActions();
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
  chooseButton.innerHTML = `Choose ${escapeHtml(card.name)} ${iconSvg('arrow')}`;
  const change = selectedCompromise();
  if (!change) {
    lockCompromiseButton.disabled = true;
    lockCompromiseButton.textContent = 'No compromise to lock';
  } else if (change.field === 'one-way travel') {
    lockCompromiseButton.disabled = false;
    lockCompromiseButton.innerHTML = `${iconSvg('car')} Keep travel at ${activeResult.brief.max_one_way_minutes} min`;
  } else if (change.field === 'minimum stay') {
    lockCompromiseButton.disabled = false;
    lockCompromiseButton.innerHTML = `${iconSvg('hourglass')} Keep stay at ${activeResult.brief.min_stay_minutes} min`;
  } else if (change.field === 'category') {
    lockCompromiseButton.disabled = false;
    lockCompromiseButton.innerHTML = `${iconSvg('tag')} Keep original category`;
  } else {
    lockCompromiseButton.disabled = true;
    lockCompromiseButton.textContent = 'No compromise to lock';
  }
}

function renderFooter(result) {
  const mode = result.provider_mode;
  $('#footerSources').innerHTML = mode === 'live'
    ? '<strong>Sources:</strong> public listings · Qloo taste signal'
    : mode === 'fixture'
      ? '<strong>Sources:</strong> public listings · fixture taste (Qloo not called)'
      : '<strong>Sources:</strong> public listings · no-taste baseline';
  $('#footerMethod').innerHTML = '<strong>Method:</strong> hard constraints first · smallest allowed changes · then taste ranking';
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
  resultMeta.innerHTML = `<span>Round ${result.round} · ${escapeHtml(result.strategy_used)} search</span><span>${result.result_status === 'confirmed' ? 'Current facts support these options' : result.result_status === 'requires_checking' ? 'Some facts still need checking' : 'No feasible result'}</span>`;

  if (result.empty || !result.cards.length) {
    cardsEl.innerHTML = '';
    emptyState.classList.remove('hidden');
    resultActions.classList.add('hidden');
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
}

function quickFormIntoDraft() {
  const fd = new FormData(quickStartForm);
  draftBrief.original_plan = String(fd.get('original_plan') || '').trim();
  draftBrief.failed_place = String(fd.get('failed_place') || '').trim();
  draftBrief.failure_reason = String(fd.get('failure_reason') || '').trim();
  draftBrief.meal_required = draftBrief.goal === 'meal';
  updateSummary(draftBrief);
}

quickStartForm.addEventListener('submit', async event => {
  event.preventDefault();
  quickFormIntoDraft();
  await runLatest('/api/search', draftBrief);
});

function nearestIndex(values, wanted) {
  const numeric = Number(wanted);
  return values.reduce((best, candidate, index) => Math.abs(candidate - numeric) < Math.abs(values[best] - numeric) ? index : best, 0);
}

function wheelMarkup(values, padded = false, unit = '') {
  return `<div class="wheel-fade top"></div><div class="wheel-selection"></div><div class="wheel-picker" role="listbox" tabindex="0"><div class="wheel-spacer" aria-hidden="true"></div>${values.map(value => `<button type="button" class="wheel-option" role="option" data-value="${value}">${padded ? String(value).padStart(2, '0') : value}${unit ? ` <span>${unit}</span>` : ''}</button>`).join('')}<div class="wheel-spacer" aria-hidden="true"></div></div><div class="wheel-fade bottom"></div>`;
}

function bindWheel(picker, values, onSelect, initialValue) {
  let ready = false;
  let settleTimer = null;
  let suppressScroll = false;
  let suppressTimer = null;
  const options = () => [...picker.querySelectorAll('.wheel-option')];
  function selectIndex(index, smooth = false) {
    const bounded = Math.max(0, Math.min(values.length - 1, index));
    if (settleTimer) {
      clearTimeout(settleTimer);
      settleTimer = null;
    }
    options().forEach((option, optionIndex) => {
      const selected = optionIndex === bounded;
      option.classList.toggle('selected', selected);
      option.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
    onSelect(values[bounded]);
    suppressScroll = true;
    if (suppressTimer) clearTimeout(suppressTimer);
    picker.scrollTo({top: bounded * WHEEL_ROW_HEIGHT, behavior: smooth && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto'});
    suppressTimer = setTimeout(() => {
      suppressScroll = false;
    }, 140);
  }
  picker.addEventListener('scroll', () => {
    if (!ready || suppressScroll) return;
    if (settleTimer) clearTimeout(settleTimer);
    settleTimer = setTimeout(() => {
      selectIndex(Math.round(picker.scrollTop / WHEEL_ROW_HEIGHT), false);
    }, 90);
  });
  options().forEach((option, index) => option.addEventListener('click', () => selectIndex(index, false)));
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
    selectIndex(index, false);
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

function fillEditor(brief) {
  const fields = ['original_plan','failed_place','failure_reason','goal','people','budget_total','date','origin','travel_mode'];
  fields.forEach(name => { if (editorForm.elements[name]) editorForm.elements[name].value = brief[name] ?? ''; });
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
    original_plan: String(fd.get('original_plan') || '').trim(),
    failed_place: String(fd.get('failed_place') || '').trim(),
    failure_reason: String(fd.get('failure_reason') || '').trim(),
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
  if (!brief.original_plan) return 'Describe the original plan.';
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
  closeEditor();
  if (sessionId) {
    await runLatest('/api/update', {session_id: sessionId, patch: nextBrief});
  } else {
    draftBrief = nextBrief;
    updateSummary(draftBrief);
    quickStartForm.elements.original_plan.value = draftBrief.original_plan;
    quickStartForm.elements.failed_place.value = draftBrief.failed_place;
    quickStartForm.elements.failure_reason.value = draftBrief.failure_reason;
  }
});

$('#cancelEditor').addEventListener('click', closeEditor);
$('#closeEditor').addEventListener('click', closeEditor);
editorBackdrop.addEventListener('click', closeEditor);
$('#openFullEditor').addEventListener('click', () => openEditor('plan'));
$$('.summary-edit').forEach(button => button.addEventListener('click', () => openEditor(button.dataset.editTarget || 'plan')));

function openChoice() {
  const card = activeResult?.cards?.[selectedIndex];
  if (!card) return;
  choiceReturnFocus = document.activeElement;
  $('#choiceTitle').textContent = card.name;
  $('#choiceWhy').textContent = card.why_this_fits;
  $('#choiceSummary').innerHTML = `
    <div><strong>${escapeHtml(formatMoney(card))}</strong><span>estimated total</span></div>
    <div><strong>${card.timing.travel_one_way_minutes} min</strong><span>one-way estimate</span></div>
    <div><strong>${card.timing.estimated_return}</strong><span>estimated return</span></div>`;
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
  if (action === 'reset') resetSession();
}));

async function loadJudgeDemo() {
  draftBrief = {
    ...makeDefaultBrief(),
    date: '2026-10-10',
    start_time: '18:30',
    return_by: '22:00',
    max_one_way_minutes: 25,
    negotiable_extra_travel_minutes: 10,
    negotiable_stay_reduction_minutes: 15,
  };
  quickStartForm.elements.original_plan.value = draftBrief.original_plan;
  quickStartForm.elements.failed_place.value = draftBrief.failed_place;
  quickStartForm.elements.failure_reason.value = draftBrief.failure_reason;
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
  quickStartForm.reset();
  quickStartForm.elements.original_plan.value = draftBrief.original_plan;
  quickStartForm.elements.failed_place.value = draftBrief.failed_place;
  quickStartForm.elements.failure_reason.value = draftBrief.failure_reason;
  updateSummary(draftBrief);
  searchingState.classList.add('hidden');
  resultContent.classList.add('hidden');
  firstRun.classList.remove('hidden');
  resultLayer?.clearLayers();
  guideLayer?.clearLayers();
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
    $('#originList').innerHTML = origins.map(origin => `<option value="${escapeHtml(origin.label)}">${escapeHtml(origin.district)} · ${escapeHtml(origin.label)}</option>`).join('');
    $('#originCount').textContent = `${origins.length} saved points across ${Object.keys(payload.districts || {}).length} districts`;
  } catch {
    $('#originCount').textContent = 'start-point catalog unavailable';
  }
}

hydrateIcons();
updateSummary(draftBrief);
initMap();
renderFooter({provider_mode: 'fixture', cards: []});
window.addEventListener('resize', refreshStatusLabel);
Promise.all([loadStatus(), loadOrigins()]).then(() => {
  if (new URLSearchParams(window.location.search).get('demo') === '1') loadJudgeDemo();
});
