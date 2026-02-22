"""Car Insurance Claim Processing (CICP) Agent.

A multi-step agent that processes car insurance claims by:
1. Extracting details from an uploaded claim form (PDF / document).
2. Analysing an uploaded damaged-car image via Azure OpenAI vision.
3. Retrieving applicable insurance rules from the **cicp** Azure AI Search index.
4. Synthesising a final APPROVE / REJECT decision with reasoning.

The agent is conversational — it prompts the user to upload the required
files (claim form + damage photo) if they are not yet provided.

Authentication uses **DefaultAzureCredential** (role-based access).
"""

from __future__ import annotations

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm, get_vectorstore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_DOC_EXTS = {".txt", ".md", ".pdf", ".csv", ".json", ".docx", ".xlsx"}

# Hard-coded index name for insurance rules
_CICP_INDEX_NAME = "cicp"

# Per-session state tracking (session_id → dict of uploaded paths)
# This allows the agent to remember across turns which files were already uploaded.
_session_files: dict[str, dict[str, str | None]] = {}


# ---------------------------------------------------------------------------
# Helper: encode image to base64
# ---------------------------------------------------------------------------
def _encode_image(image_path: str) -> tuple[str, str]:
    """Read and base64-encode a local image; return (b64_string, mime_type)."""
    path = Path(image_path)
    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    with open(path, "rb") as fh:
        b64 = base64.standard_b64encode(fh.read()).decode("utf-8")
    return b64, mime_type


# ---------------------------------------------------------------------------
# Helper: read text from a document file
# ---------------------------------------------------------------------------
def _read_document(file_path: str) -> str:
    """Extract text content from a document file."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(path))
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text.strip() or "[PDF contained no extractable text]"
        except ImportError:
            # Fallback: try pdfplumber
            try:
                import pdfplumber
                with pdfplumber.open(str(path)) as pdf:
                    text = "\n".join(
                        page.extract_text() or "" for page in pdf.pages
                    )
                return text.strip() or "[PDF contained no extractable text]"
            except ImportError:
                return "[PDF reading requires PyMuPDF or pdfplumber — please install one]"
    else:
        # Plain text / CSV / JSON / Markdown / etc.
        try:
            return path.read_text(encoding="utf-8", errors="replace")[:15000]
        except Exception as exc:
            return f"[Error reading file: {exc}]"


# ---------------------------------------------------------------------------
# Sub-task 1: Extract claim details from the uploaded form
# ---------------------------------------------------------------------------
@traceable(name="cicp_extract_claim", run_type="chain", tags=["cicp"])
async def _extract_claim_details(file_path: str) -> str:
    """Use the LLM to extract structured claim details from a document or scanned image."""
    llm = get_chat_llm(temperature=0.0, name="cicp-claim-extractor")

    ext = Path(file_path).suffix.lower()
    is_image_form = ext in _IMAGE_EXTS

    system = SystemMessage(content="""\
You are an insurance claim form analyst. Extract ALL relevant details from the \
claim form provided below. Structure your output as follows:

## Claim Summary
- **Claimant Name**: …
- **Policy Number**: …
- **Date of Incident**: …
- **Date of Claim**: …
- **Vehicle Make/Model/Year**: …
- **Vehicle VIN**: …
- **Incident Description**: …
- **Location of Incident**: …
- **Estimated Damage Amount**: …
- **Injuries Reported**: …
- **Police Report Filed**: …
- **Witnesses**: …
- **Other Parties Involved**: …
- **Additional Notes**: …

If a field is not present in the form, write "Not provided".
""")

    if is_image_form:
        # Scanned claim form — use vision to read the image
        b64, mime = _encode_image(file_path)
        logger.info("CICP: Reading scanned claim form via vision: %s", file_path)
        human = HumanMessage(content=[
            {"type": "text", "text": "This is a scanned insurance claim form. Please read and extract all details from it."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ])
    else:
        # Text-based document
        doc_text = _read_document(file_path)
        logger.info("CICP: Extracted %d chars from claim form %s", len(doc_text), file_path)
        human = HumanMessage(content=f"CLAIM FORM CONTENT:\n\n{doc_text}")

    response = await llm.ainvoke([system, human])
    add_tokens(response)
    return response.content


# ---------------------------------------------------------------------------
# Sub-task 2: Analyse the damaged car image
# ---------------------------------------------------------------------------
@traceable(name="cicp_damage_assessment", run_type="chain", tags=["cicp"])
async def _assess_damage(image_path: str) -> str:
    """Use Azure OpenAI vision to assess car damage from a photo."""
    llm = get_chat_llm(temperature=0.2, name="cicp-damage-assessor")

    b64, mime = _encode_image(image_path)
    logger.info("CICP: Analysing damage image %s (%s)", image_path, mime)

    content_parts = [
        {
            "type": "text",
            "text": (
                "You are an expert automotive damage assessor for an insurance company. "
                "Analyse this car damage photo and provide a detailed assessment:\n\n"
                "## Damage Assessment\n"
                "- **Damage Severity**: (Minor / Moderate / Severe / Total Loss)\n"
                "- **Affected Areas**: List all damaged parts (bumper, hood, fender, door, "
                "windshield, etc.)\n"
                "- **Type of Damage**: (Dent, scratch, crack, crush, shatter, etc.)\n"
                "- **Estimated Repair Complexity**: (Simple repair / Panel replacement / "
                "Major structural / Uneconomical to repair)\n"
                "- **Visible Safety Concerns**: (Airbag deployment, structural deformation, "
                "fluid leaks, etc.)\n"
                "- **Consistency Notes**: Does the damage appear consistent with a typical "
                "collision? Any signs of pre-existing damage or tampering?\n"
                "- **Estimated Repair Cost Range**: Provide a rough USD range.\n\n"
                "Be thorough and factual."
            ),
        },
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        },
    ]

    message = HumanMessage(content=content_parts)
    response = await llm.ainvoke([message])
    add_tokens(response)
    return response.content


# ---------------------------------------------------------------------------
# Sub-task 3: Extract police report details
# ---------------------------------------------------------------------------
@traceable(name="cicp_police_report", run_type="chain", tags=["cicp"])
async def _extract_police_report(file_path: str) -> str:
    """Use the LLM to extract key details from a police/incident report."""
    llm = get_chat_llm(temperature=0.0, name="cicp-police-report-extractor")

    ext = Path(file_path).suffix.lower()
    is_image_report = ext in _IMAGE_EXTS

    system = SystemMessage(content="""\
You are an insurance claims analyst reviewing a police/incident report. \
Extract ALL relevant details from the report. Structure your output as follows:

## Police Report Summary
- **Report/Case Number**: …
- **Filing Date**: …
- **Reporting Officer**: …
- **Incident Date & Time**: …
- **Incident Location**: …
- **Parties Involved**: …
- **Vehicle(s) Involved**: (make, model, plate numbers)
- **Incident Description**: (officer's account)
- **Fault Determination**: (if stated)
- **Witnesses Listed**: …
- **Injuries Reported**: …
- **Citations / Charges Filed**: …
- **BAC / Substance Involvement**: …
- **Report Conclusion / Officer's Notes**: …

If a field is not present in the report, write "Not provided".
""")

    if is_image_report:
        b64, mime = _encode_image(file_path)
        logger.info("CICP: Reading scanned police report via vision: %s", file_path)
        human = HumanMessage(content=[
            {"type": "text", "text": "This is a scanned police/incident report. Please read and extract all details from it."},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ])
    else:
        doc_text = _read_document(file_path)
        logger.info("CICP: Extracted %d chars from police report %s", len(doc_text), file_path)
        human = HumanMessage(content=f"POLICE REPORT CONTENT:\n\n{doc_text}")

    response = await llm.ainvoke([system, human])
    add_tokens(response)
    return response.content


# ---------------------------------------------------------------------------
# Sub-task 4: Retrieve applicable insurance rules from the cicp index
# ---------------------------------------------------------------------------
@traceable(name="cicp_rules_lookup", run_type="chain", tags=["cicp"])
async def _lookup_rules(claim_summary: str, damage_summary: str) -> str:
    """Search the 'cicp' Azure AI Search index for applicable rules."""

    vectorstore = get_vectorstore(_CICP_INDEX_NAME)

    # Build a focused search query combining claim + damage info
    search_query = (
        f"Insurance claim rules for: {claim_summary[:500]} "
        f"Damage assessment: {damage_summary[:500]}"
    )

    logger.info("CICP: Searching '%s' index for applicable rules", _CICP_INDEX_NAME)

    try:
        retriever = vectorstore.as_retriever()
        docs = await retriever.ainvoke(search_query)
        if docs:
            rules_text = "\n\n---\n\n".join(
                f"**Rule {i+1}:**\n{doc.page_content}" for i, doc in enumerate(docs)
            )
            return rules_text
        else:
            return "[No matching rules found in the cicp index]"
    except Exception as exc:
        logger.warning("CICP rules lookup error: %s", exc)
        return f"[Rules lookup error: {exc}]"


# ---------------------------------------------------------------------------
# Sub-task 5: Final decision — APPROVE or REJECT with reasoning
# ---------------------------------------------------------------------------
@traceable(name="cicp_decision", run_type="chain", tags=["cicp"])
async def _make_decision(
    claim_details: str,
    damage_assessment: str,
    police_report: str | None,
    rules: str,
    original_query: str,
) -> str:
    """Synthesise everything and render a final APPROVE / REJECT decision."""
    llm = get_chat_llm(temperature=0.1, name="cicp-decision-maker")

    police_instruction = ""
    if police_report:
        police_instruction = (
            "A police report has been provided. You MUST perform a mandatory "
            "cross-verification between the claim form and the police report BEFORE "
            "making any decision. Compare the following fields carefully:\n\n"
            "MANDATORY CROSS-VERIFICATION CHECKLIST:\n"
            "- **VIN (Vehicle Identification Number)**: Must match EXACTLY between claim form and police report. "
            "ANY mismatch = automatic REJECTION (possible fraud).\n"
            "- **Vehicle Make/Model/Year**: Must be consistent.\n"
            "- **License Plate Number**: Must match if present in both.\n"
            "- **Claimant Name vs. Parties Involved**: The claimant must appear in the police report.\n"
            "- **Incident Date & Time**: Must be consistent between documents.\n"
            "- **Incident Location**: Must be consistent.\n"
            "- **Incident Description**: The accounts should be broadly consistent. "
            "Major contradictions are a red flag.\n"
            "- **Injuries Reported**: Should align.\n\n"
            "⚠️ CRITICAL: If the VIN in the claim form does NOT match the VIN in the "
            "police report, you MUST REJECT the claim immediately and cite the VIN mismatch "
            "as the primary reason. This is a strong indicator of fraud or filing error.\n\n"
            "List ALL discrepancies found in the Analysis section, even minor ones."
        )
    else:
        police_instruction = (
            "⚠️ NO POLICE REPORT WAS PROVIDED. This is a critical factor. "
            "Apply the applicable insurance policy rules regarding claims without "
            "a police report. Many policies require a police report for claims "
            "above a certain threshold or for specific incident types (e.g., theft, "
            "hit-and-run, multi-vehicle). If the rules mandate a police report for "
            "this type of claim, this should heavily influence your decision toward "
            "REJECTION or conditional approval pending the report."
        )

    system = SystemMessage(content=f"""\
You are a senior insurance claims adjudicator. Based on the claim form details, \
the damage assessment report, the police report (if available), and the applicable \
insurance policy rules, render a final decision.

{police_instruction}

Your response MUST follow this exact structure:

---

# 🚗 Car Insurance Claim — Decision Report

## 1. Claim Summary
(Recap key claim details)

## 2. Damage Assessment Summary
(Recap key damage findings)

## 3. Police Report Summary
(Recap police report findings, or clearly state "No police report was provided" \
and note the implications)

## 4. Applicable Rules & Policy Provisions
(List the relevant rules that apply to this claim, especially any rules about \
police report requirements)

## 5. Cross-Verification Results
(If a police report was provided, list EACH field compared between the claim form \
and police report: VIN, vehicle details, claimant name, incident date, location, \
description. Mark each as ✅ MATCH or ❌ MISMATCH. If no police report, write "N/A".)

## 6. Analysis
(Explain how the claim, damage, police report, and rules interact — flag any \
inconsistencies, red flags, or policy exclusions. If cross-verification found \
mismatches, especially VIN mismatch, this MUST be the primary factor. If no police \
report was filed, explicitly analyse the impact per policy rules.)

## 7. Decision

**DECISION: ✅ APPROVED** or **DECISION: ❌ REJECTED**

**Reason**: (Clear, concise justification)

**Conditions / Next Steps**: (Any conditions for approval, or what the claimant \
can do if rejected — e.g., "Submit a police report within 30 days")

---

Be fair, thorough, and cite specific rules where applicable.
""")

    human_content = (
        f"## Original User Request\n{original_query}\n\n"
        f"## Claim Form Details\n{claim_details}\n\n"
        f"## Damage Assessment\n{damage_assessment}\n\n"
    )
    if police_report:
        human_content += f"## Police Report Details\n{police_report}\n\n"
    else:
        human_content += "## Police Report\n⚠️ **Not provided by claimant.**\n\n"
    human_content += f"## Applicable Insurance Rules\n{rules}"

    response = await llm.ainvoke([system, HumanMessage(content=human_content)])
    add_tokens(response)
    return response.content


# ---------------------------------------------------------------------------
# Helper: classify uploaded file by user intent + extension
# ---------------------------------------------------------------------------

_CLAIM_FORM_HINTS = {
    "claim form", "claim document", "insurance form", "my claim",
    "here is my claim", "here is the claim", "claim file",
    "the form", "my form", "insurance claim form",
    "uploaded the form", "uploading the form", "this is the form",
    "attached the form", "attaching the form",
    "application form", "claim application",
}

_DAMAGE_PHOTO_HINTS = {
    "damage photo", "damage image", "damaged car", "car photo",
    "car image", "vehicle damage", "damage picture", "the damage",
    "here is the damage", "photo of the damage", "photo of damage",
    "picture of the car", "picture of damage", "accident photo",
    "here is the photo", "uploading the photo", "attached the photo",
    "car damage", "vehicle photo",
}

_POLICE_REPORT_HINTS = {
    "police report", "police filing", "fir", "fir report",
    "incident report", "accident report", "police document",
    "here is the police", "the police report", "my police report",
    "filed a police report", "attached the police", "uploading the police",
    "law enforcement report", "officer report",
}

_SKIP_POLICE_HINTS = {
    "skip", "no police report", "don't have", "do not have",
    "no report", "wasn't filed", "was not filed", "none",
    "i don't have", "i do not have", "not available",
    "no fir", "skip police", "proceed without",
}


def _classify_upload(file_path: str, query: str) -> str | None:
    """Determine whether the uploaded file is a 'claim_form', 'damage_image', or 'police_report'.

    Uses the user's message text first (intent-based), then falls back to
    file extension heuristics. This handles scanned claim forms that are
    images (JPG/PNG) correctly.
    """
    q = query.lower().strip()
    ext = Path(file_path).suffix.lower()
    is_image = ext in _IMAGE_EXTS
    is_doc = ext in _DOC_EXTS

    # 1. Check user message for explicit intent
    if any(hint in q for hint in _POLICE_REPORT_HINTS):
        return "police_report"
    if any(hint in q for hint in _CLAIM_FORM_HINTS):
        return "claim_form"
    if any(hint in q for hint in _DAMAGE_PHOTO_HINTS):
        return "damage_image"

    # 2. Fallback: non-image documents are almost always claim forms
    if is_doc:
        return "claim_form"

    # 3. For images with no clear intent in the message, we cannot
    #    reliably guess. Return None so the caller can ask the user.
    if is_image:
        return None  # ambiguous — could be scanned form or damage photo

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@traceable(name="cicp_agent", run_type="chain", tags=["cicp", "agent"])
async def invoke(
    query: str,
    *,
    file_path: Optional[str] = None,
    history: str = "",
    session_id: str = "default",
    **kwargs,
) -> str:
    """Main entry point for the CICP agent.

    Orchestrates the multi-step claim processing pipeline:
    1. Checks for required uploads (claim form + damage photo + police report).
    2. If claim form + damage photo present → asks for police report (or skip).
    3. Once ready → runs the full pipeline.
    4. If police report is skipped → applies rules and may reject.
    """
    # ── Initialise session state ────────────────────────────────
    if session_id not in _session_files:
        _session_files[session_id] = {
            "claim_form": None,
            "damage_image": None,
            "police_report": None,
            "police_report_asked": False,
            "police_report_skipped": False,
        }

    session = _session_files[session_id]
    q = query.lower().strip()

    # ── Check if user wants to skip police report ───────────────
    if session.get("police_report_asked") and not session.get("police_report_skipped"):
        if not file_path and any(hint in q for hint in _SKIP_POLICE_HINTS):
            session["police_report_skipped"] = True
            logger.info("CICP: User opted to skip police report")

    # ── Classify the current upload (if any) ────────────────────
    if file_path:
        ftype = _classify_upload(file_path, query)
        if ftype == "claim_form":
            session["claim_form"] = file_path
            logger.info("CICP: Claim form uploaded → %s", file_path)
        elif ftype == "damage_image":
            session["damage_image"] = file_path
            logger.info("CICP: Damage image uploaded → %s", file_path)
        elif ftype == "police_report":
            session["police_report"] = file_path
            logger.info("CICP: Police report uploaded → %s", file_path)
        elif ftype is None and Path(file_path).suffix.lower() in _IMAGE_EXTS:
            # Ambiguous image — stash it and ask the user
            session["_last_ambiguous_image"] = file_path
            fname = Path(file_path).name
            return (
                f"## 🚗 CICP — File Received: **{fname}**\n\n"
                "I received an image file but I'm not sure what this is:\n\n"
                "- 📄 A **scanned claim form** — reply with "
                "*\"This is my claim form\"*\n"
                "- 📸 A **damaged car photo** — reply with "
                "*\"This is the damage photo\"*\n"
                "- 🚔 A **police report** — reply with "
                "*\"This is the police report\"*\n\n"
                "This helps me process your claim correctly!"
            )

    # ── Re-classify from message alone (no new file, user clarified) ──
    if not file_path:
        last_ambiguous = session.get("_last_ambiguous_image")
        if last_ambiguous:
            if any(hint in q for hint in _POLICE_REPORT_HINTS):
                session["police_report"] = last_ambiguous
                session.pop("_last_ambiguous_image", None)
                logger.info("CICP: User clarified image as police report → %s", last_ambiguous)
            elif any(hint in q for hint in _CLAIM_FORM_HINTS):
                session["claim_form"] = last_ambiguous
                session.pop("_last_ambiguous_image", None)
                logger.info("CICP: User clarified image as claim form → %s", last_ambiguous)
            elif any(hint in q for hint in _DAMAGE_PHOTO_HINTS):
                session["damage_image"] = last_ambiguous
                session.pop("_last_ambiguous_image", None)
                logger.info("CICP: User clarified image as damage photo → %s", last_ambiguous)

    has_claim_form = session["claim_form"] is not None
    has_damage_image = session["damage_image"] is not None
    has_police_report = session["police_report"] is not None
    police_skipped = session.get("police_report_skipped", False)

    # ── Prompt for missing uploads ──────────────────────────────
    if not has_claim_form and not has_damage_image:
        return (
            "## 🚗 Car Insurance Claim Processing (CICP)\n\n"
            "I can help you process a car insurance claim! To get started, "
            "I need **three files**:\n\n"
            "1. 📄 **Claim Form** — Upload the insurance claim form "
            "(PDF, DOCX, TXT, or a **scanned image** like JPG/PNG)\n"
            "2. 📸 **Damaged Car Photo** — Upload a photo of the vehicle damage "
            "(PNG, JPG, GIF, or WebP)\n"
            "3. 🚔 **Police Report** — Upload the police/incident report "
            "(PDF, DOCX, TXT, or scanned image)\n\n"
            "Please **attach the claim form** using the 📎 clip icon, "
            "then send a message like *\"Here is my claim form\"*.\n\n"
            "💡 **Tip:** Since files can be images, always tell me what "
            "you're uploading in your message!\n\n"
            "Once I have all files, I will:\n"
            "- Extract details from your claim form\n"
            "- Assess the vehicle damage from the photo\n"
            "- Review the police report\n"
            "- Check applicable insurance rules\n"
            "- Render a final **APPROVE** or **REJECT** decision"
        )

    if has_claim_form and not has_damage_image:
        return (
            "## 🚗 CICP — Claim Form Received ✅\n\n"
            f"I've received your claim form: **{Path(session['claim_form']).name}**\n\n"
            "Now please **attach a photo of the damaged vehicle** "
            "using the 📎 clip icon and send a message like "
            "*\"Here is the damage photo\"*."
        )

    if not has_claim_form and has_damage_image:
        return (
            "## 🚗 CICP — Damage Photo Received ✅\n\n"
            f"I've received the damage photo: **{Path(session['damage_image']).name}**\n\n"
            "Now please **attach the insurance claim form** "
            "(PDF, DOCX, TXT, or scanned image) using the 📎 clip icon "
            "and send a message like *\"Here is my claim form\"*."
        )

    # ── Both claim form + damage photo present — now ask for police report ──
    if has_claim_form and has_damage_image and not has_police_report and not police_skipped:
        if not session.get("police_report_asked"):
            session["police_report_asked"] = True
        return (
            "## 🚗 CICP — Claim Form ✅ & Damage Photo ✅\n\n"
            f"✅ Claim form: **{Path(session['claim_form']).name}**\n"
            f"✅ Damage photo: **{Path(session['damage_image']).name}**\n\n"
            "---\n\n"
            "### 🚔 Police Report Required\n\n"
            "A **police/incident report** is required for claim processing. "
            "Please upload it using the 📎 clip icon and send a message like "
            "*\"Here is the police report\"*.\n\n"
            "**If you do not have a police report**, reply with "
            "*\"No police report\"* or *\"Skip\"* — I will still process your "
            "claim, but **the absence of a police report will be factored into "
            "the decision per insurance policy rules** and may result in "
            "rejection."
        )

    # ── All files ready (or police report skipped) → run pipeline ──
    police_status = "provided" if has_police_report else "SKIPPED"
    logger.info(
        "CICP: Running full pipeline (form=%s, image=%s, police=%s)",
        session["claim_form"],
        session["damage_image"],
        police_status,
    )

    try:
        import asyncio

        # Step 1, 2 (& 3 if police report provided) run in parallel
        tasks = [
            _extract_claim_details(session["claim_form"]),
            _assess_damage(session["damage_image"]),
        ]
        if has_police_report:
            tasks.append(_extract_police_report(session["police_report"]))

        results = await asyncio.gather(*tasks)

        claim_details = results[0]
        damage_assessment = results[1]
        police_report_details = results[2] if has_police_report else None

        # Step 4: Look up rules using combined context
        rules = await _lookup_rules(claim_details, damage_assessment)

        # Step 5: Final decision
        decision = await _make_decision(
            claim_details,
            damage_assessment,
            police_report_details,
            rules,
            query,
        )

        # Clear session files after processing so next claim starts fresh
        _session_files[session_id] = {
            "claim_form": None,
            "damage_image": None,
            "police_report": None,
            "police_report_asked": False,
            "police_report_skipped": False,
        }

        return decision

    except Exception as exc:
        logger.exception("CICP pipeline error")
        return (
            f"## ⚠️ CICP Processing Error\n\n"
            f"An error occurred while processing your claim: **{exc}**\n\n"
            "Please try again or contact support."
        )
