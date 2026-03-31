# Troubleshooting Knowledge Base

This document is generated from `Catalog.json` and `Suggestions.json`.
Only suggestions with `IsPublic = 1` and `IsDeleted = 0` are included.

## Error Code DEC:109

### Error Description: The Netscaler ADC extension was unable to collect metric data during execution.

### Suggestions:

1. Verify the configured user is able to make calls to the Nitro API
2. Verify the user credentials are correct

## Error Code DEC:10E

### Error Description: Unable to fetch the property from the WMI Class

### Suggestions:

1. Verify if this counter should be present on the host, if it should be, further troubleshooting should be done regarding the counter. This article from the Microsoft community provides steps to further troubleshooting https://techcommunity.microsoft.com/blog/askperf/wmi-repository-corruption-or-not/375484

## Error Code DEC:110

### Error Description: Could not create a connection to the database using MongoClient.

### Suggestions:

1. Verify that a connection can be made using the MongoDB Shell (ex. `mongosh`). If successful, double-check that the same information has been entered into the monitoring configuration.

## Error Code DEC:111

### Error Description: Error gathering credentials for the additional processes in the monitoring configuration.

### Suggestions:

1. Ensure that the Credential ID being used in the monitoring configuration still exists and hasn't been overwritten with a different Credential Scope, or deleted.

## Error Code DEC:112

### Error Description: Error gathering credentials for the additional processes in the monitoring configuration.

### Suggestions:

1. Ensure that the Credential ID(s) being used in the monitoring configuration still exist and haven't been overwritten with a different Credential Scope or deleted.

## Error Code DEC:113

### Error Description: Could not create MongoClient or collect metadata for connection.

### Suggestions:

1. Verify that a connection can be made using the MongoDB Shell (ex. `mongosh`). If successful, double-check that the same information has been entered into the monitoring configuration.

## Error Code DEC:114

### Error Description: Error capturing metrics from MongoClient

### Suggestions:

1. Ensure that the uer querying the database has `serverStatus@admin`, `listDatabases` and `dbStats` permissions.

## Error Code DEC:115

### Error Description: Could not collect IP address.

### Suggestions:

1. Networking/firewall rules could prevent this connection from happening. Ensure that 8.8.8.8 is not blocklisted.

## Error Code DEC:118

### Error Description: Error with the `replSetGetStatus` command.

### Suggestions:

1. If the DB is apart of a replica set and this is still failing, check that the MongoDB user is using the built in 'Cluster Monitor Role' permissions.

## Error Code DEC:11C

### Error Description: Error gathering Server metadata.

### Suggestions:

1. If this error occurs, please reach out to support for further assistance.

## Error Code DEC:11E

### Error Description: Error reporting third party test results.

### Suggestions:

1. In the case of a 404 response, ensure that the REST API module is enabled on the ActiveGate running the extension. This is required for the extension to run properly
2. If the exception message relates to "Error making request", its likely an EEC issue. i.e. the EEC is not listening at the default port 9999 and is currently configured incorrectly. See https://docs.dynatrace.com/docs/ingest-from/extensions/advanced-configuration/eec-custom-configuration
3. Exception messages that include authorization issues  indicate that the API Token does not have the proper permissions

## Error Code DEC:120

### Error Description: The Databricks extension could not retrieve the Databricks/Spark configurations.

### Suggestions:

1. If the extension is failing to capture the Spark configuration, check to see if the /databricks/driver/logs/log4j-active.log file exists.

## Error Code DEC:122

### Error Description: The Databricks extension failed to capture metrics.

### Suggestions:

1. If it fails to capture Memory Metrics, make sure the free command is executable.

## Error Code DEC:12E

### Error Description: The TibcoEMS extension was unable to successfully run the underlying command using the tibemsadmin executable.

### Suggestions:

1. Verify if SSL connectivity should be enabled or disabled.
2. Verify that the user credentials supplied in the monitoring configuration are valid.

## Error Code DEC:133

### Error Description: The HAProxy extension failed to retrieve stats data from HAProxy with Socket mode.

### Suggestions:

1. For a further investigation, open an RFA and include the error message.

## Error Code DEC:136

### Error Description: Error connecting to Couchbase prometheus endpoint.

### Suggestions:

1. SSLError typically means that either the pasted certificate has been incorrectly formatted, or that the certificate is not valid for the hostname being connected to. Check that the certificate is correctly pasted and that it is valid for the hostname. If a path is supplied, check that user `dtuserag` has read access to the file.

## Error Code DEC:13E

### Error Description: Unexpected exception occurred while connecting to the IBM i host.

### Suggestions:

1. Verify hostname, username and password. If SSL is used, verify SSL configuration.

## Error Code DEC:13F

### Error Description: The IBM i extension was unable to detect installed unixODBC in Linux.

### Suggestions:

1. Check the command output of odbcinst -j and a file content /etc/odbcinst.ini or /etc/unixODBC/odbcinst.ini.

## Error Code DEC:140

### Error Description: The IBM i extension failed to retrieve the release or patch information.

### Suggestions:

1. Verify the user permissions. It is recommended that the user with the SECOFR profile be used. For more information, please refer to https://www.dynatrace.com/hub/detail/ibm-i.

## Error Code DEC:148

### Error Description: The Apigee extension was unable to successfully poll the underlying Apigee API

### Suggestions:

1. Verify that the authentication parameters are correct, whether username/password, Oauth, etc.
2. Have the customer verify their proxy filters are valid
3. As this is a standard API call, the error returned will include an HTTP status code, such as 401, 403, 404, etc., that will further point to the reason the call failed.

## Error Code DEC:149

### Error Description: Error connecting to cluster

### Suggestions:

1. Firewall rules may be blocking the connection to the endpoint, consider testing the connection from the ActiveGate via a `curl` command.

## Error Code DEC:14A

### Error Description: The Mulesoft Cloudhub extension failed to process private spaces.

### Suggestions:

1. Confirm that the private spaces exist for the organization. If it's not applicable, you can disable the collection of private spaces metrics in the extension configuration.

## Error Code DEC:14B

### Error Description: The MuleSoft CloudHub extension failed to process the endpoint.

### Suggestions:

1. If the error message shows a 401 error, verify that the MuleSoft Domain URL, MuleSoft Client ID, and Client Secret are correct.
2. If the GET organization endpoint returns a 404 error, verify that the MuleSoft Organization/Business Group ID is correct in the extension configuration.
3. If a proxy server is defined, verify that the URL and credentials are correct, and that the server is reachable.
4. If the scope is configured correctly, but a permission error still occurs, verify the scope by following the troubleshooting steps at https://dynatrace.stackenterprise.co/articles/18141.

## Error Code DEC:14C

### Error Description: The MuleSoft CloudHub extension failed to prepare the monitoring API.

### Suggestions:

1. If the bootdata endpoint returns a 403 error, something may have changed internally with the connected app. Try creating a new connected app as this is a bug/issue on the MuleSoft side.

## Error Code DEC:14D

### Error Description: The MuleSoft CloudHub extension failed to process CloudHub application information.

### Suggestions:

1. In the extension configuration, you can disable the collection of metrics for Cloudhub V1/V2 applications.
2. If it's failing to process v1 apps, ensure that CloudHub 1.0 is enabled. See https://docs.mulesoft.com/monitoring/configure-monitoring-cloudhub.

## Error Code DEC:14E

### Error Description: The RabbitMQ API returns an HTTP error.

### Suggestions:

1. Check the HTTP status code in the error message; for example, if it's a 401 error, verify the username and password. If it's a 5xx error, verify that the node is running.
2. Check the RabbitMQ logs to see if there are any errors.

## Error Code DEC:14F

### Error Description: The RabbitMQ extension failed to collect information about queues, nodes, or virtual hosts.

### Suggestions:

1. Check the RabbitMQ version. The tested versions are 3.13.7, 4.0.9, and 4.1.0.

## Error Code DEC:150

### Error Description: The RabbitMQ extension failed to connect to the RabbitMQ node.

### Suggestions:

1. Verify the Node URL and ensure it is reachable from OneAgent or ActiveGate.
2. Verify that the management plugin is enabled in the RabbitMQ broker.
3. Verify the node's status. Check the RabbitMQ logs to see if there are any errors.
4. Look for the warning log to see the detailed explanation of the error.

## Error Code DEC:152

### Error Description: Error collecting metrics from REST API

### Suggestions:

1. Ensure that the OnTap user in the extension monitoring configuration has proper permissions (the user with 'http' application access is assigned a rest-role with at least readonly access to the API paths listed in the extension documentation.)

## Error Code DEC:154

### Error Description: The Intersystems IRIS extension was unable to report the metric data or event back to the Dynatrace tenant.

### Suggestions:

1. Note which event was unable to be reported and open an RFA in the DXS project
2. Note the metric that cannot be reported and the returned error. Then open an RFA in the DXS project.

## Error Code DEC:155

### Error Description: Error reporting data for configured URL.

### Suggestions:

1. Ensure that the OnTap version used is compliant with the extension documentation. API endpoints may be different otherwise and the extension will not work properly.

## Error Code DEC:156

### Error Description: Error parsing and reporting volume.

### Suggestions:

1. Ensure that the user has API permissions for `/api/storage/volumes`.

## Error Code DEC:158

### Error Description: The IBM MQ extension was unable to successfully report a payload to the Dynatrace Settings API.

### Suggestions:

1. Note the returned status code and review the documentation for the Settings Object API endpoint https://docs.dynatrace.com/docs/discover-dynatrace/references/dynatrace-api/environment-api/settings/objects/post-object

## Error Code DEC:15A

### Error Description: The IBM MQ extension is unable to delete the noted temporary file used for the data processing

### Suggestions:

1. Verify the user running the extension process has filesystem permissions to the path in which the temporary file exists.

## Error Code DEC:15C

### Error Description: The IBM MQ extension was unable to connect to the queue manager.

### Suggestions:

1. Verify the provide credentials are valid and can login to the queue manager
2. Verify the permissions specified in the extension documentation have been assigned to the configured IBM MQ user

## Error Code DEC:15D

### Error Description: The IBM MQ extension was unable to read the extensionsmodulewatchdog.ini file to find the log directory on the ActiveGate

### Suggestions:

1. Verify the user running the extension process has read access to the file.

## Error Code DEC:160

### Error Description: Gathering data from - Load Balancer class/field failed.

### Suggestions:

1. Share the version of DataPower in use.

## Error Code DEC:162

### Error Description: Failed polling URL/Domain.

### Suggestions:

1. Aside from Authentication, check the version of DataPower being monitored, as well as ensuring that the XML Management Interface is enabled.

## Error Code DEC:163

### Error Description: Authentication failed/Access Denied for user.

### Suggestions:

1. Manually running a `curl` from the ActiveGate running the extension can verify proper Authentication independent of the extension. See https://www.ibm.com/docs/en/datapower-gateway/10.6.x?topic=interface-samples-that-use-rest-management#restinterfacesamples__eg4__title__1 for examples

## Error Code DEC:164

### Error Description: An error occurred while the Redis extension was collecting the data.

### Suggestions:

1. If the error is related to authentication, verify that the password is correct.
2. If the INFO command fails to execute, verify that the INFO command is enabled. If the commands have been renamed, ensure that the config file is accessible. The config file must be a full absolute path.

## Error Code DEC:165

### Error Description: The Redis extension failed to fetch the number of databases, or slowlog.

### Suggestions:

1. Check to see if the Redis version is supported by the extension.

## Error Code DEC:166

### Error Description: The Redis extension faied to extract data from INFO command response.

### Suggestions:

1. If the error message says "Error calculating hit ratio," then depending on how Redis is used, the cache may not be used, which makes it impossible to calculate the hit rate.

## Error Code DEC:167

### Error Description: The Salesforce extension failed to send metrics back to the Dynatrace API.

### Suggestions:

1. Verify the Dynatrace API token has the proper permissions assigned

## Error Code DEC:16E

### Error Description: Connectivity issue connecting to DataPower host.

### Suggestions:

1. To ensure that the endpoint is reacahable for a request, a `curl` can test connectivity.
```
curl -v -k --insecure --header "Content-Type: application/xml" --request POST --data 
'<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/">
<env:Body>
<dp:request xmlns:dp="http://www.datapower.com/schemas/management">
<dp:get-status class="DateTimeStatus"/></dp:request>
</env:Body>
</env:Envelope>'
-u ENTER_USER:ENTER_PASSWORD https://ENTER_IP:5550/service/mgmt/current'
```

## Error Code DEC:170

### Error Description: The CloudFlare extension failed to collect metrics.

### Suggestions:

1. Please confirm your CloudFlare account type. Some metrics cannot be collected depending on the account type.
2. Verify that the account ID is correct. The error message "Invalid account identifier" or "Invalid object identifier" could indicate an incorrect account ID.

## Error Code DEC:173

### Error Description: The SFTP Synthetic extension was unable to connect to the SFTP server.

### Suggestions:

1. Verify that the connection settings (hostname, port, username, password/key) are correct.

## Error Code DEC:174

### Error Description: The SFTP extension was unable to read the contents of the remote directory.

### Suggestions:

1. Ensure that the user configured in the monitoring configuration has sufficient permissions to access the remote directory.

## Error Code DEC:177

### Error Description: The SFTP extension failed to PUT the local file onto the SFTP server.

### Suggestions:

1. Check that the user credentials used for the SFTP connection have the necessary permissions to upload files to the target directory.

## Error Code DEC:178

### Error Description: The SFTP server did not process the uploaded file within the expected time limit.

### Suggestions:

1. Verify the SFTP is reachable.

## Error Code DEC:179

### Error Description: The SFTP extension failed to report the synthetic test result to the Dynatrace API.

### Suggestions:

1. Verify the API token specified in the monitoring configuration has the correct `ExternalSyntheticIntegration` scope assigned.
2. Attempt a manual 3rd party synthetic API call using the same API token.

## Error Code DEC:17A

### Error Description: The SFTP extension failed to create the underlying SFTP client.

### Suggestions:

1. Ensure the SSH key configured in the monitoring configuration is valid for connecting to the SFTP server

## Error Code DEC:17D

### Error Description: DhcpScopeMetrics: Exception calling "Get" : "Access denied "

### Suggestions:

1. When setting up the Active Directory Python (v5+) extension, the user must allow the extension to run with elevated privileges by adding this line to the OneAgent extensionuser.conf file:
   `elevated_privileges_extensions=[com.dynatrace.extension.active-directory-python-unabridged:*]`

## Error Code DEC:17E

### Error Description: Problem getting performance metrics from Dell API for FEDirector: Bad or unexpected response from the storage volume backend API: Error GET Array. The status code received is 403 and the message is {'message':'<Array Name> does not have authorisation on System 000120003618 as role Admin, StorageAdmin, PerfMonitor'}

### Suggestions:

1. The user provided in the monitoring configuration needs to have the PerfMonitor role assigned to it. This role allows the user to perform GET and POST requests to PowerMax performance API endpoints.

## Error Code DEC:17F

### Error Description: Error dispatching SWbemLocator: (-2147352567, 'Exception occurred.', (0, 'SWbemLocator', 'Invalid namespace ', None, 0, -2147217394), None)

### Suggestions:

1. The Invalid namespace error is often shown when the WMI classes that are trying to be queried are added to the host when a Windows role is installed. For example, if this is occurring on a WMI call to the root\MSCluster namespace then the host does not have the Failover clustering role installed. Either disable the Cluster Shared Volume feature sets or install the Failover clustering role.

## Error Code DEC:180

### Error Description: Connection test failed even after attempting reconnection.

### Suggestions:

1. Check that the user configured can actually run commands on the configured host (Can they run `echo 1`). Ideally try to run the ssh from the ActiveGate host to mimic the extension connection as closely as possible.

## Error Code DEC:181

### Error Description: Error connecting to remote host.

### Suggestions:

1. On Linux ActiveGate, run `sudo -u dtuserag ssh -vvv user@host 'echo test'`
2. If the endpoint configuration is using keys for authentication, ensure that they are included in the test ssh commands.
3. From a Windows ActiveGate try `psexec -u "nt authority\local service" -i ssh -vvv user@host 'echo test'` (if psexec is not available, its ok, just run it as the logged in user)

## Error Code DEC:186

### Error Description: Error running command on host.

### Suggestions:

1. A `custom PATH` can be set in the monitoring configuration for the endpoint to ensure the command can be found.
2. To check if The command exists, try running the command with its full path (e.g. `/usr/bin/yourcommand`).

## Error Code DEC:187

### Error Description: The trace being run by the Traceroute extension failed to reach its destination.

### Suggestions:

1. Verify each device along the expected traceroute is configured to respond to ICMP packets.

## Error Code DEC:189

### Error Description: The Forgerock Identity Cloud extension failed to reach the health URL.

### Suggestions:

1. Verify if the Forgerock Identity Cloud service is up and operational.

## Error Code DEC:18A

### Error Description: The Forgerock Identity Cloud extension failed to collect the page of logs from the API.

### Suggestions:

1. Contact Dynatrace support for further assistance.

## Error Code DEC:18C

### Error Description: The Forgerock Identity Cloud extension failed to read the cached timestamp for log ingestion from the noted Forgerock source.

### Suggestions:

1. Collect a support archive from the AG running the extension, and open an RFA in the DXS project.

## Error Code DEC:191

### Error Description: The PHP-FPM extension failed to access the status page.

### Suggestions:

1. Make sure your IP is included in the allow directive in the configuration,
2. Check web server configuration and firewall settings.
3. Review php-fpm error logs and web server logs for clues about misconfigurations or permission issues.

## Error Code DEC:192

### Error Description: The PHP-FPM extension failed to retrieve metrics from the status page.

### Suggestions:

1. Older PHP or PHP-FPM versions may not support all metrics. Check the documentation for version-specific supported metrics.
2. Try accessing the status page directly and see if the metrics are returned.

## Error Code DEC:193

### Error Description: The ISAM extension failed to access Verify Access REST API

### Suggestions:

1. Check the network connectivity between ActiveGate and the Verify Access REST API. Ensure that the API endpoint is reachable and that there are no firewall rules blocking access.

## Error Code DEC:194

### Error Description: The ISAM extension failed to extract metrics from Verify Access REST API.

### Suggestions:

1. Please collect the support archive and open an RFA to the DXS project.

## Error Code DEC:197

### Error Description: The Harbor extension failed to collect artifacts via the API.

### Suggestions:

1. Make sure the proxy address, username, and password are correct.

## Error Code DEC:198

### Error Description: The Harbor extension failed to ingest the security event.

### Suggestions:

1. Verify that the Dynatrace security events endpoint is configured correctly.
2. Ensure that the Dynatrace access token is correct and has the appropriate scope.

## Error Code DEC:19A

### Error Description: The FortiGate extension failed to ping the FortiGate device.

### Suggestions:

1. Check the FortiGate interface settings to confirm it is configured to respond to ping
2. Ensure there are no firewall rules blocking traffic from the ActiveGate to the FortiGate device.

## Error Code DEC:19B

### Error Description: The FortiGate extension failed to access the FortiGate REST API.

### Suggestions:

1. If a proxy is configured, ensure the proxy settings are correct.
2. Enable debugging on FortiGate and review the REST API Events logs for detailed error information.
3. If the API returns a 401 error, check that the access token or user credentials are valid.
4. If the API returns a 403 error, check that the user has sufficient permissions to access the required resources.

## Error Code DEC:19C

### Error Description: /proc/uptime doesn't return the expected data.

### Suggestions:

1. If it seems like it is a permissions issue, get an `ls -la /proc/uptime` to make sure the permissions are set properly.

## Error Code DEC:19E

### Error Description: The Salesforce extension failed to send a business events to Dynatrace via the Dynatrace API

### Suggestions:

1. Verify that the `bizevents.ingest` scope is assigned to the provided API token
2. Verify that the API token provided in the monitoring configuration is valid
3. If the API token is valid and the needed scope is present, collect a support archive and open an RFA in the DXS project.

## Error Code DEC:19F

### Error Description: The Salesforce extension cannot ingest RUM sessions due to the Beacon Forwarder module being disabled on the ActiveGate

### Suggestions:

1. Enable the Beacon Forwarder module as described in the documentation https://docs.dynatrace.com/docs/shortlink/sgw-configure#bf_mod

## Error Code DEC:1A0

### Error Description: The Salesforce extension failed to authenticate against Salesforce

### Suggestions:

1. Verify that the credentials provided in the monitoring configuration are valid

## Error Code DEC:1A1

### Error Description: The Salesforce extension failed to track the callback for the topic

### Suggestions:

1. Collect a support archive and open an RFA in the DXS project.

## Error Code DEC:1A2

### Error Description: The Salesforce extension failed to subscribe to the topic

### Suggestions:

1. If the returned error is a permissions error, verify that the credentials configured for the extension have the proper permissions
2. For an unknown error, collect a support archive and open an RFA in the DXS project

## Error Code DEC:1A3

### Error Description: The Salesforce extension failed to parse the cron schedule for the SOQL query

### Suggestions:

1. Verify the cron pattern is valid

## Error Code DEC:1A6

### Error Description: The Salesforce extension failed to make a http request

### Suggestions:

1. The log should include the status code of the failed request to provide further information on the issue. i.e. 401 Unauthorized -> Invalid credentials, 403 Forbidden -> Missing permissions, etc.

## Error Code DEC:1A7

### Error Description: The Salesforce extension failed to read the custom.properties file on the ActiveGate

### Suggestions:

1. Verify that dtuserag has at least read permissions to the custom.properties file and each directory in the path.

## Error Code DEC:1A8

### Error Description: The python openkit library failed to evict beacons from the cache

### Suggestions:

1. An unknown error has occurred when attempting to delete beacons from the beacon cache, collect a support archive and open a github issue for the openkit library https://github.com/dynatrace-extensions/dynatrace-openkit-python/issues

## Error Code DEC:1A9

### Error Description: The openkit python library failed to initialize

### Suggestions:

1. If the beacon forwarder module is enabled and the url is confirmed valid and reachable, collect a support archive and open a github issue https://github.com/dynatrace-extensions/dynatrace-openkit-python/issues
2. Verify the beacon forwarder module is enabled on the ActiveGate
3. Verify the provided beacon forwarder URL is valid and reachable

## Error Code DEC:1AA

### Error Description: The openkit python library failed to decode the beacon data

### Suggestions:

1. Collect a support archive from the ActiveGate running openkit and open a github issue https://github.com/dynatrace-extensions/dynatrace-openkit-python/issues

## Error Code DEC:1AB

### Error Description: Error encountered when retrieving host assets.

### Suggestions:

1. Check logs for indicator of whether it is an issue with the request or parsing the response

## Error Code DEC:1AD

### Error Description: Validation error. Fastcheck error. Dynatrace API Token need to be provided to be able to import Tags into Dynatrace

### Suggestions:

1. Check the Extension configuration settings whether token provided there is a valid token

## Error Code DEC:1AE

### Error Description: Dynatrace API Token need to be provided to be able to import Tags into Dynatrace. Tag import is disabled until API Token is provided

### Suggestions:

1. Check the Extension configuration settings whether token provided there is a valid token


## Error Code DEC:1AF

### Error Description: Fastcheck error : test connection to Dynatrace Tag API is failed

### Suggestions:

1. Check Network connectivity or API Token rights

## Error Code DEC:1B0

### Error Description: Fastcheck error : test connection to Alicloud API is failed

### Suggestions:

1. Check Network connectivity or credentials

## Error Code DEC:1B1

### Error Description: Server exception during Alicloud instance fetch

### Suggestions:

1. Check error details

## Error Code DEC:1B2

### Error Description: Client exception during Alicloud instance fetch

### Suggestions:

1. Check error details

## Error Code DEC:1B3

### Error Description: Exception during Alicloud data fetch

### Suggestions:

1. Check error details

## Error Code DEC:1B4

### Error Description: Can't determine AG URL from extensions.conf

### Suggestions:

1. Check ActiveGate extensions.conf

## Error Code DEC:1B5

### Error Description: Can't determine the AG configuration directory path

### Suggestions:

1. Check ActiveGate internal folders

## Error Code DEC:1B6

### Error Description: Invalid token in configuration

### Suggestions:

1. Recreate an access token with right scopes

## Error Code DEC:1B7

### Error Description: Token is missing scope

### Suggestions:

1. Recreate an access token with right scopes

## Error Code DEC:1B8

### Error Description: Nutanix API rate limit has been hit

### Suggestions:

1. Set the collection frequency parameter in configuration to some higher value

## Error Code DEC:1B9

### Error Description: OCI API rate limit has been hit.

### Suggestions:

1. Set the collection frequency parameter in configuration to some higher value.

## Error Code DEC:1BA

### Error Description: Dynatrace APIs return 404 error

### Suggestions:

1. Open ruxitagentproc.conf file on OneAgent running the extension.
   Identify line starting with "serverAddress", identify the address starting with a * on the same line. That is the ActiveGate address currently used by the OA.
   Verify whether the restInterface property is set to true in the custom.properties file of the AG identified on previous step. If it is set to false or unset, please adjust, then restart the AG and restart the extension (in this order). If the property is already set to true, contact Moviri support.

## Error Code DEC:1BF

### Error Description: A 401 (unauthorized) response was returned when trying to read the Qualys activity logs. 

### Suggestions:

1. Verify that the configured user has the required permissions as documented.

## Error Code DEC:1C4

### Error Description: No host assets were returned from Qualys.

### Suggestions:

1. This can indicate and issue with the configured user's permissions. Specifically, you should check in the Qualys Vulnerability Management module that the user has Asset Groups visible (ideally all of them). 

## Error Code DEC:1C6

### Error Description: An Unauthorized response was returned when trying to obtain a JWT for use in collecting activity logs.

### Suggestions:

1. Double check the authentication configuration and that the right POD URL was configured.

## Error Code DEC:1C8

### Error Description: Nutanix API is responding with status 500 - Internal Server Error

### Suggestions:

1. Open a ticket to Nutanix Support.

## Error Code DEC:1CB

### Error Description: Extension is not running with elevated privileges

### Suggestions:

1. Add the following line to the extensionuser.conf file in the OneAgent config directory. elevated_privileges_extensions=[<extension name>:*]
   For example: elevated_privileges_extensions=[com.dynatrace.extension.active-directory-python-unabridged:*]

## Error Code DEC:1CD

### Error Description: connection Error

### Suggestions:

1. make sure no other process using this port
2. make sure that port is open
3. make sure you are on version xxx or above

## Error Code DEC:1CE

### Error Description: The URL provided in the monitoring configuration is invalid

### Suggestions:

1. If the returned error states the hostname or IP is missing, verify that there is a hostname or IP address is the URL
2. If the returned error state that there is a path, remove the path from the URL

## Error Code DEC:1CF

### Error Description: API rate limit reached'. Skipping this request because the next data collection cycle is imminent. Metrics based on this response will not be reported.

### Suggestions:

1. Increase the data collection interval in the configuration to reduce request frequency and avoid hitting the rate limit.
   Increase the per-connection API rate limit in the configuration but do not exceed the limit configured on the monitored system.

## Error Code DEC:1D0

### Error Description: Asynchronous data collection timed out.

### Suggestions:

1. Verify that all configured REST API endpoints are reachable.
   If the API rate limit is being exceeded, increase the data collection interval in the configuration to reduce request frequency. You can also increase the per-connection API rate limit in the configuration, but do not exceed the limit set on the monitored system.

## Error Code DEC:1D1

### Error Description: Failed to deserialize JSON response

### Suggestions:

1. Verify that the extension supports the monitored system's version.
   Reconfigure the extension to use DEBUG log level and enable verbose logging. Open a support ticket. Include the extension log (support archive) with the ticket.

## Error Code DEC:1D2

### Error Description: REST query failed or returned an unexpected response. Metrics based on this query response will not be reported.

### Suggestions:

1. Verify that all configured REST API endpoints are reachable. 
   Verify that the extension supports the monitored system's version.

## Error Code DEC:1D3

### Error Description: No available initialized REST client to query data. Metrics based on this request will not be reported.

### Suggestions:

1. Verify that all configured REST API endpoints are reachable.

## Error Code DEC:1D4

### Error Description: REST client is not initialized.

### Suggestions:

1. Verify that the affected configured REST API endpoint is reachable.

## Error Code DEC:1D5

### Error Description: REST client HTTPError.

### Suggestions:

1. Verify that the affected REST API endpoint is reachable and accessible.


## Error Code DEC:1D6

### Error Description: REST client SSLError

### Suggestions:

1. If the monitored system's REST API endpoint uses a self-signed certificate, set the, set the 'Check SSL Certificate' connection property to false. 

## Error Code DEC:1D7

### Error Description: REST client Authentication failed

### Suggestions:

1. Verify that the correct username and password are specified in the configuration.
   Ensure that the extension has the necessary permissions to access the API.


## Error Code DEC:1D8

### Error Description: REST client ProxyError

### Suggestions:

1. Verify the proxy settings in the configuration.

## Error Code DEC:1D9

### Error Description: Unexpected Exception in method.

### Suggestions:

1. Reconfigure the extension to use DEBUG log level and enable verbose logging. Open a support ticket. Include the extension log (support archive) with the ticket.

## Error Code DEC:9F

### Error Description: The user account running the extension doesn't have permission to read this Scheduled Task folder.

### Suggestions:

1. Give the `NT AUTHORITY\LocalService` account permission to read this folder

## Error Code DEC:A1

### Error Description: File not found.

### Suggestions:

1. In case of permission errors, the `NT AUTHORITY\LocalService` account must be given permission to read this file.
2. Check the extension configuration. Verify that the task name is correct and that the task path starts with "\\" and does not contain "C:\\Windows\\...". The task name will become the name of the file searched. The path will be automatically appended to `C:\Windows\System32\Tasks` which is the default location for scheduled task files.
3. In case of decoding errors, ensure the file has valid `utf-16` content and does not contain any illegal characters.
4. In case of XML errors, ensure the task file has a valid XML structure and does not contain any illegal characters.

## Error Code DEC:A2

### Error Description: WMI query failed

### Suggestions:

1. Ensure the WMI service is running on the Windows machine. Try running the WMI query manually, for example,
   using powershell's `gwmi` command like `gwmi -query "query-from-error-message"`.

## Error Code DEC:A8

### Error Description: Failed to fetch events from Akamai

### Suggestions:

1. Update the extension to version at least 1.0.9 (com.dynatrace.extension.akamai-siem-1.0.9)

## Error Code DEC:B0

### Error Description: JSON response contained unexpected data. Unable to collect query metrics.

### Suggestions:

1. Open a support ticket and attach log output. Response will need to be examined.

## Error Code DEC:C4

### Error Description: The DynaKube is configured for Istio on a cluster where Istio is not installed.

### Suggestions:

1. Make sure you are deploying the DynaKube to the correct Kubernetes cluster.
2. Remove or set `.spec.enableIstio` from your DynaKube
3. Install Istio on your Kubernetes cluster.

## Error Code DEC:C5

### Error Description: The token secret does not contain an API token or a PaaS token.

### Suggestions:

1. Check your token secret if it contains either an `apiToken` or an `paasToken` entry.

## Error Code DEC:C6

### Error Description: Failed to ingest security events from Dynatrace extension.

### Suggestions:

1. Double-check that the connection details provided in the monitoring configuration are correct.
2. A retry should happen in the next run, but if needed restart the extension to ensure no data is lost.

## Error Code DEC:C7

### Error Description: Error fetching details from URL for Control-M

### Suggestions:

1. If this is happening to one specific request only and the rest reach the API successfully, ensure that the URL you find in the log line is correct by comparing it directly with the customer's API endpoint.

## Error Code DEC:D0

### Error Description: VMware: Error with Dynatrace API

### Suggestions:

1. Make sure that the API token has entities.read & entities.write scope
2. Make sure you are above v3.14.9

## Error Code DEC:D4

### Error Description: Failed to get data from NVIDIA BCM API

### Suggestions:

1. Turn on the `Debug` flag in the configuration and check that what the "Api call to..." debug log is the correct data from the API.

## Error Code DEC:D6

### Error Description: Unable to resolve IP address

### Suggestions:

1. Make sure you are on version 3.6.8 or above.
2. Verify that there is a DNS A or AAAA record for the hostname in the DNS provider's records
3. Verify that there is an entry for the hostname in the hosts file

## Error Code DEC:D7

### Error Description: No Snyk organizations found or organizations found do not match the selected organizations.

### Suggestions:

1. Ensure that your service account has the right permissions to see the organizations you are trying to monitor.

## Error Code DEC:E6

### Error Description: A timeout was encountered while the SSL Certificate Monitoring extension was attempting to connect to the specified port on the specified host to collect the SSL certificate.

### Suggestions:

1. Modify the timeout duration within the monitoring configuration to allow the extension more time to wait for the certificate before timing out. As the request being made by the extension is lightweight, the timeout duration should ideally be around 10 seconds or below.
2. Review network firewall rules to ensure that the ActiveGate or OneAgent the extension is running on is whitelisted to access the specified port on the specified host.

## Error Code DEC:E8

### Error Description: The SSL Certificate Monitoring extension encountered an error while attempting to collect the certificate for the specified port binding.

### Suggestions:

1. If the returned error is "Deprecation warning", the connection to the port failed due to an unsupported version of TLS. The application running on the specified port needs to be reviewed and modified to utilize a supported version of TLS.
2. If the returned error is "General exception", the connection to the port failed due to an unexpected issue and the returned error details need to be researched further.
3. If the returned error is "OpenSSL Error", the connection to the port failed due to an issue with OpenSSL. This can occur when the application listening on the specified port is not expecting an SSL connection and the port should be added as an exception in the monitoring configuration to prevent further errors.

## Error Code DEC:F1

### Error Description: The certificate monitored by the SSL Certificate Monitoring extension contains more than 50 fields, which violates the limit of dimensions allowed.

### Suggestions:

1. If this error is returned by the SSL Certificate Monitoring extension, open a support ticket for further investigation.

## Error Code DEC:F8

### Error Description: The Filesystem Monitoring extension was unable to assume the configured user when attempting to execute a check.

### Suggestions:

1. In Windows, verify that the user account has permission to logon locally and is granted logon type 2
2. Verify the configured user account is not locked.

## Error Code DEC:F9

### Error Description: The Filesystem Monitoring extension is unable to access the configured directory or files.

### Suggestions:

1. Verify the user account is not locked.
2. Verify the user has the permissions to read and execute all directories in the path. If not using the option to run as another user, the default Windows user is LOCAL SERVICE and the default Linux user is dtuser.

## Error Code DEC:FB

### Error Description: The Filesystem Monitoring extension encountered an error while making a request to Azure's API.

### Suggestions:

1. Verify the Azure key is valid.
2. If these pieces are verified, a support ticket should be opened for further investigation.
