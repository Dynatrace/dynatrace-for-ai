# Further reading

Published Dynatrace documentation behind [Classic Action and Session Property
Capturing](../classic-action-session-properties.md). Every limit, signature and field name in this
reference traces to one of these.

- [Capture event and session properties for web frontends](https://docs.dynatrace.com/docs/observe/digital-experience/rum/web-frontends/additional-configuration/event-and-session-properties)
  — the capture UI, the JavaScript API, the allow list, the aggregation recipe and the limits.
- [Capture event and session properties for mobile frontends](https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/mobile-frontends/additional-configuration/event-and-session-properties)
- [Identify individual users for session analysis in RUM Classic](https://docs.dynatrace.com/docs/observe/digital-experience/rum-classic/web-applications/additional-configuration/identify-individual-users-for-session-analysis)
  — the six classic tag sources, the 20-rule and 100-character limits, and the session rollup.
- [RUM data model](https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/concepts/data-model)
  — how a property reaches a session, including enrichment in OpenPipeline.
- [Semantic Dictionary — RUM](https://docs.dynatrace.com/docs/discover-dynatrace/references/semantic-dictionary/model/rum)
  — which fields exist on `user.events` and on `user.sessions`.
- [RUM JavaScript API reference](https://docs.dynatrace.com/javascriptapi/doc-latest/functions/API.dynatrace.sendEvent.html)
  — the signatures, the property types, `identifyUser`, and `VALID_KEY_REGEX` with the exact
  pattern.
- Custom events on mobile, with the code:
  [Android](https://docs.dynatrace.com/docs/observe/digital-experience/rum/mobile-frontends/android/id-08-custom-events)
  and [iOS](https://docs.dynatrace.com/docs/observe/digital-experience/rum/mobile-frontends/ios/id-08-custom-events)
  — `EventData` / `DTXEventData`, the modifier pair, and which fields a modifier may change.
- [OneAgent SDK for Android API reference](https://docs.dynatrace.com/javadoc/oneagent/android/agent/com/dynatrace/android/agent/Dynatrace.html)
  — the mobile signatures, the minimum version on each call, and the one-active-event rule for
  session properties.
- [Understand and manage consumption for Real User Monitoring](https://docs.dynatrace.com/docs/license/capabilities/real-user-synthetic-monitoring/real-user-monitoring)
  — the 20 included session properties, the per-session rate for the rest, and the double-billing
  protection during a migration.
