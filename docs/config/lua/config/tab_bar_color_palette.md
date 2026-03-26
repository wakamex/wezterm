---
tags:
  - tab_bar
---
# `tab_bar_color_palette = "Dark"`

Controls which family of built-in generated tab colors is used when
[tab_bar_color_mode](tab_bar_color_mode.md) is set to `Hash` or `Assign`.

Possible values are:

- `"Dark"`: generate darker tab backgrounds so they generally pair with light text
- `"Light"`: generate lighter tab backgrounds so they generally pair with dark text
- `"Mixed"`: allow both dark and light generated backgrounds

This option controls the family of generated background colors. In practice,
`"Dark"` tends to yield light foreground text, `"Light"` tends to yield dark
foreground text, and `"Mixed"` allows either based on contrast.

The default is `"Dark"`.
