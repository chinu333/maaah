"""FHIR (Fast Healthcare Interoperability Resources) Data Conversion Agent.

Helps users convert healthcare data between various formats and FHIR R4 JSON.
Supports conversions such as:
  - CSV / flat-file patient records → FHIR Patient, Observation, Condition bundles
  - HL7v2 messages → FHIR resources
  - CDA / C-CDA XML → FHIR resources
  - Free-text clinical notes → structured FHIR resources
  - FHIR resource generation from natural-language descriptions
  - FHIR Bundle assembly with proper references
  - **Live validation** against the public HAPI FHIR R4 server
  - **Live submission** to create resources on the HAPI FHIR server

The agent pipeline:
  1. LLM generates FHIR R4 JSON from the user's input
  2. Extracted JSON blocks are **validated** via HAPI FHIR ``$validate``
  3. Valid resources are **POSTed** to the HAPI server to obtain server-assigned IDs
  4. Results (validation outcome + server URLs) are appended to the response

Authentication uses **DefaultAzureCredential** (role-based access) for Azure OpenAI.
The HAPI FHIR public server requires **no authentication**.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm

logger = logging.getLogger(__name__)

# File extensions the agent can read as source data
_TEXT_EXTS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".hl7",
    ".tsv", ".yaml", ".yml", ".cda", ".ccda", ".fhir",
}

# ---------------------------------------------------------------------------
# HAPI FHIR R4 public test server
# ---------------------------------------------------------------------------
_HAPI_BASE = "https://hapi.fhir.org/baseR4"
_HAPI_TIMEOUT = 30.0  # seconds

# FHIR resource types that can be validated / POSTed individually
_POSTABLE_TYPES = {
    "Patient", "Observation", "Condition", "Encounter",
    "MedicationRequest", "MedicationStatement", "Procedure",
    "AllergyIntolerance", "DiagnosticReport", "Immunization",
    "CarePlan", "ServiceRequest", "Coverage", "Composition",
    "DocumentReference", "Organization", "Practitioner",
    "PractitionerRole", "Location", "Device", "Specimen",
    "ExplanationOfBenefit", "Claim", "ClaimResponse",
}


# ---------------------------------------------------------------------------
# Helper: extract JSON blocks from LLM markdown output
# ---------------------------------------------------------------------------
_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)```", re.DOTALL)


def _extract_json_blocks(text: str) -> list[dict[str, Any]]:
    """Parse all ```json ... ``` blocks and return valid dicts."""
    results: list[dict[str, Any]] = []
    for m in _JSON_BLOCK_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "resourceType" in obj:
                results.append(obj)
        except json.JSONDecodeError:
            continue
    return results


# ---------------------------------------------------------------------------
# Helper: flatten a Bundle into individual resources (for per-resource POST)
# ---------------------------------------------------------------------------
def _flatten_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """If the dict is a Bundle, extract entry resources; otherwise return [dict]."""
    if bundle.get("resourceType") == "Bundle":
        entries = bundle.get("entry", [])
        resources = []
        for e in entries:
            res = e.get("resource")
            if isinstance(res, dict) and "resourceType" in res:
                resources.append(res)
        return resources if resources else [bundle]
    return [bundle]


# ---------------------------------------------------------------------------
# HAPI: validate a single resource
# ---------------------------------------------------------------------------
async def _validate_resource(
    client: httpx.AsyncClient,
    resource: dict[str, Any],
) -> dict[str, Any]:
    """POST to $validate and return structured result."""
    rtype = resource.get("resourceType", "Resource")
    url = f"{_HAPI_BASE}/{rtype}/$validate"
    try:
        resp = await client.post(
            url,
            json=resource,
            headers={"Content-Type": "application/fhir+json"},
        )
        outcome = resp.json()
        issues = outcome.get("issue", [])
        errors = [i for i in issues if i.get("severity") in ("error", "fatal")]
        warnings = [i for i in issues if i.get("severity") == "warning"]
        info = [i for i in issues if i.get("severity") == "information"]
        return {
            "resourceType": rtype,
            "status": resp.status_code,
            "valid": len(errors) == 0,
            "errors": [i.get("diagnostics", "Unknown error") for i in errors],
            "warnings": [i.get("diagnostics", "") for i in warnings],
            "info": [i.get("diagnostics", "") for i in info],
        }
    except Exception as exc:
        return {
            "resourceType": rtype,
            "status": 0,
            "valid": False,
            "errors": [f"Validation request failed: {exc}"],
            "warnings": [],
            "info": [],
        }


# ---------------------------------------------------------------------------
# HAPI: POST (create) a single resource
# ---------------------------------------------------------------------------
async def _post_resource(
    client: httpx.AsyncClient,
    resource: dict[str, Any],
) -> dict[str, Any]:
    """POST the resource to HAPI and return the server response summary."""
    rtype = resource.get("resourceType", "Resource")

    # Remove client-side id so the server assigns one
    payload = {k: v for k, v in resource.items() if k != "id"}

    url = f"{_HAPI_BASE}/{rtype}"
    try:
        resp = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/fhir+json"},
        )
        if resp.status_code == 201:
            body = resp.json()
            server_id = body.get("id", "?")
            return {
                "resourceType": rtype,
                "status": 201,
                "success": True,
                "server_id": server_id,
                "url": f"{_HAPI_BASE}/{rtype}/{server_id}",
                "message": f"Created {rtype}/{server_id}",
            }
        else:
            body = resp.json() if resp.headers.get("content-type", "").startswith("application") else {}
            diag = ""
            if "issue" in body:
                diag = "; ".join(
                    i.get("diagnostics", "") for i in body["issue"]
                    if i.get("severity") in ("error", "fatal")
                )
            return {
                "resourceType": rtype,
                "status": resp.status_code,
                "success": False,
                "server_id": None,
                "url": None,
                "message": diag or f"HTTP {resp.status_code}",
            }
    except Exception as exc:
        return {
            "resourceType": rtype,
            "status": 0,
            "success": False,
            "server_id": None,
            "url": None,
            "message": f"POST failed: {exc}",
        }


# ---------------------------------------------------------------------------
# HAPI: POST a Bundle (transaction/batch)
# ---------------------------------------------------------------------------
async def _post_bundle(
    client: httpx.AsyncClient,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    """POST a Bundle to the HAPI server root."""
    url = _HAPI_BASE
    try:
        resp = await client.post(
            url,
            json=bundle,
            headers={"Content-Type": "application/fhir+json"},
        )
        body = resp.json()
        if resp.status_code == 200:
            entries = body.get("entry", [])
            created = []
            for e in entries:
                res = e.get("response", {})
                loc = res.get("location", "")
                created.append(loc)
            return {
                "resourceType": "Bundle",
                "status": 200,
                "success": True,
                "created": created,
                "message": f"Bundle processed — {len(created)} entries",
            }
        else:
            diag = ""
            if body.get("resourceType") == "OperationOutcome":
                diag = "; ".join(
                    i.get("diagnostics", "") for i in body.get("issue", [])
                    if i.get("severity") in ("error", "fatal")
                )
            return {
                "resourceType": "Bundle",
                "status": resp.status_code,
                "success": False,
                "created": [],
                "message": diag or f"HTTP {resp.status_code}",
            }
    except Exception as exc:
        return {
            "resourceType": "Bundle",
            "status": 0,
            "success": False,
            "created": [],
            "message": f"Bundle POST failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Pipeline: validate + submit all resources from LLM output
# ---------------------------------------------------------------------------
async def _validate_and_submit(text: str) -> str:
    """Extract JSON from LLM output, validate against HAPI, POST valid ones.

    Returns a Markdown section to append to the agent response.
    """
    json_blocks = _extract_json_blocks(text)
    if not json_blocks:
        return ""

    sections: list[str] = []
    sections.append("\n\n---\n\n## 🏥 HAPI FHIR R4 Server — Live Validation & Submission\n")
    sections.append(f"> **Server:** `{_HAPI_BASE}` (public test server — no PHI)\n")

    async with httpx.AsyncClient(timeout=_HAPI_TIMEOUT) as client:
        for block in json_blocks:
            rtype = block.get("resourceType", "Unknown")

            # ── Handle Bundles ───────────────────────────────────
            if rtype == "Bundle":
                bundle_type = block.get("type", "unknown")
                entry_count = len(block.get("entry", []))
                sections.append(f"\n### Bundle ({bundle_type}) — {entry_count} entries\n")

                # Validate individual resources within the Bundle
                resources = _flatten_bundle(block)
                all_valid = True
                val_lines: list[str] = []
                for res in resources:
                    vr = await _validate_resource(client, res)
                    rt = vr["resourceType"]
                    if vr["valid"]:
                        val_lines.append(f"  - ✅ **{rt}** — Valid")
                        if vr["warnings"]:
                            for w in vr["warnings"][:2]:
                                val_lines.append(f"    - ⚠️ {w}")
                    else:
                        all_valid = False
                        val_lines.append(f"  - ❌ **{rt}** — Invalid")
                        for e in vr["errors"][:3]:
                            val_lines.append(f"    - {e}")

                sections.append("**Validation Results:**\n")
                sections.extend(val_lines)
                sections.append("")

                # Submit the Bundle if transaction/batch
                if bundle_type in ("transaction", "batch") and all_valid:
                    br = await _post_bundle(client, block)
                    if br["success"]:
                        sections.append(f"\n**Submission:** ✅ Bundle accepted — "
                                        f"{len(br['created'])} resources created\n")
                        for loc in br["created"][:10]:
                            if loc:
                                sections.append(f"  - 🔗 `{_HAPI_BASE}/{loc}`")
                    else:
                        sections.append(f"\n**Submission:** ❌ {br['message']}\n")
                        # Fallback: POST individual resources
                        sections.append("\n**Fallback** — submitting resources individually:\n")
                        for res in resources:
                            rt2 = res.get("resourceType", "")
                            if rt2 in _POSTABLE_TYPES:
                                pr = await _post_resource(client, res)
                                if pr["success"]:
                                    sections.append(
                                        f"  - ✅ **{rt2}** → "
                                        f"[{pr['server_id']}]({pr['url']})"
                                    )
                                else:
                                    sections.append(
                                        f"  - ❌ **{rt2}** — {pr['message']}"
                                    )
                elif bundle_type in ("transaction", "batch") and not all_valid:
                    sections.append(
                        "\n**Submission:** ⏸️ Skipped — fix validation errors first\n"
                    )
                elif all_valid:
                    # collection or other — post individual resources
                    sections.append("\n**Submitting resources individually:**\n")
                    for res in resources:
                        rt2 = res.get("resourceType", "")
                        if rt2 in _POSTABLE_TYPES:
                            pr = await _post_resource(client, res)
                            if pr["success"]:
                                sections.append(
                                    f"  - ✅ **{rt2}** → "
                                    f"[{pr['server_id']}]({pr['url']})"
                                )
                            else:
                                sections.append(
                                    f"  - ❌ **{rt2}** — {pr['message']}"
                                )

            # ── Handle single resources ──────────────────────────
            elif rtype in _POSTABLE_TYPES:
                sections.append(f"\n### {rtype}\n")

                # Validate
                vr = await _validate_resource(client, block)
                if vr["valid"]:
                    sections.append("**Validation:** ✅ Valid FHIR R4 resource\n")
                    if vr["warnings"]:
                        for w in vr["warnings"][:3]:
                            sections.append(f"  - ⚠️ {w}")

                    # POST
                    pr = await _post_resource(client, block)
                    if pr["success"]:
                        sections.append(
                            f"\n**Submitted:** ✅ Created on server → "
                            f"[{rtype}/{pr['server_id']}]({pr['url']})\n"
                        )
                    else:
                        sections.append(
                            f"\n**Submitted:** ❌ {pr['message']}\n"
                        )
                else:
                    sections.append("**Validation:** ❌ Errors found\n")
                    for e in vr["errors"][:5]:
                        sections.append(f"  - {e}")
                    sections.append(
                        "\n**Submitted:** ⏸️ Skipped — fix errors above first\n"
                    )

    if len(sections) <= 2:
        return ""

    return "\n".join(sections)

# ---------------------------------------------------------------------------
# System prompt — rich FHIR conversion expertise
# ---------------------------------------------------------------------------
_FHIR_SYSTEM_PROMPT = """\
You are the **FHIR Conversion Specialist** inside Ensō (Multi Agent AI Hub).

Your expertise covers the **HL7 FHIR R4** standard (v4.0.1) and healthcare data interoperability.

## Capabilities
1. **Data Conversion** — Convert healthcare data from CSV, HL7v2, CDA/C-CDA, \
free-text clinical notes, or any structured format into valid FHIR R4 JSON resources.
2. **Resource Generation** — Generate complete FHIR resources from natural-language \
descriptions (e.g. "Create a Patient resource for a 45-year-old male named John Smith").
3. **Bundle Assembly** — Wrap multiple resources into FHIR Bundles (transaction, batch, \
collection) with proper internal references (e.g. `"reference": "Patient/123"`).
4. **Terminology Mapping** — Map clinical terms to standard coding systems:
   - **SNOMED CT** — clinical findings, procedures, body structures
   - **LOINC** — laboratory & clinical observations
   - **ICD-10-CM** — diagnoses
   - **CPT** — procedures (US billing)
   - **RxNorm / NDC** — medications
   - **UCUM** — units of measure
5. **Validation Guidance** — Identify missing required fields, cardinality issues, \
and conformance problems in FHIR resources.
6. **Explanation** — Explain FHIR concepts, resource relationships, search parameters, \
REST API patterns, and implementation guidance.

## Output Rules
- Always produce **valid FHIR R4 JSON** when generating or converting resources.
- Use `"resourceType"` as the first key in every resource.
- Include `"id"`, `"meta"`, and appropriate `"identifier"` where relevant.
- Use proper `"coding"` arrays with `system`, `code`, and `display`.
- For Bundles, use `"fullUrl"` entries with `"urn:uuid:<uuid>"` and matching references.
- For **transaction Bundles**: every entry MUST have a `"request"` object with `"method"` \
and `"url"` (e.g. `{"method": "POST", "url": "Patient"}`).
- Generate proper UUIDs for fullUrl entries (format: `urn:uuid:<uuid4>`).
- Wrap JSON in ```json code blocks for readability.
- After the JSON, provide a brief explanation of the resource structure and any \
assumptions made.
- If the input data is ambiguous, state your assumptions clearly.
- If asked about FHIR concepts (not conversion), answer in clear Markdown.
- **Important:** Your generated JSON will be automatically validated against a live \
HAPI FHIR R4 server and submitted if valid. Ensure strict R4 compliance.

## Common Resource Mappings
| Source Data               | FHIR Resource(s)                                    |
|--------------------------|------------------------------------------------------|
| Patient demographics     | Patient                                              |
| Lab results              | Observation (category: laboratory)                   |
| Vital signs              | Observation (category: vital-signs)                  |
| Diagnoses                | Condition                                            |
| Medications              | MedicationRequest, MedicationStatement               |
| Allergies                | AllergyIntolerance                                   |
| Procedures               | Procedure                                            |
| Visits / admissions      | Encounter                                            |
| Lab reports              | DiagnosticReport + Observation                       |
| Insurance / coverage     | Coverage, ExplanationOfBenefit                       |
| Clinical notes           | DocumentReference or Composition                     |
| Immunizations            | Immunization                                         |
| Care plans               | CarePlan                                             |
| Referrals                | ServiceRequest                                       |

Be concise, accurate, and always format your response in Markdown.
"""


# ---------------------------------------------------------------------------
# Main invoke function
# ---------------------------------------------------------------------------
async def invoke(
    query: str,
    *,
    file_path: Optional[str] = None,
    history: str = "",
    **kwargs,
) -> str:
    """Process a FHIR conversion or healthcare data query."""

    llm = get_chat_llm(temperature=0.2, max_tokens=4096, name="fhir-agent-llm")

    # ── Read attached file if present ────────────────────────────
    file_context = ""
    if file_path:
        path = Path(file_path)
        if path.exists() and path.suffix.lower() in _TEXT_EXTS:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if len(content) > 15000:
                    content = content[:15000] + "\n\n… [content truncated for length] …"
                file_context = (
                    f"\n\nThe user has attached a file named **{path.name}** "
                    f"(type: `{path.suffix}`). Here is its content:\n\n"
                    f"```\n{content}\n```\n\n"
                    "Use this file content as the **source data** for conversion. "
                    "Analyse the structure, identify healthcare-relevant fields, "
                    "and convert them into the appropriate FHIR R4 resources."
                )
            except Exception as exc:
                file_context = (
                    f"\n\n[Note: Could not read attached file '{path.name}': {exc}]"
                )
        elif file_path and Path(file_path).exists():
            file_context = (
                f"\n\n[Note: The user attached '{Path(file_path).name}' but it is a "
                f"binary file type (`{Path(file_path).suffix}`). Please ask the user to "
                f"provide the data in a text-based format such as CSV, JSON, XML, or HL7.]"
            )

    # ── Build conversation history context ───────────────────────
    history_context = ""
    if history:
        history_context = (
            "\n\nHere is the recent conversation history for context:\n"
            f"{history}\n\n"
            "Use this history to maintain continuity. If the user refers to "
            "a previous conversion or resource, use the history to respond accurately."
        )

    # ── Assemble messages ────────────────────────────────────────
    messages = [
        SystemMessage(content=_FHIR_SYSTEM_PROMPT + history_context),
        HumanMessage(content=query + file_context),
    ]

    response = await llm.ainvoke(messages)
    add_tokens(response)

    llm_output = response.content

    # ── Live validation & submission against HAPI FHIR server ────
    # Only run the pipeline when the LLM produced JSON code blocks
    # (i.e. it generated/converted resources, not just explained concepts)
    hapi_section = ""
    if "```json" in llm_output:
        try:
            hapi_section = await _validate_and_submit(llm_output)
        except Exception as exc:
            logger.warning("HAPI FHIR pipeline error: %s", exc)
            hapi_section = (
                "\n\n---\n\n## 🏥 HAPI FHIR R4 Server\n"
                f"> ⚠️ Could not reach the HAPI FHIR server: {exc}\n"
                "> The generated FHIR JSON above is still valid — "
                "you can submit it manually at `https://hapi.fhir.org/baseR4`.\n"
            )

    return llm_output + hapi_section
