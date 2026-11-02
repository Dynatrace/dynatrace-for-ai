# Translating capture expressions

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md). A
classic capture expression becomes an **ordered list of capturing steps**, and three shapes account
for most of the work. Read this while classifying and translating (step 3) — the row each property
lands in is in [Classifying properties](classifying-properties.md).

## A JSON value inside a variable

Classic `JAVA_SCRIPT_VARIABLE` capture of `localStorage.userInformation.$username` becomes four
ordered capturing steps — one property accessor per dotted segment, and a JSON parse where the `$`
was:

```
PROPERTY_ACCESSOR   localStorage
PROPERTY_ACCESSOR   userInformation
JSON_PARSER
PROPERTY_ACCESSOR   username
```

Four rules in one example: do **not** strip a leading `window.` (classic resolves the first segment
against `window`, so `window.foo` means `window.window.foo`); a `JSON_PARSER` step carries no
capture value, and the write is rejected if you set one; a `JSON_PARSER` cannot be the first step;
and classic parsed JSON only when the literal `$name` property was absent, where Grail parses
unconditionally and fails on non-string input — so flag it.

## A meta tag

Classic captured meta tags through a selector. The translation is always **two** steps:

```
QUERY_SELECTOR         meta[name="basket-total"]
DOM_ATTRIBUTE_ACCESSOR content
```

A selector-only chain captures nothing, so the attribute accessor is mandatory — and the same is
true of a classic `CSS_SELECTOR` with no `@attribute`, which relied on a text-content fallback
Grail does not have. Report those rather than emitting a bare selector.

**Never emit a single quote inside a selector.** The configuration travels in a single-quoted HTML
attribute carrying raw JSON, so `meta[name='x']` truncates it and the agent fails to initialize.
Classic configurations use single quotes routinely — normalize every `'` to `"`.

## A query-string property, in two parts

Classic `QUERY_STRING` capture of a single parameter migrates, but not in one piece. The capture
rule reads the whole query string:

```
PROPERTY_ACCESSOR   search
```

and an OpenPipeline processor on a **user-events** pipeline splits out the parameter and writes it
back under the same key. `plan` generates that processor; it reads the parameter as classic did —
name matched ignoring case, value taken as it appears in the URL, not decoded, and of repeated
parameters the first non-empty one. Report two changes per property: the property carries the
whole query string until the pipeline is in place, and on a page whose route is in the URL
fragment (`/#/page?x=1`) classic also read a query string after the `#`, which the browser does
not count as the query string — the property stays empty on such pages.

