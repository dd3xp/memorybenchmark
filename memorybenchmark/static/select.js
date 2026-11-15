'use strict';

// A shared, keyboard-operable single-select. Options stay stable during polling.
class AppSelect {
  constructor(root, {label, onChange, labelledBy, placeholder = '暂无任务', floating = false}) {
    this.root = root;
    this.onChange = onChange;
    this.options = [];
    this.value = null;
    this.active = -1;
    this.opened = false;
    this.placeholder = placeholder;
    this.floating = floating;
    root.classList.add('app-select');
    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = 'select-trigger';
    this.button.id = root.id + '-trigger';
    this.button.setAttribute('role', 'combobox');
    this.button.setAttribute('aria-label', label);
    if (labelledBy) this.button.setAttribute('aria-labelledby', labelledBy);
    this.button.setAttribute('aria-haspopup', 'listbox');
    this.button.setAttribute('aria-expanded', 'false');
    this.button.setAttribute('aria-controls', root.id + '-list');
    this.caption = document.createElement('span');
    const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevron.setAttribute('viewBox', '0 0 16 16');
    chevron.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(chevron.namespaceURI, 'path');
    path.setAttribute('d', 'm4 6 4 4 4-4');
    chevron.append(path);
    this.button.append(this.caption, chevron);
    this.list = document.createElement('div');
    this.list.id = root.id + '-list';
    this.list.className = 'select-list';
    this.list.setAttribute('role', 'listbox');
    this.list.setAttribute('aria-label', label);
    this.list.hidden = true;
    if (floating) {
      this.list.classList.add('select-floating');
      // The top layer prevents a long map list from clipping inside a dialog.
      if ('showPopover' in this.list) this.list.popover = 'manual';
      const reposition = () => { if (this.opened) this.position(); };
      window.addEventListener('resize', reposition);
      window.addEventListener('scroll', reposition, true);
    }
    root.replaceChildren(this.button, this.list);
    this.button.onclick = () => this.opened ? this.close() : this.open();
    this.button.onkeydown = event => this.keydown(event);
    document.addEventListener('pointerdown', event => {
      if (!root.contains(event.target)) this.close();
    });
    root.addEventListener('focusout', event => {
      if (!root.contains(event.relatedTarget)) this.close();
    });
    this.setOptions([]);
  }

  setOptions(options) {
    if (JSON.stringify(options) === JSON.stringify(this.options) && this.list.childElementCount) return;
    this.options = options;
    this.list.replaceChildren();
    options.forEach((option, index) => {
      const row = document.createElement('div');
      row.id = this.root.id + '-option-' + index;
      row.className = 'select-option';
      row.setAttribute('role', 'option');
      const label = document.createElement('span');
      label.textContent = option.label;
      const mark = document.createElement('span');
      mark.className = 'select-mark';
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = '✓';
      row.append(label, mark);
      row.onpointerdown = event => event.preventDefault();
      row.onclick = () => this.choose(index);
      row.onpointermove = () => this.activate(index, false);
      this.list.append(row);
    });
    this.button.disabled = !options.length;
    if (!options.length) this.close();
    this.setValue(this.value);
  }

  setValue(value) {
    this.value = value;
    const index = this.options.findIndex(option => option.value === value);
    this.caption.textContent = this.options[index]?.label || this.placeholder;
    [...this.list.children].forEach((row, i) => row.setAttribute('aria-selected', String(i === index)));
    if (!this.opened) this.active = index;
  }

  open() {
    if (!this.options.length || this.button.matches(':disabled')) return;
    this.opened = true;
    this.list.hidden = false;
    if (this.list.popover) this.list.showPopover();
    if (this.floating) this.position();
    this.button.setAttribute('aria-expanded', 'true');
    this.activate(Math.max(0, this.options.findIndex(option => option.value === this.value)));
  }

  close() {
    this.opened = false;
    if (this.list.popover && this.list.matches(':popover-open')) this.list.hidePopover();
    this.list.hidden = true;
    this.button.setAttribute('aria-expanded', 'false');
    this.button.removeAttribute('aria-activedescendant');
  }

  position() {
    const box = this.button.getBoundingClientRect(), margin = 12, gap = 6;
    const width = Math.min(Math.max(box.width, 144), innerWidth - margin * 2);
    this.list.style.width = `${width}px`;
    this.list.style.maxHeight = '296px';
    const desired = Math.min(296, this.list.scrollHeight + 2);
    const below = innerHeight - box.bottom - gap - margin, above = box.top - gap - margin;
    const upwards = below < desired && above > below;
    const height = Math.min(desired, Math.max(44, upwards ? above : below));
    this.list.style.maxHeight = `${height}px`;
    this.list.style.left = `${Math.max(margin, Math.min(box.left, innerWidth - width - margin))}px`;
    this.list.style.top = `${upwards ? Math.max(margin, box.top - gap - height) : box.bottom + gap}px`;
  }

  activate(index, scroll = true) {
    this.active = index;
    [...this.list.children].forEach((row, i) => row.classList.toggle('active', i === index));
    const row = this.list.children[index];
    if (!row) return;
    this.button.setAttribute('aria-activedescendant', row.id);
    if (scroll) {
      const top = row.offsetTop, bottom = top + row.offsetHeight;
      if (top < this.list.scrollTop) this.list.scrollTop = top;
      else if (bottom > this.list.scrollTop + this.list.clientHeight) this.list.scrollTop = bottom - this.list.clientHeight;
    }
  }

  choose(index) {
    const option = this.options[index];
    if (!option) return;
    const changed = this.value !== option.value;
    this.setValue(option.value);
    this.close();
    this.button.focus({preventScroll: true});
    if (changed) this.onChange(option.value);
  }

  keydown(event) {
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
      event.preventDefault();
      if (!this.opened) {
        this.open();
        if (event.key === 'Home') this.activate(0);
        else if (event.key === 'End') this.activate(this.options.length - 1);
        return;
      }
      const last = this.options.length - 1;
      if (event.key === 'ArrowDown') this.activate(Math.min(last, this.active + 1));
      else if (event.key === 'ArrowUp') this.activate(Math.max(0, this.active - 1));
      else if (event.key === 'Home') this.activate(0);
      else if (event.key === 'End') this.activate(last);
      else this.choose(this.active);
    } else if (event.key === 'Escape' && this.opened) {
      event.preventDefault();
      event.stopPropagation();
      this.close();
    } else if (event.key === 'Tab') {
      this.close();
    } else if (!event.ctrlKey && !event.metaKey && !event.altKey && /^[a-z0-9]$/i.test(event.key)) {
      const previous = this.searchTime && Date.now() - this.searchTime < 700 ? this.search : '';
      this.search = previous + event.key;
      this.searchTime = Date.now();
      const repeated = [...this.search.toLowerCase()].every(char => char === event.key.toLowerCase());
      const query = repeated ? event.key.toLowerCase() : this.search.toLowerCase();
      const start = repeated ? this.active + 1 : 0;
      const index = this.options.map((_, i) => (start + i) % this.options.length)
        .find(i => this.options[i].label.toLowerCase().startsWith(query));
      if (index !== undefined) { event.preventDefault(); if (!this.opened) this.open(); this.activate(index); }
    }
  }
}
