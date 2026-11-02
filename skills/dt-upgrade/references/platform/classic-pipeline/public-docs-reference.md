# Public Documentation Links

Dynatrace public documentation relevant to the classic pipeline upgrade workflow. Fetch the linked page when you need full syntax or examples for a specific item.

## Migrate Classic Processing Rules to OpenPipeline

**URL:** https://docs.dynatrace.com/docs/platform/openpipeline/migration-classic-pipeline

Official Dynatrace migration guide. Key content already incorporated into this skill:
- Breaking changes table (data types, field name case sensitivity, query language, technology parsers) — inlined in [translation-issue-fixes/misc.md](translation-issue-fixes/misc.md)
- Five-step migration process — covered by the main workflow in [classic-pipeline.md](classic-pipeline.md)
- Technology bundle processors — inlined in [technology-bundles.md](technology-bundles.md)

Only fetch this page if you need information not covered by the files above — for example, Dynatrace version requirements, license prerequisites, or permission scopes not listed in classic-pipeline.md.

## Classic log processing overview

**URL:** https://docs.dynatrace.com/docs/analyze-explore-automate/logs/lma-classic-log-processing

Key facts (no need to fetch for these):
- Processing occurs before storage.
- Matchers evaluate against the **original** record — not against fields modified by preceding rules.
- Rules execute top-to-bottom; each rule's output feeds into the next rule's processing (but not its matcher).
- Built-in rules are prefixed `[Built-in]`; they cannot be modified, only disabled or copied.

## Classic log processing functions

**URL:** https://docs.dynatrace.com/docs/analyze-explore-automate/logs/lma-classic-log-processing/lma-log-processing-functions

Fetch this page when rewriting a processor placeholder in Step 5 and you need the full syntax or an example for a specific function. The page is organized by category:

| Category | Functions |
|---|---|
| Bitwise | AND (`&`), OR (`\|`), XOR (`^`), LEFT_SHIFT (`<<`), RIGHT_SHIFT (`>>`), ZERO_FILL_RIGHT_SHIFT (`>>>`), BITWISE_NOT (`~`), BIT_COUNT |
| Boolean | AND, OR, XOR, NOT |
| Casting | BOOLEAN, BYTES, DOUBLE, DURATION, INTEGER / INT, IPADDR / IPV4 / IPV6, LONG, STRING, TIMESTAMP / T, TO_NULL, TUPLE, VARIANT / VAR, VARIANT_ARRAY / VAR_ARR, VARIANT_OBJECT, EMPTY_ARRAY, NULL_ARRAY, NULL_TUPLE |
| Comparison | EQUAL (`=`), NOT_EQUAL (`!=` / `<>`), GREATER (`>`), LESS (`<`), GREATER_OR_EQUAL (`>=`), LESS_OR_EQUAL (`<=`), IS NULL, IS NOT NULL, IN / NOT IN, FALSE_OR_NULL, TRUE_OR_NULL |
| Composite-Data | VARIANT_FIELD_SELECT, TUPLE_FIELD_SELECT, ARRAY_AVG, ARRAY_COUNT, ARRAY_FIRST, ARRAY_LAST, ARRAY_MAX, ARRAY_MIN, ARRAY_JOIN, ARRAY_SORT, ARRAY_SUM, ARRAY_IDX, ARRAY_SELECT, ARRAY_LEN, ARRAY_REMOVE_NULLS, ARRAY_REVERSE, REMOVE_NULLS, ARRAY_UNIQ, SPREAD |
| Cryptographic | MD5, SHA1 |
| Date-Time | Bracket operators (`[+/-/% N unit]`), DAY, DAY_OF_WEEK, DAY_OF_YEAR, HOUR, MINUTE, MONTH, NOW, SECOND, STR_SEC_TO_TIME, STR_TO_TIME, SYS_TIME, TIME_ADD, TIME_ADD_DAY/WEEK/MONTH/YEAR, TIME_SUB, TIME_SUB_DAY/WEEK/MONTH/YEAR, TIME_SUBMOD, TIME_SUBMOD_DAY/WEEK/MONTH/YEAR, TIME_TO_STR, TO_STR_SEC, YEAR, WEEK_OF_YEAR |
| Flow Control | IF, IF_THEN, IF_THEN_ELSE |
| Math | `+`, `-`, `*`, `/`, `%`, ABS, ADD, ACOS, ASIN, ATAN, ATAN2, CBRT, CEIL, COS, COSH, DEGREES, DIVIDE, E, EXP, EXPM1, FLOOR, FLOORDIV, FLOORMOD, GETEXPONENT, HYPOT, IEEEREMAINDER, LOG, LOG1P, LOG10, MODULO, MULTIPLY, NEXTAFTER, NEXTDOWN, NEXTUP, PI, POWER, RADIANS, RANDOM, RINT, ROUND, SCALB, SIGNUM, SIN, SINH, SQRT, SUBMOD, SUBTRACT, TAN, TANH, TOHEXSTRING, ULP |
| Network | DSLICE, IP_TRUNC, IS_IPV4, IS_IPV6, PARSEURI |
| String | `+` / `\|\|` (concat), BASE16_DECODE / UNHEX, BASE16_ENCODE / HEX, BASE64_DECODE, BASE64_DECODE_STRING, BASE64_ENCODE, CONCAT, CHARAT, CONTAINS, ENDS, INDEXOF, LDIST, LOWER, MATCHES, PARSE, PRINTF, PUNCT, REPLACE_STRING, REPLACE_PATTERN, SH_ENTROPY, SPLIT, STRLEN, STARTS, SUBSTR, TRIM, UNESCAPE / DEESCAPE, URLDECODE, URLENCODE, HTMLUNESCAPE, UPPER |
| Other | COALESCE, COLUMN, FLAG, HASH64, REMOVE_CHILD, SIZE, SIZEOF, TYPE |

## OpenPipeline technology bundle processors

Knowledge inlined in [technology-bundles.md](technology-bundles.md).

**URL:** https://docs.dynatrace.com/docs/analyze-explore-automate/logs/lma-log-processing/lma-tech-bundles-processors
