# Publix Sorter

A minimal, unofficial CLI prototype that searches Publix and prints product
names with their locations in Chasewood Plaza (store 228).

## Usage

```console
uv run publix-sorter pasta
uv run publix-sorter "tomato sauce"
```

The CLI reads the first page of products rendered by Publix search. Because it
scrapes an undocumented page payload, Publix site changes may require parser
updates.

## Tests

```console
uv run python -m unittest discover -s tests
```
