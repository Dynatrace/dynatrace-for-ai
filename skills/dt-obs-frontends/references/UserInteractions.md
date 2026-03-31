# User Interactions & Behavior

Analyze user clicks, form inputs, scrolls, and other interactions for UX insights.

**Data Source:** `fetch user.events` with `characteristics.has_user_interaction`

**Key Fields:**

- `interaction.name` - Type: click, change, blur, scroll, touch, etc.
- `ui_element.name` - Element identifier (aria-label, title, name, etc.)
- `ui_element.custom_name` - Custom name via `data-dt-name` attribute
- `ui_element.tag_name` - HTML tag or mobile component type
- `ui_element.features` - Feature grouping via `data-dt-features`
- `positions` - Click/touch coordinates

## All User Interactions

Query all interaction types:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| summarize
    interaction_count = count(),
    session_count = countDistinct(dt.rum.session.id),
    by: {frontend.name, interaction.name}
| sort interaction_count desc

```

**Use Case:** Understand interaction patterns by type.

## Click Analysis

Analyze button/link clicks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| filter interaction.name == "click"
| summarize
    click_count = count(),
    unique_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {frontend.name, ui_element.resolved_name, ui_element.tag_name}
| sort click_count desc
| limit 30

```

**Use Case:** Identify most-clicked UI elements.

## Form Field Changes

Track form interactions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| filter interaction.name == "change"
| summarize
    change_count = count(),
    by: {frontend.name, ui_element.name, ui_element.value.type}
| sort change_count desc

```

**Use Case:** Analyze form field usage and abandonment.

## Feature Usage Analysis

Analyze custom feature areas:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| filter isNotNull(ui_element.features)
| summarize
    interaction_count = count(),
    unique_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {ui_element.features}
| sort interaction_count desc

```

**Use Case:** Measure feature adoption using `data-dt-features`.

## Real vs Synthetic Interactions

Filter genuine user interactions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| summarize
    real_interactions = countIf(dom_event.is_trusted == true),
    synthetic_interactions = countIf(dom_event.is_trusted == false),
    by: {interaction.name}

```

**Use Case:** Exclude automated testing from analytics.

## Interactions Before Errors

Find UX patterns leading to errors:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true or characteristics.has_error == true
| sort dt.rum.session.id, start_time
| fieldsAdd
    has_error = characteristics.has_error == true,
    element = ui_element.resolved_name
| summarize
    sequence = collectArray(
      record(
        time = start_time,
        type = if(has_error, "error", else: interaction.name),
        element = element
      )
    ),
    error_count = countIf(has_error == true),
    by: {dt.rum.session.id}
| filter error_count > 0
| limit 20

```

**Use Case:** Debug UX flows causing errors.

## Mobile Touch Analysis

Analyze touch interactions on mobile:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| filter in(interaction.name, "touch", "long_press", "drag", "zoom")
| summarize
    interaction_count = count(),
    by: {frontend.name, interaction.name, ui_element.component}
| sort interaction_count desc

```

**Use Case:** Optimize mobile gesture handling.

## Scroll Behavior

Analyze scroll patterns:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| filter interaction.name == "scroll"
| summarize
    scroll_events = count(),
    sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, page.url.path}
| sort scroll_events desc

```

**Use Case:** Identify pages with engagement vs bounce issues.

