const form = document.getElementById('briefForm');
const errorBox = document.getElementById('formError');
const resultsSection = document.getElementById('resultsSection');
const cardsEl = document.getElementById('cards');
const emptyEl = document.getElementById('emptyState');
const agentLog = document.getElementById('agentLog');
const roundLabel = document.getElementById('roundLabel');
const constraintSummary = document.getElementById('constraintSummary');
const modeBadge = document.getElementById('modeBadge');
const originList = document.getElementById('originList');
const originCount = document.getElementById('originCount');
const loadJudgeDemo = document.getElementById('loadJudgeDemo');
const quickBudget = document.getElementById('quickBudget');
const applyBudget = document.getElementById('applyBudget');
let sessionId = null;
let currentResult = null;

function selectedValues(select) {
  return [...select.selectedOptions].map(o => o.value);
}

function formPayload() {
  const fd = new FormData(form);
  const goal = fd.get('goal');
  return {
    original_plan: fd.get('original_plan'),
    failed_place: fd.get('failed_place'),
    failure_reason: fd.get('failure_reason'),
    goal,
    city: 'Warsaw',
    date: fd.get('date'),
    start_time: fd.get('start_time'),
    return_by: fd.get('return_by'),
    min_stay_minutes: Number(fd.get('min_stay_minutes')),
    people: Number(fd.get('people')),
    budget_total: Number(fd.get('budget_total')),
    currency: 'PLN',
    origin: fd.get('origin'),
    travel_mode: fd.get('travel_mode'),
    max_one_way_minutes: Number(fd.get('max_one_way_minutes')),
    categories: [...form.querySelectorAll('input[name="category"]:checked')].map(x => x.value),
    taste_refs: String(fd.get('taste_refs') || '').split(',').map(x => x.trim()).filter(Boolean),
    meal_required: goal === 'meal',
    negotiable_extra_travel_minutes: Number(fd.get('negotiable_extra_travel_minutes')),
    negotiable_stay_reduction_minutes: Number(fd.get('negotiable_stay_reduction_minutes')),
    allow_category_change: form.elements.allow_category_change.checked,
  };
}

async function api(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function money(card) {
  const c = card.cost;
  if (c.min == null || c.max == null) return 'Unknown';
  return c.min === c.max ? `${c.max.toFixed(0)} ${c.currency}` : `${c.min.toFixed(0)}–${c.max.toFixed(0)} ${c.currency}`;
}

function changeText(change) {
  if (change.field === 'one-way travel') return `${change.from} → ${change.to}`;
  if (change.field === 'minimum stay') return `${change.from} → ${change.to}`;
  if (change.field === 'category') return `${change.from} → ${change.to}`;
  return `${change.field}: ${change.from ?? ''} → ${change.to ?? ''}`;
}

function sourceLine(label, source) {
  const status = escapeHtml(source?.status || 'unknown');
  const checked = source?.checked_at ? ` · checked ${escapeHtml(source.checked_at)}` : '';
  const link = source?.url ? ` · <a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">source</a>` : '';
  return `<div><strong>${label}:</strong> ${status}${checked}${link}</div>`;
}

function lockButton(change) {
  if (change.field === 'one-way travel') return `<button class="ghost lock-change" data-field="travel">Don't go farther</button>`;
  if (change.field === 'minimum stay') return `<button class="ghost lock-change" data-field="stay">Keep full stay</button>`;
  if (change.field === 'category') return `<button class="ghost lock-change" data-field="category">Keep category</button>`;
  return '';
}

function renderCard(card) {
  const keep = card.keep.map(x => `<span class="chip keep">${escapeHtml(x)}</span>`).join('');
  const changes = card.change.length
    ? card.change.map(x => `<span class="chip change">${escapeHtml(changeText(x))}</span>`).join('')
    : '<span class="chip keep">No compromise needed</span>';
  const needs = card.needs_checking.length
    ? `<div class="needs">${card.needs_checking.map(x => `• ${escapeHtml(x)}`).join('<br>')}</div>`
    : '<div class="needs">Nothing material is flagged by the current data status.</div>';
  const lockButtons = card.change.map(lockButton).join('');
  const fixture = card.demo_fixture ? '<div class="fixture-note">Demo operational fixture — not a real venue and not Qloo output.</div>' : '';
  const feasibility = card.feasibility_status === 'confirmed'
    ? '<span class="chip keep">Confirmed by current facts</span>'
    : '<span class="chip change">Requires fact check</span>';
  return `<article class="card" data-place-id="${escapeHtml(card.id)}">
    <div class="card-top"><div><div class="category">${escapeHtml(card.category)}</div><h3>${escapeHtml(card.name)}</h3><div class="card-address">${escapeHtml(card.address || '')}</div></div>${feasibility}</div>
    ${fixture}
    <div class="metric-row">
      <div class="metric"><b>${escapeHtml(money(card))}</b><span>${card.cost.for_people} people</span></div>
      <div class="metric"><b>≈ ${card.timing.travel_one_way_minutes} min</b><span>one way · estimated</span></div>
      <div class="metric"><b>${escapeHtml(card.timing.estimated_return)}</b><span>estimated return</span></div>
    </div>
    <div><div class="block-title">Keep</div><div class="keep-list">${keep}</div></div>
    <div><div class="block-title">Change</div><div class="change-list">${changes}</div></div>
    <div><div class="block-title">Why this fits</div><div class="why">${escapeHtml(card.why_this_fits)}</div></div>
    <div><div class="block-title">Needs checking</div>${needs}</div>
    <details class="source-details"><summary>Sources & assumptions</summary>
      ${sourceLine('Price', card.cost.source)}
      <div><strong>Price basis:</strong> ${escapeHtml(card.cost.basis || 'not specified')}</div>
      ${sourceLine('Hours', card.hours_source)}
      <div><strong>Location:</strong> geocoded from the listed address${card.location_source?.checked_at ? ` · checked ${escapeHtml(card.location_source.checked_at)}` : ''}${card.location_source?.url ? ` · <a href="${escapeHtml(card.location_source.url)}" target="_blank" rel="noreferrer">source</a>` : ''}</div>
      <div><strong>Travel:</strong> straight-line-derived estimate, not a live route.</div>
      <div>${escapeHtml(card.source_note || '')}</div>
    </details>
    <div class="card-actions">
      <button class="danger reject" data-place-id="${escapeHtml(card.id)}">Reject this place</button>
      ${lockButtons}
    </div>
  </article>`;
}

function render(result) {
  currentResult = result;
  resultsSection.classList.remove('hidden');
  roundLabel.textContent = `Round ${result.round} · strategy: ${result.strategy_used}`;
  quickBudget.value = result.brief.budget_total;
  const b = result.brief;
  constraintSummary.innerHTML = [
    `${b.people} people`, `${b.budget_total} ${b.currency} locked`, `Back by ${b.return_by} locked`,
    `${b.min_stay_minutes} min stay`, `≤ ${b.max_one_way_minutes} min one way`, b.meal_required ? 'Meal required' : `Goal: ${b.goal}`
  ].map(x => `<span>${escapeHtml(x)}</span>`).join('');
  cardsEl.innerHTML = result.cards.map(renderCard).join('');
  cardsEl.classList.toggle('hidden', result.empty);
  emptyEl.classList.toggle('hidden', !result.empty);
  if (result.empty) {
    const reasons = result.empty_explanation.map(x => `<li>${escapeHtml(x.reason)} <small>(${x.count} candidates)</small></li>`).join('');
    emptyEl.innerHTML = `<h3>No feasible rescue in the checked pool.</h3><p>Unstuck did not silently break a locked condition. Main blockers:</p><ul>${reasons}</ul>`;
  }
  agentLog.innerHTML = result.agent_log.map(x => `<li>${escapeHtml(x)}</li>`).join('');
  bindCardActions();
  resultsSection.scrollIntoView({behavior: 'smooth', block: 'start'});
}

function bindCardActions() {
  document.querySelectorAll('.reject').forEach(btn => btn.addEventListener('click', async () => {
    await runAction(() => api('/api/reject', {session_id: sessionId, place_id: btn.dataset.placeId}));
  }));
  document.querySelectorAll('.lock-change').forEach(btn => btn.addEventListener('click', async () => {
    const field = btn.dataset.field;
    const patch = field === 'travel' ? {negotiable_extra_travel_minutes: 0}
      : field === 'stay' ? {negotiable_stay_reduction_minutes: 0}
      : {allow_category_change: false};
    await runAction(() => api('/api/update', {session_id: sessionId, patch}));
  }));
}

async function runAction(fn) {
  errorBox.classList.add('hidden');
  try {
    const result = await fn();
    sessionId = result.session_id;
    render(result);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.remove('hidden');
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = form.querySelector('button[type=submit]');
  submit.disabled = true;
  submit.textContent = 'Checking feasibility…';
  await runAction(() => api('/api/search', formPayload()));
  submit.disabled = false;
  submit.textContent = 'Find the smallest rescue';
});

applyBudget.addEventListener('click', async () => {
  const value = Number(quickBudget.value);
  if (!sessionId || !value) return;
  await runAction(() => api('/api/update', {session_id: sessionId, patch: {budget_total: value}}));
});

loadJudgeDemo.addEventListener('click', () => {
  form.elements.original_plan.value = 'Dinner somewhere calm where we can talk after another venue fell through';
  form.elements.failed_place.value = 'Closed Place';
  form.elements.failure_reason.value = 'It is closed tonight';
  form.elements.goal.value = 'meal';
  form.elements.people.value = '2';
  form.elements.budget_total.value = '200';
  form.elements.max_one_way_minutes.value = '25';
  form.elements.date.value = '2026-10-10';
  form.elements.start_time.value = '18:30';
  form.elements.return_by.value = '22:00';
  form.elements.min_stay_minutes.value = '75';
  form.elements.origin.value = 'Warszawa Centralna';
  form.elements.travel_mode.value = 'transit';
  form.querySelectorAll('input[name="category"]').forEach(input => {
    input.checked = input.value === 'restaurant';
  });
  form.elements.taste_refs.value = 'Amelie, Radiohead';
  form.elements.negotiable_extra_travel_minutes.value = '8';
  form.elements.negotiable_stay_reduction_minutes.value = '15';
  form.elements.allow_category_change.checked = false;
  form.scrollIntoView({behavior: 'smooth', block: 'start'});
});

fetch('/api/health').then(r => r.json()).then(status => {
  if (status.provider_mode === 'live') {
    modeBadge.textContent = 'REAL PLACE FACTS · LIVE QLOO';
  } else if (status.provider_mode === 'baseline') {
    modeBadge.textContent = 'REAL PLACE FACTS · NO-TASTE BASELINE';
  } else if (status.catalog_mode === 'real') {
    modeBadge.textContent = 'REAL PLACE FACTS · FIXTURE TASTE · QLOO NOT CALLED';
  } else {
    modeBadge.textContent = 'FULL DEMO FIXTURES · QLOO NOT CALLED';
  }
  modeBadge.classList.add(status.provider_mode);
}).catch(() => { modeBadge.textContent = 'Backend unavailable'; });

fetch('/api/origins').then(r => r.json()).then(payload => {
  const origins = Array.isArray(payload.origins) ? payload.origins : [];
  originList.innerHTML = origins.map(origin =>
    `<option value="${escapeHtml(origin.label)}">${escapeHtml(origin.district)} · ${escapeHtml(origin.label)}</option>`
  ).join('');
  const districtCount = Object.keys(payload.districts || {}).length;
  originCount.textContent = `${origins.length} saved points across ${districtCount} districts`;
}).catch(() => {
  originCount.textContent = 'start-point catalog unavailable';
});
