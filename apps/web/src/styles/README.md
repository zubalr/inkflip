# Styles contract

- `tokens.css` is the single source of semantic design tokens, derived from
  `planning/product/design-tokens.json`. Raw color, spacing, radius and type
  values are defined **only** here.
- `global.css` holds the minimal token-free reset plus element defaults that
  consume tokens. No component rules.
- Component styles are CSS Modules: `*.module.css` files imported from their
  component. Rules must consume `var(--token)`; do not introduce new raw
  colors, spacing values or fonts outside `tokens.css`.
- Breakpoints (media queries cannot use custom properties): 1100px, 768px,
  320px minimum width floor.
- Ownership: established by T01; `apps/web/src/styles/` is owned by T06 after
  bootstrap acceptance.
