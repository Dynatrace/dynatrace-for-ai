# String Matching Functions

Reference for `matchesValue`, `matchesPhrase`, `matchesPattern`, and `in()` — the main functions for string and array pattern matching in DQL.

---

## `matchesValue()`

`matchesValue` is the primary function for pattern matching against string and array fields.

**Wildcard semantics** (`*` is supported anywhere in the pattern):

| Pattern | Meaning |
|---------|---------|
| `"exact"` | Exact match (case-insensitive by default) |
| `"prefix*"` | Starts with — **case-insensitive** (unlike `startsWith()`) |
| `"*suffix"` | Ends with — **case-insensitive** (unlike `endsWith()`) |
| `"*contains*"` | Substring — **case-insensitive** (unlike `contains()`, which is case-sensitive by default) |
| `"in*fix"` | Mid-string wildcard — matches any string starting with "in" and ending with "fix" |

**Notes:**
- The wildcard character is `*` by default and can be changed via the `wildcard` parameter: `matchesValue(field, "pattern", wildcard: "?")`.
- The second parameter must be a **constant or array literal** — a field reference is a runtime error.

**Array support** — both parameters accept arrays, eliminating `iAny`:

```dql-snippet
// Array field in first param: no iAny or [] needed
| filter matchesValue(process.command_args, "--pool")

// Array literal {} in second param: replaces a chain of OR conditions
| filter matchesValue(process.command_args, {"--pool", "--algo", "--randomx-*", "stratum+tcp://*", "*monero*"})

// Both combined: replaces iAny(matchesValue(arr[], "x") OR matchesValue(arr[], "y"))
| filter matchesValue(process.command_args, {"x", "y*", "*z*"})

// Replaces: contains(f, "a") OR contains(f, "b") OR contains(f, "c") on the same field
// Note: this is only a readability win when multiple contains() calls share the same field
| filter matchesValue(process.command_line, {"*curl*", "*wget*", "*nc*"})
```

**Case sensitivity**: `matchesValue` is **case-insensitive by default**. To enforce case: `matchesValue(field, "Pattern", caseSensitive: true)`. This also replaces `lower()` workarounds:

```dql-snippet
// WRONG — lower() + iAny + in() is verbose and fragile
| filter iAny(in(lower(process.command_args[]), array("xmrig", "ccminer")))

// RIGHT — matchesValue is case-insensitive by default
| filter matchesValue(process.command_args, {"xmrig", "ccminer"})
```

---

## `matchesPhrase()`

`matchesPhrase` tokenizes the input string and matches **whole words** (word-boundary aware). Use it instead of `contains()` when matching short or common tokens where substring hits would cause false positives.

**Optional parameters**: `caseSensitive` (default `false`) enables case-sensitive phrase matching; `wildcard` lets you specify a custom wildcard character for the phrase pattern.

**Word-boundary caveat:** punctuation characters (e.g. `-`) are themselves word boundaries. `matchesPhrase(f, "-value")` returns `true` for `"test-value"` because the `-` acts as a boundary before "value". Phrase patterns starting or ending with punctuation can match mid-string.

```dql-snippet
// contains() fires on "pipenv", "pipeline", "piped"
| filter contains(process.command_line, "pip")

// matchesPhrase() matches only the whole word "pip"
| filter matchesPhrase(process.command_line, "pip")
```

**Array support**: the **first** parameter accepts an array field — no `iAny` or `[]` needed. The **second** parameter must be a **static string literal** (array unwrapping causes a runtime error):

```dql-snippet
// WRONG — iAny wrapper is redundant when first param is an array field
| filter iAny(matchesPhrase(process.command_args[], "pip"))

// RIGHT — matchesPhrase iterates the array natively
| filter matchesPhrase(process.command_args, "pip")

// WRONG — runtime error: second param does not accept arrays
| filter matchesPhrase(process.command_line, array("-e", "-c")[])

// RIGHT — OR the phrases individually
| filter matchesPhrase(process.command_line, "-e") OR matchesPhrase(process.command_line, "-c")
```

---

## `matchesPattern()` — regex matching

`matchesPattern(field, regex)` matches a string field against a regular expression. Unlike `matchesValue` and `matchesPhrase`, **neither parameter accepts an array** — both must be scalar strings. To iterate over an array field, use `iAny` with `[]`:

```dql-snippet
// WRONG — matchesPattern does not accept an array field directly
| filter matchesPattern(process.command_args, ".*--pool.*")

// RIGHT — use iAny + [] to iterate
| filter iAny(matchesPattern(process.command_args[], ".*--pool.*"))
```

---

## `in()` — set membership and array overlap

`in()` tests whether a value (or any element of an array) appears in a set.

```dql-snippet
// Scalar field — replaces field == "a" OR field == "b" OR field == "c"
| filter in(audit.action, array("PutObject", "DeleteObject", "GetObject"))

// Array field — true if any element of the array matches
| filter in(process.command_args, array("-e", "-c"))

// Array overlap — true if the two arrays share any element
| filter in(process.command_args, process.command_args_other)
```

Syntax variants for the haystack:

```dql-snippet
in(field, {"a", "b", "c"})            // set literal
in(field, array("a", "b", "c"))        // array() constructor
in(field, "a", "b", "c"))              // simplified: extra params treated as haystack
```

---

## Quick reference

| Goal | Verbose (avoid) | Idiomatic DQL |
|------|----------------|---------------|
| Field equals one of N values | `f == "a" OR f == "b"` | `in(f, array("a","b"))` |
| Array field contains one of N values | `iAny(f[] == "a" OR f[] == "b")` | `in(f, array("a","b"))` |
| Many substring checks on same field (3+) | `contains(f,"a") OR contains(f,"b") OR ...` | `matchesValue(f, {"*a*", "*b*", ...})` ¹ |
| Array field matches any of N patterns | `iAny(matchesValue(f[], "a") OR ...)` | `matchesValue(f, {"a", "b*"})` |
| Array field contains whole-word token | `iAny(contains(f[], "pip"))` | `matchesPhrase(f, "pip")` |
| Case-insensitive array match | `iAny(in(lower(f[]), array("a","b")))` | `matchesValue(f, {"a","b"}, caseSensitive: false)` |

> ¹ `matchesValue` is case-insensitive by default. If the original `contains()` calls relied on case-sensitive matching, add `caseSensitive: true` to preserve it.
