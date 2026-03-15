/**
 * ResumeIQ — AI Resume Matcher
 * Frontend logic for intelligent resume analysis
 */

(function () {
  'use strict';

  const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt'];
  const MAX_FILE_SIZE_MB = 10;
  const MAX_FILE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

  const API_BASE = (function () {
    if (typeof window !== 'undefined' && window.location && window.location.origin) {
      const origin = window.location.origin;
      if (origin.startsWith('http://') || origin.startsWith('https://')) {
        return origin;
      }
    }
    return 'http://localhost:8000';
  })();

  const zone = document.getElementById('uploadZone');
  const fileInput = document.getElementById('resumeFile');
  const fileSelected = document.getElementById('fileSelected');
  const fileName = document.getElementById('fileName');

  if (!zone || !fileInput || !fileSelected || !fileName) return;

  function isValidFile(file) {
    if (!file) return { ok: false, msg: 'No file selected.' };
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      return { ok: false, msg: 'Unsupported format. Use PDF, DOCX, or TXT.' };
    }
    if (file.size > MAX_FILE_BYTES) {
      return { ok: false, msg: 'File too large. Maximum size is ' + MAX_FILE_SIZE_MB + 'MB.' };
    }
    return { ok: true };
  }

  function setFile(f) {
    const result = isValidFile(f);
    if (!result.ok) {
      showError(result.msg);
      return;
    }
    const dt = new DataTransfer();
    dt.items.add(f);
    fileInput.files = dt.files;
    fileName.textContent = f.name;
    fileSelected.classList.add('show');
    hideError();
  }

  function hideError() {
    const box = document.getElementById('errorBox');
    if (box) box.classList.remove('show');
  }

  fileInput.addEventListener('change', function () {
    const f = fileInput.files[0];
    if (f) setFile(f);
  });

  zone.addEventListener('dragover', function (e) {
    e.preventDefault();
    e.stopPropagation();
    zone.classList.add('drag-over');
  });

  zone.addEventListener('dragleave', function () {
    zone.classList.remove('drag-over');
  });

  zone.addEventListener('drop', function (e) {
    e.preventDefault();
    e.stopPropagation();
    zone.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  });

  window.analyzeResume = async function () {
    const btn = document.getElementById('analyzeBtn');
    const errorBox = document.getElementById('errorBox');
    const results = document.getElementById('results');

    if (!btn || !errorBox || !results) return;

    errorBox.classList.remove('show');
    results.classList.remove('show');

    const file = fileInput.files[0];
    const jdEl = document.getElementById('jobDesc');
    const jd = jdEl ? jdEl.value.trim() : '';

    const fileCheck = isValidFile(file);
    if (!fileCheck.ok) {
      showError(fileCheck.msg);
      return;
    }
    if (!jd) {
      showError('Please paste a job description.');
      return;
    }

    btn.classList.add('loading');
    btn.disabled = true;

    try {
      const fd = new FormData();
      fd.append('resume', file);
      fd.append('job_description', jd);

      const url = API_BASE + '/api/analyze';
      const res = await fetch(url, { method: 'POST', body: fd });

      const text = await res.text();
      let data = null;
      if (text && text.trim()) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          if (res.ok) {
            throw new Error('Invalid response from server.');
          }
          throw new Error(res.status === 404 ? 'API not found. Is the server running?' : 'Server error. Try again later.');
        }
      }

      if (!res.ok) {
        const msg = (data && data.detail)
          ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
          : (res.status === 404 ? 'API not found. Start the server: uvicorn main:app --reload --port 8000' : 'Analysis failed.');
        throw new Error(msg);
      }

      if (!data || typeof data.score === 'undefined') {
        throw new Error('Invalid response from server.');
      }

      renderResults(data);
    } catch (err) {
      if (err.name === 'TypeError' && (err.message.includes('fetch') || err.message.includes('Failed to fetch'))) {
        showError('Cannot reach the server. Make sure the backend is running: uvicorn main:app --reload --port 8000');
      } else {
        showError(err.message || 'Analysis failed.');
      }
    } finally {
      btn.classList.remove('loading');
      btn.disabled = false;
    }
  };

  function showError(msg) {
    const box = document.getElementById('errorBox');
    const msgEl = document.getElementById('errorMsg');
    if (box && msgEl) {
      msgEl.textContent = msg;
      box.classList.add('show');
    }
  }

  function renderResults(data) {
    const score = data.score;
    const bd = data.breakdown || {};
    const skills = data.skills || { matched: [], missing: [] };
    const missingKeywords = data.missing_keywords || [];
    const suggestions = data.suggestions || { skills_to_add: [], tools_to_learn: [], resume_improvements: [] };
    const roleSuitability = data.role_suitability || { label: '', color: 'muted' };

    // Score ring
    const ringFill = document.getElementById('ringFill');
    if (ringFill) {
      const circumference = 283;
      const offset = circumference - (score / 100) * circumference;
      ringFill.style.strokeDashoffset = offset;

      let ringColor = '#00e5ff';
      if (score >= 75) ringColor = '#00e676';
      else if (score >= 50) ringColor = '#00e5ff';
      else if (score >= 30) ringColor = '#ffb300';
      else ringColor = '#ff3d57';
      ringFill.style.stroke = ringColor;
    }

    animateNumber('scoreNum', 0, score, 1200);

    let badge = '';
    let title = '';
    let desc = '';
    if (score >= 75) {
      badge = '<span class="score-badge badge-excellent">✦ Excellent Match</span>';
      title = 'Strong Candidate';
      desc = 'Your resume is highly aligned with this role. You have the skills and experience the employer is looking for.';
    } else if (score >= 55) {
      badge = '<span class="score-badge badge-good">◆ Good Match</span>';
      title = 'Solid Fit';
      desc = 'Good alignment overall. Address the missing skills and tailor your language to strengthen your application.';
    } else if (score >= 35) {
      badge = '<span class="score-badge badge-moderate">▲ Moderate Match</span>';
      title = 'Partial Fit';
      desc = 'Some alignment exists, but significant gaps remain. Consider building missing skills before applying.';
    } else {
      badge = '<span class="score-badge badge-low">✕ Low Match</span>';
      title = 'Needs Work';
      desc = 'Your resume lacks many of the required qualifications. Upskilling or targeting different roles is recommended.';
    }

    setText('scoreTitle', title);
    setText('scoreDesc', desc);

    const badgeEl = document.getElementById('scoreBadge');
    if (badgeEl) badgeEl.innerHTML = badge;

    // Role suitability badge
    const roleEl = document.getElementById('roleSuitability');
    if (roleEl && roleSuitability.label) {
      roleEl.textContent = 'Role: ' + roleSuitability.label;
      roleEl.className = 'role-suitability-badge ' + (roleSuitability.color || '');
      roleEl.style.display = 'inline-flex';
    } else if (roleEl) {
      roleEl.style.display = 'none';
    }

    // Breakdown bars
    const metrics = [
      ['cosine', bd.tfidf_cosine || 0],
      ['skill', bd.skill_overlap || 0],
      ['exp', bd.experience_match || 0],
      ['density', bd.keyword_density || 0]
    ];

    metrics.forEach(function (pair) {
      const key = pair[0];
      const val = Number(pair[1]);
      const mEl = document.getElementById('m-' + key);
      const bEl = document.getElementById('b-' + key);
      if (mEl) mEl.textContent = val.toFixed(1) + '%';
      if (bEl) {
        setTimeout(function () {
          bEl.style.width = val + '%';
        }, 200);
      }
    });

    // Skills
    renderSkills('matchedSkills', skills.matched || [], 'matched');
    renderSkills('missingSkills', skills.missing || [], 'missing');

    // Missing keywords
    renderKeywords('missingKeywords', missingKeywords);

    // Suggestions
    renderList('skillsToAdd', suggestions.skills_to_add || []);
    renderList('toolsToLearn', suggestions.tools_to_learn || []);
    renderList('resumeImprovements', suggestions.resume_improvements || []);

    const resultsEl = document.getElementById('results');
    if (resultsEl) {
      resultsEl.classList.add('show');
      resultsEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderSkills(elId, skills, type) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (!skills || !skills.length) {
      el.innerHTML = '<span class="no-skills">None detected</span>';
      return;
    }
    el.innerHTML = skills.map(function (s) {
      return '<span class="skill-tag ' + type + '">' + escapeHtml(s) + '</span>';
    }).join('');
  }

  function renderKeywords(elId, keywords) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (!keywords || !keywords.length) {
      el.innerHTML = '<span class="no-skills">All important keywords found in your resume.</span>';
      return;
    }
    el.innerHTML = keywords.map(function (kw) {
      return '<span class="keyword-tag">' + escapeHtml(kw) + '</span>';
    }).join('');
  }

  function renderList(elId, items) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (!items || !items.length) {
      el.innerHTML = '<li class="no-skills">No specific suggestions for this category.</li>';
      return;
    }
    el.innerHTML = items.map(function (item) {
      return '<li>' + escapeHtml(item) + '</li>';
    }).join('');
  }

  function animateNumber(elId, start, end, duration) {
    const el = document.getElementById(elId);
    if (!el) return;
    const range = end - start;
    const startTime = performance.now();

    function step(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(start + range * eased);
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
})();
