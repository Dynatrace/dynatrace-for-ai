# DQL Functions — String

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

## Table of Contents

[`concat`](#concat) · [`contains`](#contains) · [`decodeBase16ToBinary`](#decodebase16tobinary) · [`decodeBase16ToString`](#decodebase16tostring) · [`decodeBase64ToBinary`](#decodebase64tobinary) · [`decodeBase64ToString`](#decodebase64tostring) · [`decodeUrl`](#decodeurl) · [`encodeBase16`](#encodebase16) · [`encodeBase64`](#encodebase64) · [`encodeUrl`](#encodeurl) · [`endsWith`](#endswith) · [`escape`](#escape) · [`getCharacter`](#getcharacter) · [`indexOf`](#indexof) · [`lastIndexOf`](#lastindexof) · [`levenshteinDistance`](#levenshteindistance) · [`like`](#like) · [`lower`](#lower) · [`matchesPattern`](#matchespattern) · [`matchesPhrase`](#matchesphrase) · [`matchesRegex`](#matchesregex) · [`matchesValue`](#matchesvalue) · [`punctuation`](#punctuation) · [`replacePattern`](#replacepattern) · [`replaceString`](#replacestring) · [`splitByPattern`](#splitbypattern) · [`splitString`](#splitstring) · [`startsWith`](#startswith) · [`stringLength`](#stringlength) · [`substring`](#substring) · [`trim`](#trim) · [`unescape`](#unescape) · [`unescapeHtml`](#unescapehtml) · [`upper`](#upper)

_string function_

## `concat`
Concatenates the expressions into a single string.
`concat([delimiter ,] expression, …)`
  `delimiter:?` (String) — A constant string expression that is added between the concatenated expressions.  [default:""]
  `expression*` (Double|Long|String) — A numeric or string expressions that should be concatenated with others.
  → String

## `contains`
Searches the string expression for a substring. Returns `true` if the substring was found, `false` otherwise.
`contains(expression, substring [, caseSensitive])`
  `expression` (String) — The field or expression to check (the haystack).
  `substring` (String) — The substring that should be contained (the needle).
  `caseSensitive:?` (Boolean) — caseSensitive  [default:TRUE]
  → Boolean

## `decodeBase16ToBinary`
Decodes the given BASE16-string to a binary.
`decodeBase16ToBinary(expression)`
  `expression` (Binary|String) — The encoded string or binary that shall be decoded.
  → Binary

## `decodeBase16ToString`
Decodes the given BASE16-string to a string.
`decodeBase16ToString(expression)`
  `expression` (Binary|String) — The encoded string or binary that shall be decoded.
  → String

## `decodeBase64ToBinary`
Decodes the given BASE64-string to a binary.
`decodeBase64ToBinary(expression)`
  `expression` (Binary|String) — The encoded string or binary that shall be decoded.
  → Binary

## `decodeBase64ToString`
Decodes the given BASE64-string to a string.
`decodeBase64ToString(expression)`
  `expression` (Binary|String) — The encoded string or binary that shall be decoded.
  → String

## `decodeUrl`
Returns a decoded url string.
`decodeUrl(expression)`
  `expression` (String) — The string expression that will be decoded.
  → String

## `encodeBase16`
Encodes the given binary or string as BASE16-string.
`encodeBase16(expression)`
  `expression` (Binary|String) — The string or binary expression that shall be encoded.
  → String

## `encodeBase64`
Encodes the given binary or string as BASE64-string.
`encodeBase64(expression)`
  `expression` (Binary|String) — The string or binary expression that shall be encoded.
  → String

## `encodeUrl`
Returns an encoded url string.
`encodeUrl(expression)`
  `expression` (String) — The string expression that will be encoded.
  → String

## `endsWith`
Checks if a string expression ends with a suffix. Returns `true` if does, `false` otherwise.
`endsWith(expression, suffix [, caseSensitive])`
  `expression` (String) — The string expression that will be checked.
  `suffix` (String) — The suffix string with which the expression should end.
  `caseSensitive:?` (Boolean) — Whether the check should be done in a case-sensitive way.  [default:TRUE]
  → Boolean

## `escape`
Returns an escaped string.
`escape(expression)`
  `expression` (String) — The string expression that will be escaped.
  → String

## `getCharacter`
Returns the character at a given position from a string expression. Negative positions are counted from the end of the string.
`getCharacter(expression, position)`
  `expression` (String) — The string expression from which to get the character.
  `position` (Long) — The position at which to get the character (negative positions are counted from the end of the string).
  → String

## `indexOf`
Finds the index of the first occurrence of a substring in a string expression, starting a forward search from a given index. Returns -1, if the substring is not found.
`indexOf(expression, substring [, from])`
  `expression` (String) — The string expression in which the substring is searched for.
  `substring` (String) — The substring expression to search for in the expression.
  `from:?` (Long) — The index from which to start the forward search for the first occurrence of the substring within the expression. Negative values are counted from the end of the string.  [default:0]
  → Long

## `lastIndexOf`
Finds the index of the last occurrence of a substring in a string expression, starting a backward search from a given index. Returns -1, if the substring is not found.
`lastIndexOf(expression, substring [, from])`
  `expression` (String) — The string expression in which the substring is searched for.
  `substring` (String) — The substring expression to search for in the expression.
  `from:?` (Long) — The index from which to start the backward search for the last occurrence of the substring within the expression. Negative values are counted from the end of the string.  [default:9223372036854775807]
  → Long

## `levenshteinDistance`
Computes Levenshtein distance between two given strings.
`levenshteinDistance(firstExpression, secondExpression)`
  `firstExpression` (String) — The first string expression to compute the Levenshtein distance from.
  `secondExpression` (String) — The second string expression to compute the Levenshtein distance from.
  → Long

## `like`
Tests if a string expression matches a pattern. If the pattern doesn't contain percent signs then like() acts as == operator (equality check). A percent character in the pattern (%) matches any sequence of zero or more characters. An underscore in the pattern (_) matches a single character.
`like(expression, pattern)`
  `expression` (String) — The string expression that will be checked.
  `pattern` (String) — The matching pattern.
  → Boolean

## `lower`
Converts a string to lowercase.
`lower(expression)`
  `expression` (String) — The string expression to convert to lowercase.
  → String

## `matchesPattern`
Tests if a string expression matches the DPL pattern.
`matchesPattern(expression, pattern)`
  `expression` (String) — A field or string expression to test.
  `pattern` (—) — The matching pattern.
  → Boolean

## `matchesPhrase`
Matches a phrase against the input string expression using token matchers.
`matchesPhrase(expression, phrase [, caseSensitive])`
  `expression` (Array|String) — The expression (string or array of strings) that should be checked.
  `phrase` (String) — The phrase to search for.
  `caseSensitive:?` (Boolean) — Whether the match should be done case-sensitive (default: false).  [default:FALSE]
  `wildcard:?` (String) — A single character that will be used as wildcard (default: "*").  [default:"*"]
  → Boolean

## `matchesRegex` (deprecated)
Tests if a string expression matches a regular expression.
`matchesRegex(expression, pattern)`
  `expression` (String) — The string to check.
  `pattern` (String) — The applied regular expression pattern (has to match the whole string).
  → Boolean

## `matchesValue`
Matches a value against the input expression using token matchers.
`matchesValue([caseSensitive ,] expression, value, …)`
  `caseSensitive:?` (Boolean) — Whether the match should be done case-sensitive (default: false).  [default:FALSE]
  `wildcard:?` (String) — A single character that will be used as wildcard (default: "*").  [default:"*"]
  `expression` (Array|SmartscapeId|String) — The expression (string or array of strings) that should be checked.
  `value*` (Array|String) — The value to search for using patterns (supports an array of patterns or a list of patterns).
  → Boolean

## `punctuation`
Returns punctuation characters contained in given string.
`punctuation(expression [, count] [, withSpace])`
  `expression` (String) — The string expression of which to extract the punctuation characters.
  `count:?` (Long) — The maximum number of returned punctuation characters.  [default:32, min:0]
  `withSpace:?` (Boolean) — Whether space characters should be included.  [default:FALSE]
  → String

## `replacePattern`
Replaces each substring of a string that matches the DPL pattern with the given string.
`replacePattern(expression, pattern, replacement)`
  `expression` (String) — A field or string expression to replace.
  `pattern` (—) — The replacing pattern.
  `replacement` (String) — The string that should replace the found substrings.
  → String

## `replaceString`
Replaces each substring of a string with a given string.
`replaceString(expression, substring, replacement)`
  `expression` (String) — The field or expression where substrings should be replaced.
  `substring` (String) — The substring that should be replaced.
  `replacement` (String) — The string that should replace the found substrings.
  → String

## `splitByPattern`
Splits a string into an array at each occurrence of the DPL pattern.
`splitByPattern(expression, pattern)`
  `expression` (String) — A field or string expression to split.
  `pattern` (—) — The splitting pattern.
  → Array

## `splitString`
Splits a string at each occurrence of a pattern. If not found, returns an array with a single element that contains the full string. Splits into single-byte strings if the pattern is empty.
`splitString(expression, pattern)`
  `expression` (String) — The string expression to split up into an array.
  `pattern` (String) — The pattern to split the string expression at, or the empty string to split into one-byte strings.
  → Array

## `startsWith`
Checks if a string expression starts with a prefix. Returns `true` if does, `false` otherwise.
`startsWith(expression, prefix [, caseSensitive])`
  `expression` (String) — The string expression that will be checked.
  `prefix` (String) — The prefix string with which the expression should start.
  `caseSensitive:?` (Boolean) — Whether the check should be done in a case-sensitive way.  [default:TRUE]
  → Boolean

## `stringLength`
Returns number of UTF-16 code units in given string.
`stringLength(expression)`
  `expression` (String) — The string expression to get the number of UTF-16 code units for.
  → Long

## `substring`
Gets part of a string using a start index (inclusive) and an optional end index (exclusive).Negative indexes are relative to the last code unit. Indexes that are out-of-bounds are clamped at the string length for positive indexes, and at zero for negative indexes.Returns empty string in case of out-of-bounds indexes.Indexes are in UTF-16 code units and may not correspond to a single character.
`substring(expression [, from] [, to])`
  `expression` (String) — The string expression to get a substring of.
  `from:?` (Long) — Index of first code unit to include in sub-string, inclusive, relative to start of `expression` if positive, relative to end if negative. Clamped at string bounds.  [default:0]
  `to:?` (Long) — Index of last code unit to include in sub-string, exclusive, relative to start of `expression` if positive, relative to end if negative. Clamped at string bounds.  [default:9223372036854775807]
  → String

## `trim`
Returns given string without leading and trailing white-space.
`trim(expression)`
  `expression` (String) — The string expression to remove leading and trailing white-space from.
  → String

## `unescape`
Returns an unescaped string.
`unescape(expression)`
  `expression` (String) — The string expression that will be unescaped.
  → String

## `unescapeHtml`
Returns an unescaped html string.
`unescapeHtml(expression)`
  `expression` (String) — The string expression that will be unescaped.
  → String

## `upper`
Converts a string to uppercase.
`upper(expression)`
  `expression` (String) — The string expression to convert to uppercase.
  → String
