/**
 * Detection script for customer-authored EF1 ("DT Plugins") installations.
 *
 * Runs inside the Dynatrace JS runtime via `dtctl exec function -f`, where a
 * relative fetch is authenticated by the runtime -- no token handling here.
 *
 * Uses a raw relative fetch rather than a typed SDK client. A typed client
 * does exist -- `getPlugins` (scope `legacy-plugins:configs:read`) -- but it
 * ships in a private package that the external customers this skill targets
 * cannot install. The relative
 * fetch below needs no package install and works identically for customers
 * and DT support alike.
 *
 * Read-only: GETs classic Config v1 only (uploaded plugin packages, not
 * runtime state -- a plugin appearing here means it was uploaded, not
 * necessarily that it is actively running).
 *
 * Verified live against a real tenant (33 plugins, 2 customer-authored): the
 * endpoint returns a flat `{ extensions: [...], totalResults }` shape, each
 * entry `{ id, name, type }` -- not the `remotePlugins`/`plugins`/`jmxv1`
 * grouping this script originally assumed (that shape does not exist on this
 * endpoint; assuming it made every scan silently report zero, regardless of
 * what was actually installed). `type` is the datasource kind
 * (`JMX`/`ONEAGENT`/`ACTIVEGATE`), not a type ID -- `id` is the field
 * carrying the `custom.*`/`dynatrace.*` prefix used to classify
 * customer-authored vs built-in.
 *
 * Scope: customer-authored EF1 plugins only. Built-in plugins (namespaced
 * `dynatrace.*`) are explicitly out of scope for this reference, pending a
 * follow-up epic. The classification rule below (`id` prefixed `custom.*`)
 * is provisional -- the endpoint's `isCustom` flag is planned but not yet
 * shipped; once it lands, prefer it over this prefix heuristic.
 *
 * Pagination: the endpoint accepts a `page-key` query param, but its own
 * docs are inconsistent about which response field carries the next-page
 * cursor -- prose says `nextPageKey`, the response schema example says
 * `nextPageToken`. Not verified live (the one live tenant checked had 33
 * plugins, returned in a single page with neither field present), so this
 * checks both rather than assuming one.
 */

const BASE_URL = '/platform-reserved/classic-config/v1/plugins';
const CUSTOM_PREFIX = 'custom.';

interface PluginStub {
  id: string;
  name?: string;
  type?: string;
}

interface PluginsResponse {
  extensions?: PluginStub[];
  totalResults?: number;
  nextPageKey?: string;
  nextPageToken?: string;
}

interface Finding {
  id: string;
  name: string;
  /** Datasource kind from the endpoint's `type` field, e.g. `JMX`, `ONEAGENT` (Python), `ACTIVEGATE`. */
  kind: string;
}

export default async function () {
  const all: Finding[] = [];
  let pageKey: string | undefined;

  do {
    const response = await fetchPlugins(pageKey);
    for (const stub of response.extensions ?? []) {
      all.push({ id: stub.id, name: stub.name ?? '<unnamed>', kind: stub.type ?? '<unknown>' });
    }
    pageKey = response.nextPageKey ?? response.nextPageToken;
  } while (pageKey);

  const custom = all.filter((finding) => isCustomId(finding.id));

  return {
    scanned: all.length,
    custom: custom.length,
    entries: custom,
  };
}

function isCustomId(id: string): boolean {
  return id.startsWith(CUSTOM_PREFIX);
}

async function fetchPlugins(pageKey?: string): Promise<PluginsResponse> {
  const url = pageKey ? `${BASE_URL}?page-key=${encodeURIComponent(pageKey)}` : BASE_URL;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`listing plugins failed: ${res.status} ${await res.text()}`);
  }
  return (await res.json()) as PluginsResponse;
}
