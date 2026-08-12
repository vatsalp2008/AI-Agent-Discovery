/**
 * The combobox wiring for name suggestions.
 *
 * `Suggest` holds the pure ranking logic; this is the DOM half — building the
 * listbox, keeping ARIA state in step, and handling the keyboard. It lived in
 * main.js, which had grown to twice the size of any other page script.
 *
 * Attached rather than self-starting, so the caller supplies what it owns:
 * the elements, and what to do when a suggestion is chosen.
 */
const SearchSuggestions = (() => {
    /**
     * Wire suggestions to an input and a listbox.
     *
     * Returns a handle with `close()` — the search form needs to dismiss the
     * list on submit — and `load()` to fetch the names.
     */
    function attach({ input, list, onChoose, fetchNames }) {
        if (!input || !list) {
            // A page without the markup gets a no-op handle rather than a crash.
            return { close() {}, async load() {}, isOpen: () => false };
        }

        let names = [];
        let items = [];
        let active = -1;

        function close() {
            list.hidden = true;
            list.replaceChildren();
            items = [];
            active = -1;
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
        }

        function highlight(index) {
            items.forEach((item, i) => {
                const on = i === index;
                item.classList.toggle('active', on);
                item.setAttribute('aria-selected', on ? 'true' : 'false');
            });
            active = index;
            if (index >= 0) {
                input.setAttribute('aria-activedescendant', items[index].id);
            } else {
                input.removeAttribute('aria-activedescendant');
            }
        }

        function choose(name) {
            input.value = name;
            close();
            if (onChoose) onChoose(name);
        }

        function show() {
            const matches = Suggest.rank(names, input.value);
            if (matches.length === 0) {
                close();
                return;
            }

            items = matches.map((match, index) => {
                const item = document.createElement('li');
                item.className = 'suggestion';
                item.id = `suggestion-${index}`;
                item.setAttribute('role', 'option');
                item.setAttribute('aria-selected', 'false');

                Suggest.segments(match.name, input.value).forEach(part => {
                    const span = document.createElement(part.match ? 'mark' : 'span');
                    span.textContent = part.text;
                    item.appendChild(span);
                });

                // mousedown, not click: blur would close the list first.
                item.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    choose(match.name);
                });
                return item;
            });

            list.replaceChildren(...items);
            list.hidden = false;
            input.setAttribute('aria-expanded', 'true');
            highlight(-1);
        }

        input.addEventListener('input', show);
        input.addEventListener('blur', () => setTimeout(close, 120));

        input.addEventListener('keydown', (e) => {
            if (list.hidden) return;

            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                highlight(Suggest.nextIndex(active, items.length, e.key === 'ArrowDown' ? 1 : -1));
            } else if (e.key === 'Enter' && active >= 0) {
                e.preventDefault();
                choose(items[active].textContent);
            } else if (e.key === 'Escape') {
                close();
            }
        });

        return {
            close,
            isOpen: () => !list.hidden,
            async load() {
                if (!fetchNames) return;
                names = await fetchNames();
            },
        };
    }

    return { attach };
})();

if (typeof module !== 'undefined') module.exports = SearchSuggestions;
