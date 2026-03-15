"""
ResumeIQ — Intelligent Resume Analysis API
Supports PDF, DOCX, and TXT resume formats with skill matching and improvement suggestions.
"""

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import PyPDF2
import re
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import io
import os
import uvicorn

# Configuration
MAX_FILE_SIZE_MB = 10
MAX_FILE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

app = FastAPI(title="ResumeIQ API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"], check=False)
    nlp = spacy.load("en_core_web_sm")


# ─── Text Extraction ─────────────────────────────────────────────────────────

def extract_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using PyPDF2."""
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def extract_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs)


def extract_from_txt(file_bytes: bytes) -> str:
    """Extract text from TXT file."""
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1")


def extract_resume_text(file_bytes: bytes, filename: str) -> str:
    """Extract text from resume based on file extension."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        return extract_from_pdf(file_bytes)
    if ext == ".docx":
        return extract_from_docx(file_bytes)
    if ext == ".txt":
        return extract_from_txt(file_bytes)
    raise ValueError(f"Unsupported format: {ext}. Use PDF, DOCX, or TXT.")


# ─── Text Preprocessing ──────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Clean and preprocess text for analysis."""
    text_lower = text.lower()
    pattern = r"[^a-zA-Z0-9+/#.\- ]"
    cleaned = re.sub(pattern, " ", text_lower)
    return preprocess(cleaned)


def preprocess(text: str) -> str:
    """Lemmatize and normalize text using spaCy."""
    doc = nlp(text)
    tokens = []
    for token in doc:
        if not token.is_punct and not token.is_space:
            tokens.append(token.lemma_)
    return " ".join(tokens)


# ─── Skills & Keywords ───────────────────────────────────────────────────────

# Expanded skills list for better matching
SKILLS_LIST = [
    "python", "java", "c++", "c#", "sql", "javascript", "typescript", "html", "css",
    "aws", "gcp", "azure", "docker", "kubernetes", "react", "angular", "vue", "node",
    "nodejs", "microservices", "machine", "learning", "deep", "data", "analysis",
    "system", "design", "distributed", "backend", "frontend", "fullstack", "full-stack",
    "cybersecurity", "cloud", "blockchain", "tensorflow", "pytorch", "scikit",
    "mongodb", "postgresql", "mysql", "redis", "kafka", "spark", "hadoop",
    "scala", "golang", "go", "rust", "graphql", "rest", "api", "agile", "scrum",
    "devops", "ci/cd", "jenkins", "terraform", "ansible", "linux", "git",
    "nlp", "computer", "vision", "data science", "excel", "tableau", "power bi",
    "jira", "figma", "testing", "automation", "selenium", "unit", "integration",
]


def extract_keywords_from_text(text: str, top_n: int = 50) -> list:
    """Extract important keywords using TF-IDF (single document)."""
    words = text.split()
    word_freq = {}
    for w in words:
        if len(w) > 2 and not w.isdigit():
            word_freq[w] = word_freq.get(w, 0) + 1
    sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_words[:top_n]]


def match_skills(text: str) -> set:
    """Find skills from our list that appear in text."""
    text_lower = text.lower()
    found = set()
    for skill in SKILLS_LIST:
        if skill in text_lower:
            found.add(skill)
    return found


def get_missing_keywords(jd_keywords: list, resume_words: set) -> list:
    """Find important JD keywords not present in resume."""
    resume_lower = {w.lower() for w in resume_words}
    missing = []
    for kw in jd_keywords:
        if kw.lower() not in resume_lower and len(kw) > 2:
            missing.append(kw)
    return missing[:20]  # Limit to top 20


# ─── Scoring Logic ───────────────────────────────────────────────────────────

def skill_overlap_score(resume: str, jd: str) -> float:
    resume_skills = match_skills(resume)
    jd_skills = match_skills(jd)
    if not jd_skills:
        return 0.5
    matched = resume_skills & jd_skills
    return len(matched) / len(jd_skills)


def experience_score(resume: str, jd: str) -> float:
    resume_numbers = re.findall(r"\d+", resume)
    jd_numbers = re.findall(r"\d+", jd)
    if not jd_numbers:
        return 0.5
    resume_exp = max([int(n) for n in resume_numbers if int(n) < 50], default=0)
    jd_exp = max([int(n) for n in jd_numbers if int(n) < 50], default=0)
    if jd_exp == 0:
        return 0.5
    if resume_exp >= jd_exp:
        return 1.0
    return min(1.0, resume_exp / jd_exp)


def calc_cosine_similarity(resume: str, jd: str) -> float:
    v = TfidfVectorizer(ngram_range=(1, 2), max_features=8000)
    vectors = v.fit_transform([resume, jd])
    sim = cosine_similarity(vectors[0:1], vectors[1:2])
    return float(sim[0][0])


def keyword_density_score(resume: str, jd: str) -> float:
    resume_words = set(resume.split())
    jd_words = set(jd.split())
    overlap = resume_words & jd_words
    return len(overlap) / len(jd_words) if jd_words else 0


def calculate_final_score(resume: str, jd: str) -> dict:
    cosine = calc_cosine_similarity(resume, jd)
    skill = skill_overlap_score(resume, jd)
    experience = experience_score(resume, jd)
    density = keyword_density_score(resume, jd)

    final_score = (0.40 * cosine + 0.25 * skill + 0.20 * experience + 0.15 * density) * 100

    return {
        "final_score": round(min(100, final_score), 2),
        "breakdown": {
            "tfidf_cosine": round(cosine * 100, 2),
            "skill_overlap": round(skill * 100, 2),
            "experience_match": round(experience * 100, 2),
            "keyword_density": round(density * 100, 2),
        },
    }


# ─── Improvement Suggestions ──────────────────────────────────────────────────

SKILL_SUGGESTIONS = {
    "python": ["Build a small project with FastAPI or Django", "Add Python certifications (e.g., PCPP)"],
    "aws": ["Complete AWS Cloud Practitioner or Solutions Architect", "Build a project using EC2, S3, Lambda"],
    "docker": ["Containerize an existing application", "Learn Docker Compose for multi-container apps"],
    "kubernetes": ["Complete Kubernetes basics tutorial", "Deploy a sample app to minikube"],
    "react": ["Build a portfolio or dashboard project", "Learn React Hooks and state management"],
    "sql": ["Practice complex queries on LeetCode/HackerRank", "Add database design projects"],
    "machine": ["Complete a Kaggle competition", "Add ML project with scikit-learn or TensorFlow"],
    "data": ["Add data visualization projects (Tableau, matplotlib)", "Include analytics case studies"],
    "devops": ["Set up CI/CD pipeline for a project", "Learn Terraform or Ansible"],
}


def generate_suggestions(missing_skills: list, missing_keywords: list) -> dict:
    """Generate improvement suggestions based on missing skills and keywords."""
    skills_to_add = []
    tools_to_learn = []
    resume_improvements = []

    for skill in missing_skills[:10]:
        skill_lower = skill.lower()
        skills_to_add.append(f"Add {skill} to your resume with concrete projects or experience")

        if skill_lower in SKILL_SUGGESTIONS:
            tools_to_learn.extend(SKILL_SUGGESTIONS[skill_lower][:1])

    for kw in missing_keywords[:5]:
        if kw not in [s for s in missing_skills]:
            resume_improvements.append(f"Include '{kw}' in your resume where relevant")

    if not tools_to_learn:
        tools_to_learn = [
            "Complete online courses (Coursera, Udemy, edX)",
            "Build side projects to demonstrate skills",
            "Get relevant certifications for the role",
        ]

    if not resume_improvements:
        resume_improvements = [
            "Use action verbs (Led, Developed, Implemented) in experience bullet points",
            "Quantify achievements with numbers and metrics",
            "Add a skills section with keywords from the job description",
            "Include relevant certifications and courses",
        ]

    return {
        "skills_to_add": list(dict.fromkeys(skills_to_add))[:8],
        "tools_to_learn": list(dict.fromkeys(tools_to_learn))[:6],
        "resume_improvements": list(dict.fromkeys(resume_improvements))[:6],
    }


def get_role_suitability(score: float) -> dict:
    """Return role suitability indicator."""
    if score >= 80:
        return {"level": "highly_suitable", "label": "Highly Suitable", "color": "success"}
    if score >= 60:
        return {"level": "suitable", "label": "Suitable", "color": "accent"}
    if score >= 40:
        return {"level": "moderate", "label": "Moderate Fit", "color": "warn"}
    return {"level": "needs_work", "label": "Needs Improvement", "color": "danger"}


# ─── API Routes ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.post("/api/analyze")
async def analyze_resume(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
):
    # Validate file type
    if not resume.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = os.path.splitext(resume.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Please upload PDF, DOCX, or TXT.",
        )

    if not job_description or not job_description.strip():
        raise HTTPException(status_code=400, detail="Job description cannot be empty.")

    # Read file with size limit
    resume_bytes = await resume.read()
    if len(resume_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
        )

    # Extract text
    try:
        raw_resume = extract_resume_text(resume_bytes, resume.filename)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract text from file: {str(e)}",
        )

    if not raw_resume or not raw_resume.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from the file. The file may be empty or corrupted.",
        )

    # Preprocess
    resume_clean = clean_text(raw_resume)
    jd_clean = clean_text(job_description)

    # Compute scores
    scores = calculate_final_score(resume_clean, jd_clean)
    score = scores["final_score"]

    # Skills analysis
    resume_skills = match_skills(resume_clean)
    jd_skills = match_skills(jd_clean)
    matched = resume_skills & jd_skills
    missing = jd_skills - resume_skills

    # Missing keywords (important JD terms not in resume)
    jd_keywords = extract_keywords_from_text(jd_clean, 30)
    resume_words = set(resume_clean.split())
    missing_keywords = get_missing_keywords(jd_keywords, resume_words)

    # Suggestions
    suggestions = generate_suggestions(list(missing), missing_keywords)

    # Role suitability
    role_suitability = get_role_suitability(score)

    return JSONResponse({
        "status": "success",
        "filename": resume.filename,
        "score": score,
        "breakdown": scores["breakdown"],
        "role_suitability": role_suitability,
        "skills": {
            "matched": sorted(list(matched)),
            "missing": sorted(list(missing)),
            "resume_total": len(resume_skills),
            "jd_total": len(jd_skills),
        },
        "missing_keywords": missing_keywords[:15],
        "suggestions": suggestions,
    })


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": "en_core_web_sm"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
