# docs/demo/demo.tape — reproducible source for docs/assets/demo.gif
#
# Regenerate the GIF (from the repository root):
#     vhs docs/demo/demo.tape
# Requires: vhs + ttyd + ffmpeg + tree on PATH (`brew install vhs tree`; vhs pulls ttyd in).
#
# The recording is the whole pipeline on the GitHub API example, from a clean slate: the
# spec tree with no generated code, the real generator writing 15 files, and the tree it
# produced. Nothing is staged or faked — the Hide block deletes `examples/github/out`
# before recording, and the recorded `refract generate --write` puts it back byte-for-byte
# identical to what is committed (which is what `--check` gates in CI).
#
# Width 1040 gives an 87-column terminal, the narrowest that fits the longest recorded line
# (the 83-character `generate` invocation) without wrapping. Height 820 gives 38 rows for
# 37 rows of content, so nothing scrolls.

Output docs/assets/demo.gif

Set Shell bash
Set FontSize 17
Set Width 1040
Set Height 820
Set Padding 24
Set TypingSpeed 55ms
Set Theme { "name": "Catppuccin Mocha", "background": "#1e1e2e", "foreground": "#cdd6f4", "cursor": "#f5e0dc", "selection": "#585b70", "black": "#45475a", "brightBlack": "#585b70", "red": "#f38ba8", "brightRed": "#f38ba8", "green": "#a6e3a1", "brightGreen": "#a6e3a1", "yellow": "#f9e2af", "brightYellow": "#f9e2af", "blue": "#89b4fa", "brightBlue": "#89b4fa", "magenta": "#cba6f7", "brightMagenta": "#cba6f7", "cyan": "#94e2d5", "brightCyan": "#94e2d5", "white": "#bac2de", "brightWhite": "#a6adc8" }

# Sync once, set a clean prompt, and delete the generated output — all off-camera, so the
# recording starts from a spec-only tree with no install noise.
Hide
Type 'uv sync --dev >/dev/null 2>&1' Enter
Type 'export PS1="❯ "' Enter
Type 'rm -rf examples/github/out' Enter
Type 'clear' Enter
Show

# The input: two resources and one client.yaml. No generated code anywhere.
Type "tree examples/github" Sleep 500ms Enter
Sleep 2.5s

# The generator, for real.
Type "uv run refract generate --write --specs examples/github --out examples/github/out" Sleep 500ms Enter
Sleep 2.5s

# The output: models, request builders, a client, a CLI, an MCP server and tests.
Type "tree examples/github/out" Sleep 500ms Enter
Sleep 3.5s
