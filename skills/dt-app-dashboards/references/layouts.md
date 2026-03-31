# Dashboard Layouts

Layouts define tile positioning on the dashboard grid. Each layout entry
corresponds to a tile ID from the `tiles` object.

## Layout Structure

```json
{
  "layouts": {
    "14": {
      "x": 0,
      "y": 0,
      "w": 20,
      "h": 1
    },
    "2": {
      "x": 0,
      "y": 2,
      "w": 20,
      "h": 12
    }
  }
}
```

## Positioning Properties

Each layout entry defines the position and size of a tile:

- `x`: Horizontal position (column) - starts at 0
- `y`: Vertical position (row) - starts at 0
- `w`: Width in grid units
- `h`: Height in grid units

## Grid System

The dashboard uses a **grid system with configurable column count**. By
default, dashboards use 20 columns (via `gridColumnsCount: 20` at root level
or `settings.gridLayout.columnsCount`), but this can be customized. The full
width of the dashboard is divided into the configured number of equal columns.

### Common Width Patterns

- **Full-width tiles**: `w: 20` (spans entire dashboard width)
- **Half-width tiles**: `w: 10` (two tiles side-by-side)
- **Quarter-width tiles**: `w: 5` (four tiles side-by-side)

### Height Units

Height (`h`) is measured in grid units where each unit represents a standard
row height. Common values:

- `h: 1`: Small height (good for headers/markdown tiles)
- `h: 6-8`: Medium height (typical for charts)
- `h: 12-16`: Large height (detailed visualizations)

## Layout Patterns

### Stacking Tiles Vertically

Tiles are positioned from top to bottom by increasing the `y` value:

```json
{
  "1": { "x": 0, "y": 0, "w": 20, "h": 1 },
  "2": { "x": 0, "y": 1, "w": 20, "h": 8 },
  "3": { "x": 0, "y": 9, "w": 20, "h": 8 }
}
```

### Placing Tiles Side-by-Side

Tiles can be positioned horizontally by varying the `x` value while keeping
the same `y`:

```json
{
  "1": { "x": 0, "y": 0, "w": 10, "h": 8 },
  "2": { "x": 10, "y": 0, "w": 10, "h": 8 }
}
```

## Responsive Considerations

- The 20-unit grid provides flexibility for different screen sizes
- Keep tiles at standard widths (for 20-column grid: 5, 10, 20) for best responsiveness
- Avoid complex fractional widths that don't align to the grid
- Remember that tiles with `x + w > gridColumnsCount` will wrap to the next row
- The grid mode can be set to "canvas" or "responsive" via `settings.gridLayout.mode`
