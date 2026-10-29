# Contributing

The pipeline is small and standard-library only. Keep it that way: a new dependency needs a strong
reason, because the main value of this tool is that it runs anywhere Python runs.

## Before you open a pull request

```bash
cd skills/design_skill_generator
python3 -m unittest discover -s tests -v
```

All 22 tests must pass. `python3 -m unittest` uses no network.

## Adding support for a portal or a block type

1. Add a fixture to `tests/fixtures/site/` that reproduces the shape you want to support.
2. Write the failing test first.
3. Add the code. Prefer a config key over a hardcoded value when the difference is a name, a path
   or a content-type id.
4. Update `README.md` if a config key or a stage changed, and `skills/design_skill_generator/references/guide.md`
   if a renderer or an extension point changed.

## Rules

- No network access in tests. Use the local fixture server.
- Never drop content silently. An unknown block renders as text with an
  `<!-- unhandled content type: ... -->` marker.
- Keep the politeness delays configurable and non-zero by default.
- Do not commit `cache/`, `raw_data/`, `assets/` or `config.json`. They are local build state.

## Licence

By contributing you agree that your contribution is licensed under GPL-3.0, the licence of this
repository.
