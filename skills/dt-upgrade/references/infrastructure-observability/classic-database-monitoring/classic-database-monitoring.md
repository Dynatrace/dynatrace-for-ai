# Classic Database Monitoring

<!-- Jira: none -->

**Gen3 replacement**: Database Observability

**Phase 2 required**: no

## What changes

Multiple generations of database monitoring in Dynatrace are being standardized on the
new Database Observability, which provides comprehensive monitoring inside your databases.

### DB Insights

DB Insights was a much older database monitoring technology for monitoring Oracle with Dynatrace. It was deprecated in 2022 and was no longer possible to use after ActiveGate version 1.301 in 2024. You can check for instances of it still running using the following DQL query:

```dql
fetch dt.entity.custom_device
| fieldsAdd entity.name, entity.type, icon
| filter icon[primaryIconType] == "oracledatabase"
```

These should be replaced with the `com.dynatrace.extension.sql-oracle` extension. It is not possible to copy over credentials or other configuration information; however, you can assist the user in creating configurations for the extension. From the above DQL result, the `entity.name` appears to be a connect string or TNS name.

### Database extensions

Database extensions are the current method of collecting database health and performance data, which is made available in the Databases app. However, with Phase 3, specific versions or newer are required to ensure compatibility.

Ensure these minimum versions are met, if the extension is installed:

| Database | Extension                              | Minimum version |
|----------|----------------------------------------|-----------------|
| Oracle   | com.dynatrace.extension.sql-oracle     | 4.1.1           |
| MS SQL   | com.dynatrace.extension.sql-server     | 4.1.3           |
| Postgres | com.dynatrace.extension.postgres       | 3.2.4           |
| MySQL    | com.dynatrace.extension.mysql          | 3.1.2           |
| MariaDB  | com.dynatrace.extension.mariadb        | 2.0.14          |
| Informix | com.dynatrace.extension.sql-informix   | 3.1.0           |
| MongoDB  | com.dynatrace.mongo-db-tls             | 3.2.2           |
| SAP HANA | com.dynatrace.extension.sql-sap-hana   | 3.1.2           |
| DB2      | com.dynatrace.extension.sql-db2        | 3.1.0           |
| Sybase   | com.dynatrace.extension.sybase-ase     | 2.0.0           |
| Cassandra| com.dynatrace.extension.jmx-cassandra  | 1.3.0           |
| Snowflake| com.dynatrace.extension.sql-snowflake  | 3.2.0           |

You can use `dtctl get extensions` to check versions. The user can upgrade extensions via the Extensions app.

Additionally, these local Microsoft SQL extensions are deprecated:
- `com.dynatrace.extension.sql-server.wmi`
- `com.dynatrace.extension.python.wmi.mssql`

Customers should upgrade to the main Microsoft SQL extension: `com.dynatrace.extension.sql-server`

## Licensing

Licensing for the newest database monitoring extensions uses a new DPS capability: `DATABASE_MONITORING`.
You can check whether it's included in the user's license using:
```dtctl
dtctl get license-settings DATABASE_MONITORING
```

If this shows `false`, the user should contact their Dynatrace account representative to add `DATABASE_MONITORING` to their DPS contract.

## Customer actions

- **DB Insights**: Migrate any Oracle DB Insights instances to `com.dynatrace.extension.sql-oracle` — credentials cannot be copied, so create new configurations using the connect string or TNS name from the DQL results
- **Database extensions**: Upgrade all installed database extensions to the minimum versions listed above
- **Deprecated SQL extensions**: Migrate from `com.dynatrace.extension.sql-server.wmi` / `com.dynatrace.extension.python.wmi.mssql` to `com.dynatrace.extension.sql-server`
- **Licensing**: Verify `DATABASE_MONITORING` is in the DPS contract; if not, engage the Dynatrace account representative
