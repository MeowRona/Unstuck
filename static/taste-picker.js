/* Qloo entity selector shared by Rescue and Plan a Day.
 * It performs no lookup until a user clicks the button and never guesses
 * which similarly named movie, book or artist the user intended.
 */
(() => {
  function mount(input) {
    if (!input || input.dataset.qlooPickerMounted) return;
    input.dataset.qlooPickerMounted = 'true';

    const wrapper = document.createElement('div');
    wrapper.className = 'qloo-picker';
    const controls = document.createElement('div');
    controls.className = 'qloo-picker-controls';
    const type = document.createElement('select');
    type.setAttribute('aria-label', 'Qloo cultural entity category');
    const kinds = [
      ['artist', 'Artist / music'],
      ['movie', 'Film'],
      ['book', 'Book'],
      ['tv_show', 'TV show'],
    ];
    kinds.forEach(([value, label]) => type.add(new Option(label, value)));
    const find = document.createElement('button');
    find.type = 'button';
    find.textContent = 'Find exact Qloo entity';
    find.className = 'qloo-picker-find';
    controls.append(type, find);
    const matches = document.createElement('div');
    matches.className = 'qloo-picker-matches';
    matches.setAttribute('aria-live', 'polite');
    const selected = document.createElement('div');
    selected.className = 'qloo-picker-selected';
    selected.setAttribute('aria-label', 'Selected cultural entities');
    const note = document.createElement('p');
    note.className = 'qloo-picker-note';
    note.textContent = 'Optional. Search is performed only when you click. Choosing a result avoids guessing which entity you meant; restaurant ranking still depends on Qloo coverage.';
    wrapper.append(controls, matches, selected, note);
    input.closest('label')?.after(wrapper);

    const refs = () => input.value.split(',').map(x => x.trim()).filter(Boolean);
    function selectedItems() {
      return refs().filter(x => x.startsWith('qloo-id:')).map(x => {
        const [id, kind, name] = x.slice(8).split('|');
        return {token:x, id, kind, name};
      }).filter(x => x.id && x.kind && x.name);
    }
    function renderSelected() {
      selected.replaceChildren();
      for (const item of selectedItems()) {
        const chip = document.createElement('span');
        chip.className = 'qloo-picker-chip';
        const label = document.createElement('span');
        label.textContent = item.name + ' (' + item.kind.replaceAll('_', ' ') + ')';
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.setAttribute('aria-label', 'Remove ' + item.name + ' Qloo entity');
        remove.addEventListener('click', () => {
          input.value = refs().filter(x => x !== item.token).join(', ');
          input.dispatchEvent(new Event('input', {bubbles:true}));
        });
        chip.append(label, remove);
        selected.append(chip);
      }
    }
    input.addEventListener('input', renderSelected);
    input.addEventListener('focus', renderSelected);
    renderSelected();

    find.addEventListener('click', async () => {
      const values = refs();
      const last = values[values.length - 1] || '';
      if (last.startsWith('qloo-id:')) {
        matches.textContent = 'Type a new name after a comma to search another entity.';
        return;
      }
      const hinted = last.match(/^(artist|music|movie|film|book|tv):\s*(.+)$/i);
      const kind = hinted ? ({music:'artist', film:'movie', tv:'tv_show'}[hinted[1].toLowerCase()] || hinted[1].toLowerCase()) : type.value;
      const query = (hinted ? hinted[2] : last).trim();
      if (query.length < 2 || query.length > 70) {
        matches.textContent = 'Enter one name (2–70 characters) as the last taste reference before searching.';
        return;
      }
      find.disabled = true;
      find.textContent = 'Searching Qloo…';
      matches.textContent = 'Looking for exact cultural entities…';
      try {
        const response = await fetch('/api/taste-entities', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({query, kind}),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || 'Qloo lookup failed');
        if (!payload.available) {
          matches.textContent = payload.reason || 'Live Qloo entity search is not available in this mode.';
          return;
        }
        if (!payload.options?.length) {
          matches.textContent = 'No Qloo entities returned. Keep the typed name or try a different category.';
          return;
        }
        matches.replaceChildren();
        const intro = document.createElement('p');
        intro.textContent = 'Choose the intended entity (no result is selected automatically):';
        matches.append(intro);
        for (const option of payload.options) {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'qloo-picker-option';
          button.textContent = option.name + ' · ' + option.kind.replaceAll('_', ' ') + ' · ' + option.id;
          button.addEventListener('click', () => {
            // Pipe/comma delimiters are reserved by the backend's token grammar.
            const safeName = option.name.replace(/[|,\r\n]/g, ' ').trim().slice(0, 80);
            const token = 'qloo-id:' + option.id + '|' + option.kind + '|' + safeName;
            const current = refs();
            const previous = current.slice(0, -1);
            if (!previous.includes(token)) previous.push(token);
            input.value = previous.join(', ');
            input.dispatchEvent(new Event('input', {bubbles:true}));
            matches.textContent = 'Selected ' + safeName + '. The final plan will show whether Qloo actually ranked any places using it.';
          });
          matches.append(button);
        }
      } catch (err) {
        matches.textContent = 'Qloo lookup unavailable: ' + err.message + '. You can still type a name manually.';
      } finally {
        find.disabled = false;
        find.textContent = 'Find exact Qloo entity';
      }
    });
  }
  mount(document.querySelector('#plannerTasteRefs'));
  mount(document.querySelector('#editorForm [name="taste_refs"]'));
})();
