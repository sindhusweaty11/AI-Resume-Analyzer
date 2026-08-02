from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
import os, re, json, time
from datetime import datetime, timezone

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE_DIR, 'Uploads')
ANALYSIS_DIR = os.path.join(BASE_DIR, 'Test_analysis')
ALL_JSON = os.path.join(ANALYSIS_DIR, 'all_analyses.json')

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=BASE_DIR)

ROLE_SKILLS = {
    'Software Engineer': ['python','java','c++','algorithms','data structures'],
    'Data Analyst': ['sql','excel','python','tableau','pandas'],
    'Data Scientist': ['python','machine learning','pandas','numpy','statistics'],
    'Frontend Developer': ['javascript','react','html','css','frontend'],
}

COMMON_SKILLS = set(sum([v for v in ROLE_SKILLS.values()], []))


def extract_text_from_pdf(path):
    if PdfReader is None:
        return ''
    try:
        reader = PdfReader(path)
        texts = []
        for p in reader.pages:
            try:
                texts.append(p.extract_text() or '')
            except Exception:
                pass
        return '\n'.join(texts)
    except Exception:
        return ''


def extract_name(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for l in lines[:10]:
        if re.match(r"^[A-Z][a-z]+\s+[A-Z][a-z]+", l):
            return l.strip()
    return ''


def find_skills(text):
    text_l = text.lower()
    found = set()
    skills = list(COMMON_SKILLS) + ['sql','excel','tableau','django','flask','react','node','aws','docker','kubernetes','git','pandas','numpy']
    for s in skills:
        if s in text_l:
            found.add(s)
    return sorted(found)


def find_education(text):
    ed = []
    patterns = ['bachelor','master','b.sc','m.sc','phd','degree','diploma']
    for p in patterns:
        if p in text.lower():
            ed.append(p)
    return ed


def find_experience(text):
    m = re.findall(r"(\d+)\+?\s+years", text.lower())
    if m:
        return [{'years': int(m[0])}]
    if 'experience' in text.lower():
        return [{'years': 1}]
    return []


def find_projects(text):
    parts = []
    for l in text.splitlines():
        if 'project' in l.lower():
            parts.append(l.strip())
    return parts[:5]


def find_certifications(text):
    certs = []
    for l in text.splitlines():
        if any(k in l.lower() for k in ['certificate','certified','certification']):
            certs.append(l.strip())
    return certs


def rewrite_resume(text, missing_skills=None, target_role=None):
    if not text or not text.strip():
        return 'No resume text was found to rewrite.'

    text = text.rstrip()
    added_skills = []
    if missing_skills:
        added_skills = [s.strip() for s in missing_skills if s and s.strip()]
        added_skills = sorted(dict.fromkeys(added_skills), key=str.lower)

    if added_skills:
        skills_line = ', '.join(added_skills)
        match = re.search(r'(?im)^skills\s*[:\-]?\s*(.*)$', text, re.MULTILINE)
        if match:
            start, end = match.start(), match.end()
            line_end = text.find('\n', start)
            if line_end == -1:
                line_end = len(text)
            line_text = text[start:line_end]
            if ':' in line_text:
                base, current = line_text.split(':', 1)
                current = current.strip()
                if current:
                    new_line = f"{base}: {current}, {skills_line}"
                else:
                    new_line = f"{base}: {skills_line}"
            else:
                new_line = f"{line_text} {skills_line}"
            text = text[:start] + new_line + text[line_end:]
        else:
            text += f"\n\nSkills added: {skills_line}"

    return text


def get_role_skills(role):
    return ROLE_SKILLS.get(role, list(COMMON_SKILLS))


def analyze_text(text, target_role=None):
    name = extract_name(text)
    skills_found = find_skills(text)
    education = find_education(text)
    experience = find_experience(text)
    projects = find_projects(text)
    certifications = find_certifications(text)
    role_skills = get_role_skills(target_role or 'Software Engineer')
    missing = [s for s in role_skills if s not in skills_found]
    if role_skills:
        ats_score = int((len(role_skills)-len(missing))/len(role_skills)*100)
    else:
        ats_score = 0
    other_roles = []
    for r, sk in ROLE_SKILLS.items():
        overlap = len(set(sk).intersection(set(skills_found)))
        score = int((overlap / max(1, len(sk))) * 100)
        if r != target_role:
            other_roles.append({'role': r, 'score': score})
    other_roles = sorted(other_roles, key=lambda x: -x['score'])[:6]

    roadmap = {
        'Week 1': ['Brush up fundamentals', 'Read key docs'],
        'Week 2': ['Build small project', 'Practice problems'],
        'Week 3': ['Study advanced topics', 'Mock interviews'],
        'Week 4': ['Apply to jobs', 'Refine resume']
    }

    suggestions = ['Highlight projects', 'Add measurable achievements', 'List relevant keywords']
    final_recommendation = 'to be successfull for this role  Improve missing skills to increase your score.'

    return {
        'name': name,
        'skills_found': skills_found,
        'education': education,
        'experience': experience,
        'projects': projects,
        'certifications': certifications,
        'ats_score': ats_score,
        'missing_skills': missing,
        'other_roles': other_roles,
        'roadmap': roadmap,
        'suggestions': suggestions,
        'final_recommendation': final_recommendation
    }


def save_analysis(analysis, uploaded_filename=None):
    analysis_record = dict(analysis)
    analysis_record['timestamp'] = datetime.now(timezone.utc).isoformat()
    analysis_record['uploaded_filename'] = uploaded_filename
    arr = []
    if os.path.exists(ALL_JSON):
        try:
            with open(ALL_JSON, 'r', encoding='utf-8') as f:
                arr = json.load(f)
        except Exception:
            arr = []
    arr.append(analysis_record)
    with open(ALL_JSON, 'w', encoding='utf-8') as f:
        json.dump(arr, f, indent=2)


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'Index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'resume' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['resume']
    role = request.form.get('role')
    filename = f.filename or 'resume.pdf'
    filename = secure_filename(filename)
    ts = time.strftime('%Y%m%d%H%M%S')
    save_path = os.path.join(UPLOAD_DIR, f"{ts}_{filename}")
    f.save(save_path)
    text = extract_text_from_pdf(save_path)
    missing_skills = [s for s in get_role_skills(role or 'Software Engineer') if s not in find_skills(text)]
    rewritten = rewrite_resume(text, missing_skills=missing_skills, target_role=role)
    analysis = analyze_text(text, target_role=role)
    analysis['rewritten_resume'] = rewritten
    analysis['original_text'] = text
    analysis['missing_skills'] = missing_skills
    save_analysis(analysis, uploaded_filename=os.path.basename(save_path))
    return jsonify(analysis)


@app.route('/api/analyses', methods=['GET'])
def api_analyses():
    if os.path.exists(ALL_JSON):
        return send_file(ALL_JSON, mimetype='application/json')
    return jsonify([])


@app.route('/analyses')
def analyses_page():
    if os.path.exists(ALL_JSON):
        with open(ALL_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = []
    return jsonify(data)


if __name__ == '__main__':
    HOST = os.environ.get('APP_HOST', '0.0.0.0')
    PORT = int(os.environ.get('APP_PORT', 5000))
    app.run(host=HOST, port=PORT, debug=True)