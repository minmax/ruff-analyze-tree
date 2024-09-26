# ruff-analyze-tree

Turns the output of `ruff analyze graph` into a colored tree.

## Example run on `fastapi` repo:

```zsh
git clone git@github.com:fastapi/fastapi.git && cd fastapi
uvx ruff analyze graph fastapi | uvx --from https://github.com/minmax/ruff-analyze-tree.git ruff-analyze-tree
```

<p align="center">
  <img src="https://github.com/user-attachments/assets/a78231ca-39f9-410f-bf75-f01a2a6806c8">
</p>

## All in one with `uvx`:

```bash
ruff analyze graph src | uvx --from https://github.com/minmax/ruff-analyze-tree.git ruff-analyze-tree
```

or step by step

## Install:

```bash
uv pip install https://github.com/minmax/ruff-analyze-tree.git
```

## Use:

```bash
ruff analyze graph src | python -m ruff_analyze_tree
```

## Options
`-q {percentile}` - Сommon boundary for dividing into good (green) / bad (red), e.g. "-q 99.9"

`--deps` - Show only dependencies.

`--hide-counters` - Don't show relations counters.

`--hide-deps` - Don't show dependencies.

`--hide-stats` - Don't show statistics.

`--hide-zero` - Don't show files without dependencies.

`--no-color` - Disable colors.
