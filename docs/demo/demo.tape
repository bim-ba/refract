# docs/demo/demo.tape — reproducible source for docs/assets/demo.gif
#
# Regenerate the GIF (from the repository root):
#     vhs docs/demo/demo.tape
# Requires: vhs + ttyd + ffmpeg on PATH (`brew install vhs` pulls ttyd in).
# The Hide block below syncs the dev extras up front, so no command prints install
# noise into the recording.
#
# Everything recorded is real, offline and credential-free: a slice of the checked-in
# `me` spec, the actual `refract generate --check` drift gate against the committed
# `examples/ycli-tracker/out/`, and the whole generated FastMCP tool that the `mcp:`
# facet in the first slice produced.
#
# Width is 1240 (not ycli's 960) because this repo formats at 100 columns
# (`line-length = 100` in pyproject.toml): 960 gives an 80-column terminal, which
# wraps the project's own generated code.

Output docs/assets/demo.gif

Set Shell bash
Set FontSize 17
Set Width 1240
Set Height 980
Set Padding 24
Set TypingSpeed 55ms
Set Theme { "name": "Catppuccin Mocha", "background": "#1e1e2e", "foreground": "#cdd6f4", "cursor": "#f5e0dc", "selection": "#585b70", "black": "#45475a", "brightBlack": "#585b70", "red": "#f38ba8", "brightRed": "#f38ba8", "green": "#a6e3a1", "brightGreen": "#a6e3a1", "yellow": "#f9e2af", "brightYellow": "#f9e2af", "blue": "#89b4fa", "brightBlue": "#89b4fa", "magenta": "#cba6f7", "brightMagenta": "#cba6f7", "cyan": "#94e2d5", "brightCyan": "#94e2d5", "white": "#bac2de", "brightWhite": "#a6adc8" }

# Sync once and set a clean prompt, all off-camera, so the recorded commands run
# instantly with no install noise.
Hide
Type 'uv sync --dev >/dev/null 2>&1' Enter
Type 'export PS1="❯ "' Enter
Type 'clear' Enter
Show

# The input: one operation, with its MCP tool and CLI command declared inline.
Type "sed -n '21,39p' examples/ycli-tracker/tracker/me/resource.yaml" Sleep 500ms Enter
Sleep 3s

# The drift gate: render in memory, diff against the committed output.
Type "uv run refract generate --check" Sleep 500ms Enter
Sleep 2.5s

# The output: the whole FastMCP tool the `mcp:` facet above produced.
Type "cat examples/ycli-tracker/out/tracker/me/mcp.py" Sleep 500ms Enter
Sleep 3.5s
