# Publix Sorter

A minimal, unofficial CLI prototype that uses GPT-5.6 Luna through OpenRouter
to sort a grocery list by product locations at Chasewood Plaza (Publix store
228).

## Sort a grocery list

Set an OpenRouter API key:

```console
export OPENROUTER_API_KEY=your-key
```

Pass grocery items as arguments:

```console
uv run publix-sorter sort \
  "grapes - green" \
  "apples x4" \
  "penne pasta" \
  "cheddar cheese"
```

The sorted output includes the selected store location as an inline comment:

```text
- grapes - green  # Produce
- apples x4  # Produce
- cheddar cheese  # Rear Left - Cheese
- penne pasta  # Aisle 6 - Pasta & Pasta Sauce
```

Or read a bulleted, newline-separated list from a file or stdin:

```console
uv run publix-sorter sort --file groceries.txt
cat groceries.txt | uv run publix-sorter sort
```

The model sorts Deli first, then Produce and other departments, aisles 1–9,
Cheese, remaining numbered aisles, other Dairy, Raw Meat, and Frozen last.
Location searches return the first five Publix results and are cached at
`~/.cache/publix-sorter/locations.csv`. Override that path with `--cache` or
`PUBLIX_SORTER_CACHE`.

Add `--debug` to write the sorting agent's system and user input, each output
text, and every tool call and result to stderr without changing the sorted
stdout output:

```console
uv run publix-sorter sort --debug "milk" "penne pasta"
```

## Sort a Todoist project

Set a Todoist API token from Todoist's **Settings → Integrations** page, along
with the OpenRouter key:

```console
export TODOIST_API_TOKEN=your-token
export OPENROUTER_API_KEY=your-key
```

Then provide a project name or ID:

```console
uv run publix-sorter todoist "Groceries"
uv run publix-sorter todoist --debug "Groceries"
```

The command reads all active tasks in the project, sorts them through the same
Publix workflow, and writes the new order back to Todoist. It preserves
unrelated labels and replaces any prior `Publix: ` label with the current store
location. Numbered aisles use only the aisle number, such as `Publix: 6`, while
departments use labels such as `Publix: Produce`. Unknown locations have no
Publix label.

Only flat projects are supported. The command stops without making changes if
any active task belongs to a section or is a subtask. Completed tasks are not
included by Todoist's active-task API.

## Search Publix

The underlying product-location search remains available:

```console
uv run publix-sorter search pasta
uv run publix-sorter pasta
```

The search reads the first page rendered by Publix. Because it scrapes an
undocumented page payload, Publix site changes may require parser updates.

## Tests

```console
uv run python -m unittest discover -s tests
```
