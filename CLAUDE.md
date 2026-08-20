# jobrake agent instructions

## Style

- Keep module docstrings to one-line orientation. Keep short docstrings on one
  line; longer ones open with a bare `"""` and put the summary on the next line.
  Put rationale and contracts on the symbol that owns them.
- Comments explain non-obvious mechanisms or reasons. User-facing messages
  state what happened, name the likely cause when known, and give a concrete next action.
- Treat style checks as heuristics, not bans. Preserve useful facts, concrete
  examples, and the author's voice. Use punctuation where it improves clarity.

## Changelog

- Use `[version] (date)`, an `Unreleased` section, and the standard change
  categories. Treat released entries as historical records; correct errors
  without broadly restyling their prose.
