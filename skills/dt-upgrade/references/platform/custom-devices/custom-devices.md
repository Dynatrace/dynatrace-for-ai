# Custom Devices (Entity API)

<!-- Jira: none -->

**Gen3 replacement**: Smartscape API

**Phase 2 required**: no

## What changes

The classic entity API is deprecated. Custom devices created through the entity API will no longer be supported in Phase 3.

## Customer actions

- Customer must rebuild their integration to send data to the new Smartscape API instead

## References

- [`custom-devices-synthetic.md`](custom-devices-synthetic.md) — SNMP custom device monitoring via the SNMP extension; migration of ICMP/TCP `MULTI_PROTOCOL` monitors with `targetFilter` to `NETWORK_AVAILABILITY` monitors with static host targeting (dtctl/Settings API) or `MULTI_PROTOCOL` monitors with explicit `targetList` (Environment API v2)
