# DQL Functions — Network

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_network function_

## `ipIn`
Checks if an ip address matches with given ip addresses. Returns `true` if it does, `false` otherwise.
`ipIn(needle, haystack, …)`
  `needle` (Array|IpAddress|String) — The expression that will be compared with the given ip addresses
  `haystack*` (Array|IpAddress|String) — The ip addresses with which the expression should be compared
  → Boolean

## `ipIsLinkLocal`
Checks if a string or ip address expression is a link local ip address. Returns `true` if it is, `false` otherwise.
`ipIsLinkLocal(expression)`
  `expression` (IpAddress|String) — The string or ip address expression that will be checked.
  → Boolean

## `ipIsLoopback`
Checks if a string or ip address expression is a loopback ip address. Returns `true` if it is, `false` otherwise.
`ipIsLoopback(expression)`
  `expression` (IpAddress|String) — The string or ip address expression that will be checked.
  → Boolean

## `ipIsPrivate`
Checks if a string or ip address expression is a private ip address. Returns `true` if it is, `false` otherwise.
`ipIsPrivate(expression)`
  `expression` (IpAddress|String) — The string or ip address expression that will be checked.
  → Boolean

## `ipIsPublic`
Checks if a string or ip address expression is a public ip address. Returns `true` if it is, `false` otherwise.
`ipIsPublic(expression)`
  `expression` (IpAddress|String) — The string or ip address expression that will be checked.
  → Boolean

## `ipMask`
Returns an ip address where a given mask is applied
`ipMask(expression, maskBits [, ipv6MaskBits])`
  `expression` (IpAddress|String) — The string or ip address expression that will be masked.
  `maskBits` (Long) — The mask bits that should be applied to an ip address.  [min:0]
  `ipv6MaskBits:?` (Long) — The mask bits that should be applied to an ipv6 address.  [min:0]
  → IpAddress

## `isIp`
Checks if a string or ip address expression is an ip address. Returns `true` if it is, `false` otherwise.
`isIp(expression)`
  `expression` (IpAddress|String) — The string or ip address expression that will be checked.
  → Boolean

## `isIpV4`
Checks if a string or ip address expression is an ipv4 address. Returns `true` if it is, `false` otherwise.
`isIpV4(expression)`
  `expression` (IpAddress|String) — The string or ip address expression that will be checked.
  → Boolean

## `isIpV6`
Checks if a string or ip address expression is an ipv6 address. Returns `true` if it is, `false` otherwise.
`isIpV6(expression)`
  `expression` (IpAddress|String) — The string or ip address expression that will be checked.
  → Boolean
