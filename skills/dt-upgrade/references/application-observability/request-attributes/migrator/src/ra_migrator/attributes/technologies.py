"""The spellings one stored `serviceTechnology` can appear under, on either side of a read.

Vocabulary of the stored configuration rather than a property of a read, which is why it lives
here: the narrowing filter and the comparison behind it both accept the same set, and neither is
the thing that defines it.

Not a translation. Grail's `type:` segment carries the `KnownTechnologyDto` spelling - the very
string a Scope stores - so the stored name is always the first spelling and never a substitute
for it. The second one exists because `SOFTWARE_TECH_TYPE_EQUALS` dispatches on the **service's**
own technology: an untyped one is compared against the condition's `verbatimType`, which
`SimpleSoftwareTechFactory.ofType` sets to the `KNOWN_TECHNOLOGY` name, case-insensitively. So a
Scope naming `APACHE_KAFKA` selects the verbatim `KAFKA` services too.
"""

from __future__ import annotations

# The divergent assignments, and only those: everything the mapper spells the same way is the
# identity and carries no entry. Transcribed 2026-09-15 from the 249 `.assign(...)` lines of
# `shared/monitoredentities/src/main/java/com/compuware/apm/monitoredentities/api/dto/
# KnownTechnologyDtoMapper.java`, cross-checked against
# `ui/webui.model.shared/java/webui.model.angular/.../api/common/protocol/KnownTechnology.java` -
# the readable mirror of `KNOWN_TECHNOLOGY`, since the protobuf enum has no source in the
# checkout.
#
# The mapper's three `.assignDomainToCodomain(...)` lines are deliberately absent. They are alias
# DTO names, and a body POSTed with one is read back canonical because a GET converts the stored
# technology with the same `domainOf` - so a Scope this tool reads names one of the 249, never an
# alias.
_KNOWN_TECHNOLOGY_NAME = {
    "ACTIVE_MQ_ARTEMIS": "ARTEMIS",
    "AIX": "AIX_SYSTEM",
    "APACHE_CASSANDRA": "CASSANDRA",
    "APACHE_COUCH_DB": "COUCHDB",
    "APACHE_HTTP_SERVER": "APACHE_HTTPD",
    "APACHE_KAFKA": "KAFKA",
    "APACHE_STORM": "STORM",
    "APACHE_TOMCAT": "TOMCAT",
    "ASP_DOTNET": "ASP_NET",
    "ASP_DOTNET_CORE": "ASP_NET_CORE",
    "ASP_DOTNET_CORE_SIGNALR": "SIGNALR_CORE",
    "ASP_DOTNET_SIGNALR": "SIGNALR",
    "AWS_DYNAMO_DB": "DYNAMO_DB",
    "AWS_SQS": "AWS_SQS_CLIENT",
    "CLOUDFOUNDRY_BOSH": "BOSH",
    "DYNATRACE": "APMNG",
    "IBM_CICS_TRANSACTION_GATEWAY": "CTG",
    "IBM_IMS_CONNECT_REGION": "IBM_IMS_CONNECT",
    "IBM_IMS_CONTROL_REGION": "IBM_IMS_CONTROL",
    "IBM_IMS_MESSAGE_PROCESSING_REGION": "IBM_IMS_MPR",
    "IBM_MQ": "MQ_SERIES",
    "IBM_WEBSPHERE_APPLICATION_SERVER": "WEBSPHERE",
    "IBM_WEBSPHERE_LIBERTY": "WEBSPHERE_LIBERTY",
    # The DTO's own typo, which is the spelling the tenant's `type:` segment carries.
    "JAVA_HTTPURLCONNETION": "JAVA_HTTPURLCONNECTION",
    "MICROSOFT_SQL_SERVER": "MSSQL",
    "ORACLE_DATABASE": "ORACLE_DB",
    "ORACLE_WEBLOGIC": "WEBLOGIC",
    "POSTGRE_SQL": "POSTGRES",
    "POSTGRE_SQL_DOTNET_DATA_PROVIDER": "POSTGRE_DOTNET_DATA_PROVIDER",
    "RABBIT_MQ": "RABBITMQ",
    "SPARK": "APACHE_SPARK",
    "TIBCO_BUSINESS_WORKS": "TIBCO_BW",
    "VIRTUAL_MACHINE_KVM": "KVM",
    "VIRTUAL_MACHINE_QEMU": "QEMU",
    "WINDOWS_CONTAINERS": "WINC",
    "ZERO_MQ": "ZEROMQ",
}


def spellings_of(technology: str) -> tuple[str, ...]:
    """Every string a `type:` segment can equal for this condition, the stored one first.

    One string for the technologies the two enums spell alike, two for the rest. The stored name
    is always in the set: it is what Grail holds for every typed entry, so dropping it to catch
    the untyped ones would break the common case for the rare one.

    An unknown name is its own only spelling rather than an error. The table is a table of
    exceptions transcribed from a checkout, and a technology the cluster added since is still the
    string the segment carries.
    """
    other = _KNOWN_TECHNOLOGY_NAME.get(technology)
    return (technology,) if other is None else (technology, other)
