'use strict';

// A shared, keyboard-operable single-select. Options stay stable during polling.
class AppSelect {
  constructor(root, {label, onChange}) {
    this.root = root;
    this.onChange = onChange;
    this.options = [];
    this.value = null;
    this.active = -1;
    this.opened = false;
    root.classList.add('app-select');
    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = 'select-trigger';
    this.button.id = root.id + '-trigger';
    this.button.setAttribute('role', 'combobox');
    this.button.setAttribute('aria-label', label);
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
    this.caption.textContent = this.options[index]?.label || '暂无任务';
    [...this.list.children].forEach((row, i) => row.setAttribute('aria-selected', String(i === index)));
    if (!this.opened) this.active = index;
  }

  open() {
    if (!this.options.length) return;
    this.opened = true;
    this.list.hidden = false;
    this.button.setAttribute('aria-expanded', 'true');
    this.activate(Math.max(0, this.options.findIndex(option => option.value === this.value)));
  }

  close() {
    this.opened = false;
    this.list.hidden = true;
    this.button.setAttribute('aria-expanded', 'false');
    this.button.removeAttribute('aria-activedescendant');
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
    this.setValue(option.value);
    this.close();
    this.button.focus({preventScroll: true});
    this.onChange(option.value);
  }

  keydown(event) {
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
      event.preventDefault();
      if (!this.opened) { this.open(); return; }
      const last = this.options.length - 1;
      if (event.key === 'ArrowDown') this.activate(Math.min(last, this.active + 1));
      else if (event.key === 'ArrowUp') this.activate(Math.max(0, this.active - 1));
      else if (event.key === 'Home') this.activate(0);
      else if (event.key === 'End') this.activate(last);
      else this.choose(this.active);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
    } else if (event.key === 'Tab') {
      this.close();
    } else if (/^[a-z0-9]$/i.test(event.key)) {
      this.search = (this.searchTime && Date.now() - this.searchTime < 700 ? this.search : '') + event.key;
      this.searchTime = Date.now();
      const index = this.options.findIndex(option => option.label.toLowerCase().startsWith(this.search.toLowerCase()));
      if (index >= 0) { if (!this.opened) this.open(); this.activate(index); }
    }
  }
}
