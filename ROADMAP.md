<h1 align="center">Taking Qoffee Hardware-Agnostic</h1>

Qoffee works with IBM Quantum today. This document provides a roadmap for adding AWS Braket and Azure Quantum.

Claims marked verified were read from the vendor's own API reference or from the SDK source it ships. 

## Contents

- [1. The problem](#1-the-problem)
- [2. IBM Quantum: the baseline](#2-ibm-quantum-the-baseline)
- [3. AWS Braket](#3-aws-braket)
- [4. Azure Quantum](#4-azure-quantum)
- [5. Side-by-side comparison](#5-side-by-side-comparison)
- [6. The fetch plan for each vendor](#6-the-fetch-plan-for-each-vendor)
- [7. Status vocabularies and normalisation](#7-status-vocabularies-and-normalisation)
- [8. Dependencies](#8-dependencies)
- [9. Credentials and permissions](#9-credentials-and-permissions)
- [10. References](#10-references)

## 1. The problem

Qoffee needs two separate things from a provider.

1. Discovery answers "which jobs am I responsible for?" It has to work for jobs of any age: a job queued on Monday and still queued on Thursday must be findable on Thursday without scanning history.
2. State answers "have I already told the user about this one?" Qoffee has no database, so state has to be written onto the job itself and read back on the next run.

The original IBM design covers both with job tags.

## 2. IBM Quantum: the baseline

Status: verified, implemented and running in production.

### Discovery

[`QiskitRuntimeService.jobs()`](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/qiskit-runtime-service):

```python
jobs(limit=10, skip=0, backend_name=None, pending=None, program_id=None,
     instance=None, job_tags=None, session_id=None,
     created_after=None, created_before=None, descending=True)
```

- `job_tags` filters on the server. A job matches only if it carries every tag given, so the filter is AND, not OR.
- `pending=True` returns QUEUED and RUNNING jobs; `pending=False` returns DONE, CANCELLED and ERROR.
- `created_after` and `created_before` are documented as local time, not UTC, so pass timezone-aware datetimes.
- `limit` defaults to 10. The default silently cut off discovery, which is why the code passes `limit=None`.

### State

State is kept in tags and changed with `job.update_tags()`.

### Tag scheme

`job_tags` matches exactly, so state can't live in the discovery tag: the job would become unfindable as soon as its state changed. Qoffee uses two tags:

```
qoffee              discovery, present for the whole life of tracking
qoffee@R            state; F:<epoch> for a reported failure
name:Bell Test 1    optional human label
qoffeed             applied once tracking ends
```

## 3. AWS Braket

### 3.1 What Braket calls a job

Braket uses "job" to mean a hybrid job: a managed container that runs a classical-quantum algorithm and submits many quantum tasks of its own. What Qiskit calls a job, Braket calls a quantum task.

```
Hybrid Job  (jobArn)
  ├── quantum task 1
  ├── quantum task 2
  └── ... N more
```

Calling `SearchJobs` instead of `SearchQuantumTasks` returns an empty list.

### 3.2 Braket's own search can't filter by tag

Verified from [`SearchQuantumTasksFilter`](https://docs.aws.amazon.com/braket/latest/APIReference/API_SearchQuantumTasksFilter.html):

| Field | Values |
|---|---|
| `name` | `quantumTaskArn`, `deviceArn`, `jobArn`, `status`, `createdAt` |
| `operator` | `LT`, `LTE`, `EQUAL`, `GT`, `GTE`, `BETWEEN` |
| `values` | 1 to 10 items |

Those are all the fields and operators there are. There is no tag filter and no `CONTAINS`.

In [`SearchQuantumTasks`](https://docs.aws.amazon.com/braket/latest/APIReference/API_SearchQuantumTasks.html) itself, `filters` is required but accepts 0 to 10 items, so an unfiltered listing is allowed. `maxResults` is 1 to 100, and paging uses `nextToken`.

Values inside one filter are OR'd, and separate filters are AND'd. So `quantumTaskArn EQUAL [arn1..arn10]` fetches ten specific tasks in one call, and adding a second `quantumTaskArn` filter narrows the result instead of widening it.

### 3.3 `QuantumTaskSummary` includes tags

Verified. The search response returns:

```json
{
  "createdAt": "...", "deviceArn": "...", "endedAt": "...",
  "outputS3Bucket": "...", "outputS3Directory": "...",
  "quantumTaskArn": "...", "shots": 0, "status": "...",
  "tags": { "string": "string" }
}
```

Because tags come back inline, filtering by tag on the client costs no extra API calls. The response also confirms that Braket tags are key/value maps, unlike the flat string lists IBM and Azure use.

`failureReason` is missing. It is only on [`GetQuantumTask`](https://docs.aws.amazon.com/braket/latest/APIReference/API_GetQuantumTask.html), so failure messages need one call per task. Qoffee makes that call only for tasks that failed, the same way the IBM adapter calls `error_message()` only on ERROR.

### 3.4 Hybrid jobs have different filters

Verified from [`SearchJobsFilter`](https://docs.aws.amazon.com/braket/latest/APIReference/API_SearchJobsFilter.html):

| Field | Operators | Notes |
|---|---|---|
| `jobArn` | `EQUAL` only | cannot be combined with other filters |
| `jobName` | `EQUAL`, `CONTAINS` | substring match |
| `deviceArn` | `EQUAL` only | device ARN or `local:braket/default` |
| `createdAt` | `EQUAL`, `GT`, `GTE`, `LT`, `LTE`, `BETWEEN` | RFC 3339; `BETWEEN` needs exactly two values |

Hybrid jobs have a name the user chooses, and it can be searched by substring. Quantum tasks have no name, because they are generated by the hundred and nobody names them one by one.

The difference runs both ways: jobs have `jobName` and `CONTAINS`, and tasks have `status` and `jobArn`, which jobs lack.

### 3.5 Discovery through the Resource Groups Tagging API

Braket discovery depends on this API.

[`GetResources`](https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/API_GetResources.html) returns every tagged or previously tagged resource in the given Region for the account. The same page says:

> All tagged resources, whether the tagging used the Resource Groups Tagging API
> or not, are returned by the `Get*` operation.

That covers resources tagged through a service's own tagging call, which is what Braket's `TagResource` is.

```json
{
  "ResourceTypeFilters": ["braket:quantum-task"],
  "TagFilters": [{"Key": "qoffee"}],
  "ResourcesPerPage": 100
}
```

`ResourceTypeFilters` uses the form `service[:resourceType]`, matching what appears in the resource's ARN. A Braket task ARN looks like `arn:aws:braket:<region>:<account>:quantum-task/<uuid>`.

The useful rule is how a filter with only a key behaves:

> If you don't specify a value for a key, the response returns all resources
> that are tagged with that key, with any or no value.

A filter on the key alone matches any value, so state can live in the tag value without breaking discovery. One tag does the job of IBM's two.

The response is a `ResourceTagMappingList` of `{ResourceARN, Tags[]}`. It holds ARNs and tags only, with no status, which is why fetching takes two steps.

`GetResources` doesn't return untagged resources, and a `PaginationToken` is valid for at most 15 minutes.

### 3.6 Quotas

Braket API ([service quotas](https://docs.aws.amazon.com/braket/latest/developerguide/braket-quotas.html)):

| Operation | Rate |
|---|---|
| `SearchQuantumTasks` | 5/sec, burst 50 |
| `GetQuantumTask` | 100/sec |

Tag Editor ([service quotas](https://docs.aws.amazon.com/tag-editor/latest/userguide/service-quotas.html)):

| Item | Limit |
|---|---|
| `GetResources` | 15 calls/sec |
| `TagResources` / `UntagResources` / `GetTagKeys` / `GetTagValues` | 5 calls/sec |
| Tags per resource | 50 user-defined |
| Tag key | 1 to 128 Unicode characters |
| Tag value | 0 to 256 Unicode characters |
| Allowed characters | letters, numbers, spaces, and `_ . : / = + - @` |

The tag index can be queried three times as often as Braket's own search: 15 calls a second against 5.

The allowed characters don't include braces, quotes or commas, so raw JSON can't go in a tag value. Use a delimited format instead. AWS also warns that individual services may set stricter limits than these general ones.

### 3.7 Regional fan-out

Braket resources are regional, and devices are spread across us-east-1, us-west-1, us-west-2 and eu-north-1. `GetResources` and `SearchQuantumTasks` both work per region, so every run has to query each region. A user whose devices are all in one region should narrow the configured list.

## 4. Azure Quantum

### 4.1 Jobs live on the data plane, not in ARM

This rules out copying the AWS approach. The workspace is the ARM resource, and jobs live inside it on the data plane:

```
https://{region}.quantum.azure.com
  /subscriptions/{sub}/resourceGroups/{rg}
  /providers/Microsoft.Quantum/workspaces/{ws}/jobs
  ?api-version=...
```

`Workspaces - Update Tags` is an ARM operation at `management.azure.com`. Azure Resource Graph and ARM tag queries index ARM resources, so they would find your workspaces and not your jobs. Azure has no equivalent of `GetResources` for jobs.

API versions seen in the reference are `2022-09-12-preview`, `2025-09-01-preview` and `2026-01-15-preview`, so this API is still changing.

### 4.2 The filter vocabulary, from the SDK source

Verified by reading `_create_filter` in [`azure-quantum-python`](https://github.com/microsoft/azure-quantum-python) (`azure/quantum/workspace.py`). This list is authoritative because it is the code Microsoft ships:

```
startswith(Name, '<prefix>')
ItemType     eq '<...>'
JobType      eq '<...>'
ProviderId   eq '<...>'
Target       eq '<...>'
State        eq '<...>'
CreationTime ge <iso-date>
CreationTime le <iso-date>
```

`_create_orderby` checks against the same set: `Name`, `ItemType`, `JobType`, `ProviderId`, `Target`, `State`, `CreationTime`.

Neither tags nor metadata can be filtered. The CLI confirms this by omission: [`az quantum job list`](https://learn.microsoft.com/en-us/cli/azure/quantum/job) exposes every other filterable field, and not tags.

That list has two traps:

- The OData property is `State`, not `Status`, even though the JSON response field is `status`.
- The SDK truncates `created_after` to a date (`created_after.date().isoformat()`), so time filtering through `list_jobs()` works by day at best. The raw REST `filter` parameter would take a full timestamp if you build it by hand.

### 4.3 Finding jobs by name

Three facts together make the name usable as an index:

1. `--job-name` is documented as a prefix search, which emits `startswith(Name, ...)` on the server.
2. `az quantum job update --job-name` can change the name after submission.
3. The REST schema says the name need not be unique and is used for display only.

Microsoft treats the name as a display field with no meaning of its own, so using it as a marker fits its intended use.

A prefix survives changes to the rest of the name, so one field can carry both discovery and state:

```
qoffee/Q|Bell Test 1
qoffee/R|Bell Test 1
qoffee/F:1755835200|Bell Test 1
```

Search with `startswith(Name, 'qoffee/')`, parse the middle part, and restore the original label for display. Tags and `metadata` stay free for the user.

### 4.4 What the list response returns

Verified from [`Jobs - List`](https://learn.microsoft.com/en-us/rest/api/azurequantum/dataplane/jobs/list). `JobDetails` includes:

| Field | Notes |
|---|---|
| `id` | GUID |
| `name` | display only, not unique |
| `status` | see the enum in section 7 |
| `errorData` | structured: `code`, `message`, `details[]`, `innererror`, `target` |
| `tags` | `string[]`, a flat list like IBM's |
| `metadata` | free-form object for client-specific information |
| `creationTime`, `beginExecutionTime`, `endExecutionTime`, `cancellationTime`, `lastUpdatedTime` | |
| `sessionId` | grouping |
| `itemType` | `"Job"` or `"Session"` |
| `providerId`, `target`, `jobType` | |
| `costEstimate`, `usage` | only Azure has these |

Status, error and the state marker all arrive in one paginated call. That's better than Braket, which needs three calls, and on par with IBM.

`itemType` matters because list responses can include sessions as well as jobs. The adapter has to filter them out or it will treat a session as a job.

`costEstimate` is worth using too. Neither IBM nor Braket reports what a job cost, so an Azure notification could include it.

### 4.5 Pagination and limits

`PagedJobDetails` is `{value: JobDetails[], nextLink: uri}`. The generated client declares `top` and `skip` as `Optional[int] = None`, with no validation and no ceiling. The `list_jobs_paginated` wrapper defaults to `top=100`, which is the SDK's choice and not a service limit. `ItemPaged` follows `nextLink` on its own.

The data plane has no published rate limit or `top` maximum. The generated client's `error_map` handles 401, 404, 409 and 304 but leaves out 429, so throttling shows up as a generic `HttpResponseError` at that layer, and honouring `Retry-After` is left to the retry policy in `azure-core`. Qoffee should treat 429 explicitly as a transient `ProviderError`.

### 4.6 Quotas

From [Azure Quantum quotas](https://learn.microsoft.com/en-us/azure/quantum/azure-quantum-quotas): the concurrent job quota is the number of jobs that can be queued in a workspace at one time. Quotas are set per provider, scoped to either a workspace or a subscription, and renew monthly or never (infinite).

`workspace.get_quotas()` returns the limit, usage, scope and period. Azure is the only one of the three that reports your quota through its API.

On the Learn & Develop SKU you can't request a quota increase; you have to switch to Performance at Scale.

This quota limits submission, not queries. It also caps the tracked set: a workspace can only have N jobs queued at once, so discovery never returns more than N active jobs plus the recently finished ones.

### 4.7 Authentication

Azure supports two paths: `AzureEntraAuth` (OAuth2, scope `https://quantum.microsoft.com/.default`) or an `x-ms-quantum-api-key` header.

The API key suits Qoffee much better because it is one secret, like the IBM token. Entra means registering an app, granting it workspace access and storing three secrets. How API keys are issued is not confirmed yet; see the test plan.

## 5. Side-by-side comparison

| | IBM Quantum | AWS Braket | Azure Quantum |
|---|---|---|---|
| Discovery | `job_tags` exact match | `GetResources` tag index | `startswith(Name, ...)` |
| Discovery cost | O(tracked) | O(tracked) | O(tracked) |
| Time horizon | none | none | none |
| State marker | tags (list) | tags (key/value) | job name |
| Marker mutable | yes, overwrites | yes, merges | yes |
| Status in list | yes | yes | yes |
| Error in list | no (`error_message()`) | no (`GetQuantumTask`) | yes (`errorData`) |
| Tags in list | yes | yes | yes |
| Page size | 200 (REST) / `limit=None` | 100, fixed | undocumented |
| Paging | `limit`/`skip` | `nextToken` | `nextLink` |
| Rate limit | undocumented | 5/s search, 15/s tagging | undocumented |
| Fan-out | instance | 4 regions | workspace |
| Push available | no | EventBridge | no |
| Retention | 3 years | undocumented | undocumented |

All three discover jobs in O(tracked) time with one confirmed mechanism each, and none of them needs an external database.

## 6. The fetch plan for each vendor

### IBM: one call

```python
service.jobs(job_tags=["qoffee"], pending=None, limit=None)
```

This returns tracked jobs with status, tags and metadata. Each failed job needs one more `error_message()` call.

### AWS Braket: two calls per region

```
Step 1  tagging.get_resources(
            ResourceTypeFilters=["braket:quantum-task"],
            TagFilters=[{"Key": "qoffee"}],
            ResourcesPerPage=100)
        → ARNs + state from tag values, paginate on PaginationToken

Step 2  braket.search_quantum_tasks(
            filters=[{"name": "quantumTaskArn",
                      "operator": "EQUAL",
                      "values": <batch of ≤10 ARNs>}],
            maxResults=100)
        → status, device, timestamps, tags

Step 3  braket.get_quantum_task(quantumTaskArn=arn)
        → failureReason, only for tasks in FAILED
```

The filter rules force the batch size of 10 in step 2: values inside one filter are OR'd, and a second filter would narrow the results instead of adding more.

For n tracked tasks in one region, a run costs `ceil(n/100)` tagging calls at 15 a second, `ceil(n/10)` search calls at 5 a second, and one call per failed task at 100 a second.

Writing state: `braket.tag_resource()` merges tags instead of replacing them, so the user's own tags survive without being passed back in. This is the one place Braket is easier to work with than IBM.

### Azure: one call per workspace

```
GET .../jobs?$filter=startswith(Name,'qoffee/')&$top=100
```

This returns status, `errorData`, `tags`, `metadata` and the state encoded in the name, in one paginated response. Filter on `itemType == "Job"` to leave out sessions.

Writing state: `Jobs - Patch` (JSON Patch, `replace` on `/name`), or `az quantum job update --job-name`.

### The shared interface

Every adapter implements the same two protocols from `providers/base.py`:

```python
class JobSource(Protocol):
    def fetch_tracked(self) -> list[TrackedJob]: ...

class TrackingStore(Protocol):
    def set_state(self, job, state) -> None: ...
    def resolve(self, job) -> None: ...
```

Nothing outside `providers/` knows what a tag, an ARN or a job name is, and none of this work touches the policy layer, the renderer or the notification channels.

## 7. Status vocabularies and normalisation

| Qoffee | IBM | Braket | Azure |
|---|---|---|---|
| `INITIALIZING` | `INITIALIZING`, `VALIDATING` | `CREATED` | `Waiting` |
| `QUEUED` | `QUEUED` | `QUEUED` | `Queued` |
| `RUNNING` | `RUNNING` | `RUNNING`, `CANCELLING` | `Executing`, `Finishing`, `CancellationRequested`, `Cancelling` |
| `DONE` | `DONE` | `COMPLETED` | `Succeeded` |
| `ERROR` | `ERROR` | `FAILED` | `Failed` |
| `CANCELLED` | `CANCELLED` | `CANCELLED` | `Cancelled` |
| `UNKNOWN` | anything else | anything else | anything else |

Things to watch for:

- Braket `CANCELLING` and Azure `Cancelling` and `CancellationRequested` are not terminal. Mapping them to `CANCELLED` would resolve a job that is still winding down, so map them to an active state.
- Azure `Finishing` is not terminal either, despite the name.
- Azure has both `Completed` and `Succeeded`, described as "the job completed" and "the job completed with success". Which one Azure actually sends on success is unverified; see the test plan.
- Azure's status enum has ten values, and the CLI examples show only a few. All ten must be mapped, or the missing ones fall into `UNKNOWN` and stay unreported forever.
- The policy layer must never resolve an `UNKNOWN` job. `core/policy.py` already follows this rule, and it has to stay that way.

## 8. Dependencies

`azure-quantum`'s own `requirements.txt`:

```
azure-core>=1.41.0,<2.0
azure-identity>=1.25.3,<2.0
azure-storage-blob>=12.20,<13.0
msrest>=0.7.1,<1.0
numpy>=2.2.6
deprecated>=1.3.1,<2.0
```

`azure-storage-blob` is there to download results, which Qoffee never reads. In the same way, `amazon-braket-sdk` pulls in numpy, networkx and openqasm3 for building circuits, which Qoffee doesn't do.

### Recommended

| Provider | Package | Rationale |
|---|---|---|
| IBM | `qiskit-ibm-runtime` | already working |
| AWS | `boto3` | the `braket` and `resourcegroupstaggingapi` clients ship in botocore, so the SDK isn't needed |
| Azure | `requests` | with `x-ms-quantum-api-key`, the data plane is a plain GET plus a PATCH |

```toml
dependencies = ["requests>=2.31"]

[project.optional-dependencies]
ibm   = ["qiskit-ibm-runtime>=0.49,<0.50"]
aws   = ["boto3>=1.35"]
azure = []
all   = ["qoffee[ibm,aws,azure]"]
dev   = ["pytest>=8.0", "pytest-cov>=5.0"]
```

An IBM-only user installs no AWS or Azure code. Rough install sizes are about 50 MB for IBM (qiskit), about 10 MB for AWS (boto3) and close to nothing for Azure, so adding both new vendors costs less than the IBM support already in place.

If the Azure API key turns out to be unavailable, the fallback is `azure-identity` alone for the client-credentials flow, which is still far lighter than the full SDK.

## 9. Credentials and permissions

### IBM

`IBM_TOKEN` and `IBM_CRN`. The token isn't scoped; it grants whatever the account can do.

### AWS

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "QoffeeDiscovery",
      "Effect": "Allow",
      "Action": "tag:GetResources",
      "Resource": "*"
    },
    {
      "Sid": "QoffeeReadTasks",
      "Effect": "Allow",
      "Action": ["braket:SearchQuantumTasks", "braket:GetQuantumTask"],
      "Resource": "*"
    },
    {
      "Sid": "QoffeeWriteTags",
      "Effect": "Allow",
      "Action": ["braket:TagResource", "braket:UntagResource"],
      "Resource": "arn:aws:braket:*:*:quantum-task/*"
    }
  ]
}
```

The IAM prefix for the tagging API is `tag:`, not `resourcegroupstaggingapi:`.

The policy leaves out `CreateQuantumTask`, `CancelQuantumTask`, `GetJob`, `SearchJobs` and every S3 permission on purpose. Results are stored in S3, so without S3 access the policy itself stops Qoffee from reading your results. That's a stronger guarantee than Qoffee can give on IBM.

List operations can't be scoped below `"*"`. The two write actions are scoped to quantum tasks only.

### Azure

Either `x-ms-quantum-api-key` (preferred, one secret) or an Entra service principal (three secrets: tenant, client ID and client secret). Both also need the workspace details: subscription ID, resource group, workspace name and region.

## 10. References

### IBM Quantum

- [QiskitRuntimeService API](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/qiskit-runtime-service)
- [RuntimeJobV2](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/runtime-job-v2)

### AWS Braket

- [API Operations index](https://docs.aws.amazon.com/braket/latest/APIReference/API_Operations.html)
- [SearchQuantumTasks](https://docs.aws.amazon.com/braket/latest/APIReference/API_SearchQuantumTasks.html)
- [SearchQuantumTasksFilter](https://docs.aws.amazon.com/braket/latest/APIReference/API_SearchQuantumTasksFilter.html)
- [QuantumTaskSummary](https://docs.aws.amazon.com/braket/latest/APIReference/API_QuantumTaskSummary.html)
- [GetQuantumTask](https://docs.aws.amazon.com/braket/latest/APIReference/API_GetQuantumTask.html)
- [SearchJobsFilter](https://docs.aws.amazon.com/braket/latest/APIReference/API_SearchJobsFilter.html)
- [TagResource](https://docs.aws.amazon.com/braket/latest/APIReference/API_TagResource.html)
- [Braket quotas](https://docs.aws.amazon.com/braket/latest/developerguide/braket-quotas.html)
- [Monitoring with EventBridge](https://docs.aws.amazon.com/braket/latest/developerguide/braket-monitor-eventbridge.html)

### AWS Resource Groups Tagging

- [GetResources](https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/API_GetResources.html)
- [Tag Editor service quotas](https://docs.aws.amazon.com/tag-editor/latest/userguide/service-quotas.html)
- [Services that support the Resource Groups Tagging API](https://docs.aws.amazon.com/tag-editor/latest/userguide/supported-services.html)

### Azure Quantum

- [Jobs - List (data plane)](https://learn.microsoft.com/en-us/rest/api/azurequantum/dataplane/jobs/list)
- [Jobs - Get](https://learn.microsoft.com/en-us/rest/api/azurequantum/dataplane/jobs/get)
- [Jobs - Patch](https://learn.microsoft.com/en-us/rest/api/azurequantum/dataplane/jobs/patch)
- [az quantum job CLI reference](https://learn.microsoft.com/en-us/cli/azure/quantum/job)
- [azure-quantum-python on GitHub](https://github.com/microsoft/azure-quantum-python)
- [Azure Quantum quotas](https://learn.microsoft.com/en-us/azure/quantum/azure-quantum-quotas)
- [Azure subscription and service limits](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits)

## Summary

Every vendor offers a marker on each job that can be both queried and changed. IBM and Braket use tags, and Azure uses the job name.
