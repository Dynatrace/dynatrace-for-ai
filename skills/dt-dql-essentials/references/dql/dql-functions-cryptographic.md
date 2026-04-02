# DQL Functions — Cryptographic

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_cryptographic string function_

## `hashCrc32`
Returns a CRC32 hash for the given expression.
`hashCrc32(expression)`
  `expression` (Binary|String) — The string expression that will be hashed.
  → String

## `hashMd5`
Returns a MD5 hash for the given expression.
`hashMd5(expression)`
  `expression` (Binary|String) — The string expression that will be hashed.
  → String

## `hashSha1`
Returns a SHA-1 hash for the given expression.
`hashSha1(expression)`
  `expression` (Binary|String) — The string expression that will be hashed.
  → String

## `hashSha256`
Returns a SHA-256 hash for the given expression.
`hashSha256(expression)`
  `expression` (Binary|String) — The string expression that will be hashed.
  → String

## `hashSha512`
Returns a SHA-512 hash for the given expression.
`hashSha512(expression)`
  `expression` (Binary|String) — The string expression that will be hashed.
  → String

## `hashXxHash32`
Returns a xxHash32 hash for the given expression.
`hashXxHash32(expression)`
  `expression` (Binary|String) — The expression that is considered for the hash function.
  → String

## `hashXxHash64`
Returns a xxHash64 hash for the given expression.
`hashXxHash64(expression)`
  `expression` (Binary|String) — The expression that is considered for the hash function.
  → String
