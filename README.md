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

Or read a bulleted, newline-separated list from a file or stdin:

```console
uv run publix-sorter sort --file groceries.txt
cat groceries.txt | uv run publix-sorter sort
```

The model sorts Deli first, then Produce and other departments, numbered aisles
in ascending order, Milk, Raw Meat, and Frozen last. Location searches return
the first five Publix results and are cached at
`~/.cache/publix-sorter/locations.csv`. Override that path with `--cache` or
`PUBLIX_SORTER_CACHE`.

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
