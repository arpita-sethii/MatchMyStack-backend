# backend/app/services/resume_parser.py
import re
import logging
from io import BytesIO
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Try pdfplumber first, then PyPDF2. Both are optional.
PDF_LIBRARY = None
try:
    import pdfplumber  # type: ignore
    PDF_LIBRARY = "pdfplumber"
except Exception:
    try:
        import PyPDF2  # type: ignore
        PDF_LIBRARY = "PyPDF2"
    except Exception:
        PDF_LIBRARY = None

logger = logging.getLogger("app.services.resume_parser")
logging.basicConfig(level=logging.INFO)

# Exported constant (routes import this)
MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB

# Regex patterns
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"[\+\(]?[0-9][0-9\-\s\.\(\)]{7,}[0-9]")
GITHUB_RE = re.compile(r"github\.com/([A-Za-z0-9_-]+)", re.IGNORECASE)
LINKEDIN_RE = re.compile(r"linkedin\.com/in/([A-Za-z0-9_-]+)", re.IGNORECASE)

# Minimal skill ontology — extend as needed
SKILL_KEYWORDS = {
    "frontend": {
        "react": ["react", "reactjs", "react.js"],
        "javascript": ["javascript", "js"],
        "html": ["html", "html5"],
        "css": ["css", "scss", "sass"],
        "tailwind": ["tailwind", "tailwindcss"],
    },
    "backend": {
        "python": ["python", "python3"],
        "fastapi": ["fastapi", "fast api"],
        "flask": ["flask"],
        "nodejs": ["node", "nodejs", "node.js"],
        "express": ["express", "expressjs"],
        "java": ["java"],
        "csharp": ["c#", "csharp", ".net"],
    },
    "ml_ai": {
        "pytorch": ["pytorch", "torch"],
        "tensorflow": ["tensorflow", "tf", "keras"],
        "sklearn": ["scikit-learn", "sklearn"],
        "nlp": ["nlp", "natural language processing"],
        "cv": ["computer vision", "opencv", "cv"],
        "transformers": ["transformers", "bert", "gpt", "llm"],
    },
    "data": {
        "sql": ["sql", "mysql", "postgres", "postgresql"],
        "pandas": ["pandas"],
        "numpy": ["numpy"],
        "mongodb": ["mongo", "mongodb"],
        "elasticsearch": ["elasticsearch", "elastic"],
    },
    "devops": {
        "docker": ["docker", "dockerfile"],
        "kubernetes": ["kubernetes", "k8s"],
        "aws": ["aws", "amazon web services", "ec2", "s3"],
    },
}

# build reverse map: synonym -> (canonical, category)
_skill_syn = {}
for cat, kv in SKILL_KEYWORDS.items():
    for canonical, syns in kv.items():
        for s in syns:
            _skill_syn[s.lower()] = (canonical, cat)

ROLE_PATTERNS = {
    "frontend": ["frontend", "front end", "front-end", "ui developer"],
    "backend": ["backend", "backend engineer", "api developer"],
    "fullstack": ["fullstack", "full-stack", "full stack"],
    "ml_engineer": ["machine learning", "ml engineer", "data scientist"],
    "devops": ["devops", "sre", "site reliability"],
}

HACKATHON_KEYWORDS = ["hackathon", "devpost", "mlh", "challenge", "competition"]


class ImprovedResumeParser:
    def __init__(self):
        # record which PDF library we're trying to use
        self.parsing_library = PDF_LIBRARY or "none"
        logger.info("Initialized ImprovedResumeParser (library=%s)", self.parsing_library)

    # -------------------------
    # PDF text extraction with THREE-STAGE FALLBACK
    # -------------------------
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> tuple[str, str, Optional[str]]:
        """
        Three-stage fallback extraction.
        Returns: (raw_text, parsing_library_used, parsing_note)
        """
        if not pdf_bytes:
            logger.warning("extract_text_from_pdf: empty bytes")
            return "", "none", "empty_input"

        if len(pdf_bytes) > MAX_PDF_BYTES:
            logger.info("extract_text_from_pdf: truncating %d -> %d", len(pdf_bytes), MAX_PDF_BYTES)
            pdf_bytes = pdf_bytes[:MAX_PDF_BYTES]

        parsing_note = None

        # STRATEGY 1: Try pdfplumber first if available
        if self.parsing_library == "pdfplumber":
            try:
                import pdfplumber  # local import
                parts: List[str] = []
                with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                    logger.info("pdfplumber: opened PDF with %d pages", len(pdf.pages))
                    for i, page in enumerate(pdf.pages):
                        try:
                            text = page.extract_text() or ""
                            if text:
                                parts.append(text)
                        except Exception as page_err:
                            logger.debug("pdfplumber page %d failed: %s", i, page_err)
                result = "\n".join(parts).strip()
                if result:
                    logger.info("✓ pdfplumber extracted %d chars", len(result))
                    return result, "pdfplumber", None
                logger.info("pdfplumber extracted no text, trying fallback")
            except Exception as e:
                error_str = str(e).lower()
                # Detect "No /Root object" or similar pdfminer errors
                if "no /root" in error_str or "pdfminer" in error_str or "pdf structure" in error_str:
                    logger.warning("⚠ pdfplumber failed with pdfminer error: %s — falling back", e)
                    parsing_note = "pdfminer_failed_used_fallback"
                else:
                    logger.exception("pdfplumber extraction error: %s", e)

        # STRATEGY 2: Fallback to PyPDF2
        if self.parsing_library == "PyPDF2" or parsing_note == "pdfminer_failed_used_fallback":
            try:
                import PyPDF2  # local import
                reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
                parts: List[str] = []
                logger.info("PyPDF2: opened PDF with %d pages", len(reader.pages))
                for i, page in enumerate(reader.pages):
                    try:
                        text = page.extract_text() or ""
                        if text:
                            parts.append(text)
                    except Exception as page_err:
                        logger.debug("PyPDF2 page %d failed: %s", i, page_err)
                result = "\n".join(parts).strip()
                if result:
                    logger.info("✓ PyPDF2 extracted %d chars", len(result))
                    if parsing_note == "pdfminer_failed_used_fallback":
                        return result, "pypdf_fallback", parsing_note
                    return result, "PyPDF2", None
                logger.info("PyPDF2 extracted no text, trying text fallback")
            except Exception as e:
                logger.warning("PyPDF2 extraction failed: %s — trying text fallback", e)

        # STRATEGY 3: Last resort - try utf-8 decode (works for text files renamed .pdf)
        try:
            decoded = pdf_bytes.decode("utf-8", errors="ignore").strip()
            if decoded and len(decoded) > 30:
                logger.info("✓ UTF-8 text fallback extracted %d chars", len(decoded))
                final_note = parsing_note or "text_fallback"
                return decoded, "text_fallback", final_note
        except Exception as e:
            logger.debug("UTF-8 decode failed: %s", e)

        logger.warning("⚠ No text extracted from PDF; it may be image-only (scan).")
        return "", "none", "no_text_extracted"

    # -------------------------
    # Simple extractors
    # -------------------------
    def extract_contact_info(self, text: str) -> Dict[str, Optional[str]]:
        email = EMAIL_RE.search(text)
        phone = PHONE_RE.search(text)
        gh = GITHUB_RE.search(text)
        li = LINKEDIN_RE.search(text)
        return {
            "email": email.group(0) if email else None,
            "phone": phone.group(0) if phone else None,
            "github": f"https://{gh.group(0)}" if gh else None,
            "linkedin": f"https://{li.group(0)}" if li else None,
        }

    def extract_name(self, text: str) -> Optional[str]:
        # Heuristic: first non-empty line that is not a section header
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if any(skip in low for skip in ["skills", "experience", "education", "projects", "summary", "contact"]):
                continue
            if 2 <= len(line.split()) <= 4 and re.match(r"^[A-Za-z .'\-]{2,}$", line):
                return line
        return None

    def extract_skills(self, text: str) -> Dict[str, List[str]]:
        text_lower = text.lower()
        found = defaultdict(set)
        for syn, (canonical, cat) in _skill_syn.items():
            if re.search(r"\b" + re.escape(syn) + r"\b", text_lower):
                found[cat].add(canonical)
        return {k: sorted(v) for k, v in found.items()}

    def extract_roles(self, text: str) -> List[str]:
        text_lower = text.lower()
        roles = set()
        for role, pats in ROLE_PATTERNS.items():
            for pat in pats:
                if pat in text_lower:
                    roles.add(role)
                    break
        return sorted(list(roles))

    def extract_experience_years(self, text: str) -> int:
        matches = re.findall(r"(\d{1,2})\+?\s*(?:years|yrs)\s+(?:of\s+)?experience", text.lower())
        if matches:
            try:
                nums = [int(m) for m in matches]
                return max(nums)
            except Exception:
                pass
        return 0

    def extract_education(self, text: str) -> List[Dict[str, str]]:
        degrees = []
        # Basic patterns (B.Tech/B.E./Bachelor/Master/PhD)
        patterns = [
            (r"b(?:\.tech|\.?tech|achelor)", "Bachelor"),
            (r"m(?:\.tech|\.?tech|aster)", "Master"),
            (r"(?:phd|ph\.d\.)", "PhD"),
        ]
        for pat, label in patterns:
            if re.search(pat, text, flags=re.IGNORECASE):
                degrees.append({"degree": label, "field": "Unknown"})
        return degrees

    def extract_work_experience(self, text: str) -> List[Dict[str, str]]:
        companies = []
        # look for "at Company" patterns
        for m in re.finditer(r"(?:at|@)\s+([A-Z][A-Za-z0-9 &\.\-]{2,50})", text):
            name = m.group(1).strip()
            companies.append({"company": name})
        # dedupe
        seen = set()
        out = []
        for c in companies:
            key = c["company"].lower()
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out[:5]

    def extract_hackathon_wins(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower()
        found = []
        wins = {"first": 0, "second": 0, "third": 0, "finalist": 0, "participant": 0}
        for kw in HACKATHON_KEYWORDS:
            if kw in text_lower:
                idx = text_lower.find(kw)
                start = max(0, idx - 120)
                end = min(len(text_lower), idx + 120)
                snippet = text[start:end]
                placement = "participant"
                if re.search(r"\b(winner|1st|first|champion|gold)\b", snippet):
                    placement = "first"
                elif re.search(r"\b(runner up|runner-up|2nd|second|silver)\b", snippet):
                    placement = "second"
                elif re.search(r"\b(3rd|third|bronze)\b", snippet):
                    placement = "third"
                wins[placement] += 1
                found.append({"context": snippet[:200], "placement": placement})
        score = wins["first"] * 10 + wins["second"] * 7 + wins["third"] * 5 + wins["finalist"] * 3 + wins["participant"]
        return {"total_hackathons": len(found), "achievements": found, "wins_breakdown": wins, "hackathon_score": score, "has_hackathon_experience": len(found)>0}

    # -------------------------
    # Main parse function
    # -------------------------
    def parse_resume(self, pdf_bytes: bytes = None, text: str = None) -> Dict[str, Any]:
        """
        Returns a dict with:
        name, contact, skills_by_category, all_skills, roles, experience_years,
        education, work_experience, hackathons, raw_text_preview, raw_text, total_text_length, parsing_library, parsing_note
        On failure returns {"error": "message", "raw_text": ...}
        """
        raw_text = ""
        parsing_library = "none"
        parsing_note = None
        
        try:
            if pdf_bytes:
                raw_text, parsing_library, parsing_note = self.extract_text_from_pdf(pdf_bytes)
            if not raw_text and text:
                raw_text = text
                parsing_library = "text_input"
            raw_text = (raw_text or "").strip()
            if not raw_text or len(raw_text) < 40:
                logger.info("parse_resume: no meaningful text extracted (len=%d)", len(raw_text))
                return {
                    "error": "No meaningful text to parse", 
                    "raw_text": raw_text[:500],
                    "parsing_library": parsing_library,
                    "parsing_note": parsing_note
                }
        except Exception as e:
            logger.exception("parse_resume extraction error: %s", e)
            return {
                "error": f"text extraction failed: {str(e)}", 
                "raw_text": "",
                "parsing_library": "error",
                "parsing_note": str(e)
            }

        contact = self.extract_contact_info(raw_text)
        name = self.extract_name(raw_text) or ""
        skills_by_category = self.extract_skills(raw_text)
        all_skills = sorted({s for cat in skills_by_category.values() for s in cat})
        roles = self.extract_roles(raw_text)
        experience_years = self.extract_experience_years(raw_text)
        education = self.extract_education(raw_text)
        work_experience = self.extract_work_experience(raw_text)
        hackathon_data = self.extract_hackathon_wins(raw_text)

        result = {
            "name": name,
            "contact": contact,
            "skills_by_category": skills_by_category,
            "all_skills": all_skills,
            "roles": roles,
            "experience_years": experience_years,
            "education": education,
            "work_experience": work_experience,
            "hackathons": hackathon_data,
            "raw_text_preview": raw_text[:500],
            "raw_text": raw_text,
            "total_text_length": len(raw_text),
            "parsing_library": parsing_library,
        }
        
        # Add parsing_note if there was an issue
        if parsing_note:
            result["parsing_note"] = parsing_note
        
        return result


# quick CLI test
if __name__ == "__main__":
    p = ImprovedResumeParser()
    sample = """
    John Doe
    john.doe@example.com | github.com/johndoe | +1-234-567-8900

    Senior Full-Stack Developer

    Technical Skills:
    React, JavaScript, TypeScript, Tailwind, Python, FastAPI, Docker, Kubernetes, PyTorch, TensorFlow, SQL, Postgres

    Experience:
    Software Engineer at Google (2020 - Present)
    """
    print(p.parse_resume(text=sample))