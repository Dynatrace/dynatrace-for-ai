# Replacing the classic calls

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
The code changes step 3 lists and step 7 hands off. Every signature here is published.

| Classic call                                                   | Grail replacement                      | Published signature                                                                                                                                            |
|----------------------------------------------------------------|----------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `dtrum.addActionProperties()`, on an action the agent detected | `dynatrace.addEventModifier()`         | `addEventModifier(eventModifier: (jsonEvent: Readonly<JSONEvent>, eventContext?: EventContext) => JSONEvent): () => void` — it returns the unsubscriber        |
| `dtrum.addActionProperties()`, on an action you send yourself  | `dynatrace.sendEvent()`                | `sendEvent(fields: ApiCreatedEventPropertiesEvent, eventContext?: unknown): void`                                                                              |
| `dtrum.sendSessionProperties()`                                | `dynatrace.sendSessionPropertyEvent()` | `sendSessionPropertyEvent(fields: ApiCreatedSessionPropertiesEvent): void`                                                                                     |
| Action properties on a reported error                          | `dynatrace.sendExceptionEvent()`       | `sendExceptionEvent(error: Error, fields?: ApiCreatedEventPropertiesEvent): void` — ⚠ it is `undefined` unless the Error module is enabled, so guard the call |

`fields` is one flat object, and the **key carries its own namespace**: the two accepted shapes are
`event_properties.${string}` and `session_properties.${string}`, with `duration` and `start_time`
the only members that take no prefix. Values are string, number or boolean. `duration` is dropped
on a session-property event.

```javascript
// Attach a property to an action the agent detects for you. The modifier sees every event,
// so narrow it first, and return a new object rather than mutating the readonly one.
const stopModifying = dynatrace.addEventModifier(function (event) {
  if (event["event.type"] !== "click") {
    return event;
  }
  return { ...event, "event_properties.cart_total": 42 };
});

// Send the value yourself — event scope, then session scope.
dynatrace.sendEvent({ "event_properties.cart_total": 42 });
dynatrace.sendSessionPropertyEvent({ "session_properties.plan": "enterprise" });
```

On mobile the same three calls are published per platform, and Android has a generated API
reference of its own: `Dynatrace.sendEvent(EventData())` carrying
`.addEventProperty("event_properties.checkout_step", "payment_confirmed")`,
`Dynatrace.sendSessionPropertyEvent(SessionPropertyEventData())` carrying
`.addSessionProperty("session_properties.userId", "12345")`, and
`Dynatrace.addEventModifier(modifier)` / `removeEventModifier(modifier)` for an event the SDK
detected; iOS has the same shapes through `DTXEventData` and `addEventProperty:value:`. Four
differences from the web path: the **fully prefixed name goes in the call** — *"Any property
without this prefix will be dropped during validation"*; *"only one Session Property event may be
active for every session"*, so send it once, when the values are known; *"Any properties that are
not pre-configured will be discarded"*, so the configuration has to be applied before the release
ships; and a modifier may only touch `event_properties.*`, `session_properties.*` (on
session-property events), `url.full` and `exception.stack_trace`, with everything else read-only.
These calls arrived with the Gen3 SDK — **8.329**, and **8.343** for the variant that attaches
properties to a user action you create yourself — and none of them are supported on RUM Classic.
