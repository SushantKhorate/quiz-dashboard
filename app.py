import streamlit as st
import random
from supabase import create_client, Client
from fpdf import FPDF

# --- Page Setup ---
st.set_page_config(page_title="Proctored Exam Portal", page_icon="📝", layout="wide")

# --- Initialize Supabase Connection Safely ---
@st.cache_resource
def init_supabase():
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None

supabase = init_supabase()

# --- Fallback Local Data ---
LOCAL_CANDIDATES = {
    "student1@gmail.com": "PASS123",
    "student2@gmail.com": "PASS456"
}

LOCAL_QUESTION_BANK = [
    {
        "id": i,
        "question_text": f"Question {i}: What is the output/result of concept #{i} in computer science?",
        "option_a": "Option A (Incorrect)",
        "option_b": f"Option B (Correct Answer {i})",
        "option_c": "Option C (Incorrect)",
        "option_d": "Option D (Incorrect)",
        "correct_option": 2
    }
    for i in range(1, 101)
]

# --- Initialize Session State ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "candidate_email" not in st.session_state:
    st.session_state.candidate_email = ""
if "questions" not in st.session_state:
    st.session_state.questions = []
if "warnings" not in st.session_state:
    st.session_state.warnings = 0
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "disqualified" not in st.session_state:
    st.session_state.disqualified = False
if "exam_finished" not in st.session_state:
    st.session_state.exam_finished = False
if "final_score" not in st.session_state:
    st.session_state.final_score = 0
if "fullscreen_active" not in st.session_state:
    st.session_state.fullscreen_active = False

# Handle Violation Callbacks from Query Params
if "action" in st.query_params:
    action = st.query_params["action"]
    if action == "violation":
        st.session_state.warnings += 1
        if st.session_state.warnings >= 3:
            st.session_state.disqualified = True
            st.session_state.exam_finished = True
        st.query_params.clear()
        st.rerun()

# --- Helper: PDF Certificate Generator ---
def generate_certificate(email, score):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_line_width(2)
    pdf.rect(10, 10, 277, 190)
    
    pdf.set_font('Arial', 'B', 28)
    pdf.cell(0, 40, 'CERTIFICATE OF PARTICIPATION', 0, 1, 'C')
    
    pdf.set_font('Arial', '', 18)
    pdf.cell(0, 20, 'This certificate is proudly awarded to:', 0, 1, 'C')
    
    pdf.set_font('Arial', 'B', 24)
    pdf.cell(0, 25, f'{email}', 0, 1, 'C')
    
    pdf.set_font('Arial', '', 16)
    pdf.cell(0, 20, f'For completing the examination with a score of {score}/30.', 0, 1, 'C')
    
    return pdf.output(dest='S').encode('latin1')

# ==========================================
# 1. LOGIN SCREEN
# ==========================================
if not st.session_state.logged_in and not st.session_state.exam_finished:
    st.title("🔒 Candidate Portal Login")
    st.write("Please authenticate with your registered candidate email and assigned passkey.")
    
    email_input = st.text_input("Enter Registered Email:", placeholder="student1@gmail.com").strip().lower()
    passkey_input = st.text_input("Enter Exam Passkey:", type="password", placeholder="PASS123").strip()
    
    if st.button("Authenticate Candidate", type="primary"):
        if email_input and passkey_input:
            authenticated = False
            has_attempted = False
            
            if supabase:
                try:
                    res = supabase.table("candidates").select("*").eq("email", email_input).eq("passkey", passkey_input).execute()
                    if res.data and len(res.data) > 0:
                        candidate = res.data[0]
                        authenticated = True
                        has_attempted = candidate.get("has_attempted", False)
                except Exception:
                    pass
            
            if not authenticated and email_input in LOCAL_CANDIDATES:
                if LOCAL_CANDIDATES[email_input] == passkey_input:
                    authenticated = True

            if authenticated:
                if has_attempted:
                    st.error("❌ You have already submitted or attempted this examination.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.candidate_email = email_input
                    
                    fetched_q = []
                    if supabase:
                        try:
                            q_res = supabase.table("questions").select("*").execute()
                            if q_res.data and len(q_res.data) >= 30:
                                fetched_q = q_res.data
                        except Exception:
                            pass
                    
                    if not fetched_q:
                        fetched_q = LOCAL_QUESTION_BANK
                        
                    st.session_state.questions = random.sample(fetched_q, min(len(fetched_q), 30))
                    st.rerun()
            else:
                st.error("❌ Invalid Email or Passkey combination.")
        else:
            st.warning("Please fill in both Email and Passkey fields.")

# ==========================================
# 2. PROCTORED EXAM WITH NON-BLOCKING ANTI-CHEAT
# ==========================================
elif st.session_state.logged_in and not st.session_state.exam_finished:

    # Initial Gate to Trigger Fullscreen natively via User Click
    if not st.session_state.fullscreen_active:
        st.subheader("🛡️ Proctoring Pre-Check")
        st.warning("This examination requires mandatory **Full-Screen Mode**. Exiting full-screen, switching tabs, or taking screenshots will register a strike penalty!")
        
        st.components.v1.html("""
            <div style="text-align: center; margin-top: 10px;">
                <button id="start-btn" style="background-color: #ff4b4b; color: white; border: none; padding: 16px 32px; font-size: 18px; font-weight: bold; border-radius: 8px; cursor: pointer;">
                    🚀 Request Full-Screen & Start Exam
                </button>
            </div>
            <script>
            document.getElementById('start-btn').addEventListener('click', function() {
                const docEl = window.parent.document.documentElement;
                if (docEl.requestFullscreen) {
                    docEl.requestFullscreen().catch(e => console.log(e));
                } else if (docEl.webkitRequestFullscreen) {
                    docEl.webkitRequestFullscreen().catch(e => console.log(e));
                }
                window.parent.location.search = '?fullscreen_ok=true';
            });
            </script>
        """, height=80)

        if "fullscreen_ok" in st.query_params:
            st.session_state.fullscreen_active = True
            st.query_params.clear()
            st.rerun()

    else:
        # Non-Blocking Anti-Cheat Suite Injection
        st.components.v1.html("""
            <div id="reenter-banner" style="display:none; position:fixed; top:0; left:0; width:100%; background:#d9534f; color:white; text-align:center; padding:12px; z-index:999999; font-weight:bold; font-size:16px;">
                ⚠️ FULLSCREEN EXITED! 
                <button id="reenter-btn" style="margin-left:15px; padding:6px 16px; background:white; color:#d9534f; border:none; font-weight:bold; border-radius:4px; cursor:pointer;">
                    Click Here to Re-enter Fullscreen
                </button>
            </div>

            <script>
            const doc = window.parent.document;
            const win = window.parent;
            const banner = document.getElementById('reenter-banner');
            const reenterBtn = document.getElementById('reenter-btn');

            function triggerViolation() {
                const currentUrl = new URL(win.location.href);
                currentUrl.searchParams.set('action', 'violation');
                win.location.href = currentUrl.toString();
            }

            // Re-enter Fullscreen Handler
            reenterBtn.addEventListener('click', () => {
                const docEl = doc.documentElement;
                if (docEl.requestFullscreen) {
                    docEl.requestFullscreen();
                } else if (docEl.webkitRequestFullscreen) {
                    docEl.webkitRequestFullscreen();
                }
                banner.style.display = 'none';
            });

            // 1. Prevent Text Selection, Copy, Cut, Paste & Context Menu
            doc.addEventListener('contextmenu', e => e.preventDefault());
            doc.addEventListener('copy', e => e.preventDefault());
            doc.addEventListener('cut', e => e.preventDefault());
            doc.addEventListener('paste', e => e.preventDefault());

            // 2. Block Keyboard Shortcuts (PrintScreen, Ctrl+C, Ctrl+V, F12)
            doc.addEventListener('keydown', e => {
                if (e.key === "PrintScreen" || 
                   (e.ctrlKey && (e.key === 'c' || e.key === 'u' || e.key === 's' || e.key === 'v')) || 
                   e.key === "F12") {
                    e.preventDefault();
                    triggerViolation();
                }
            });

            // 3. Monitor Fullscreen Exits
            doc.addEventListener('fullscreenchange', () => {
                if (!doc.fullscreenElement && !doc.webkitFullscreenElement) {
                    banner.style.display = 'block';
                    triggerViolation();
                } else {
                    banner.style.display = 'none';
                }
            });

            // 4. Tab Switching & Visibility Detection
            doc.addEventListener('visibilitychange', () => {
                if (doc.hidden) {
                    triggerViolation();
                }
            });
            </script>
        """, height=0)

        # Main Examination Interface
        st.warning(f"⚠️ **PROCTORED SESSION ACTIVE** | Candidate: `{st.session_state.candidate_email}`")
        
        col_info, col_strike = st.columns([3, 1])
        with col_strike:
            st.error(f"⚠️ Violations: {st.session_state.warnings} / 2 Allowed")

        # Disqualification Handler
        if st.session_state.warnings >= 3 or st.session_state.disqualified:
            if supabase:
                try:
                    supabase.table("candidates").update({"has_attempted": True}).eq("email", st.session_state.candidate_email).execute()
                    supabase.table("exam_attempts").insert({
                        "email": st.session_state.candidate_email,
                        "score": 0,
                        "status": "DISQUALIFIED",
                        "violation_count": st.session_state.warnings,
                        "violation_reasons": "Exceeded 2 anti-cheat warnings."
                    }).execute()
                except Exception:
                    pass
            st.session_state.exam_finished = True
            st.rerun()

        # Questions Form
        with st.form("exam_form"):
            st.subheader("Randomized Questions (30 Total)")
            st.divider()
            
            for idx, q in enumerate(st.session_state.questions):
                st.markdown(f"**Question {idx+1}:** {q['question_text']}")
                options = [q['option_a'], q['option_b'], q['option_c'], q['option_d']]
                
                selected = st.radio(
                    f"Select answer for Q{idx+1}:", 
                    options, 
                    index=None, 
                    key=f"q_{q['id']}"
                )
                st.session_state.user_answers[q['id']] = selected
                st.divider()

            submit_btn = st.form_submit_button("Submit Exam Responses", type="primary")
            
            if submit_btn:
                score = 0
                for q in st.session_state.questions:
                    user_ans = st.session_state.user_answers.get(q['id'])
                    opts = [q['option_a'], q['option_b'], q['option_c'], q['option_d']]
                    correct_idx = q.get('correct_option', 1) - 1
                    if 0 <= correct_idx < len(opts) and user_ans == opts[correct_idx]:
                        score += 1
                
                st.session_state.final_score = score
                
                if supabase:
                    try:
                        supabase.table("candidates").update({"has_attempted": True}).eq("email", st.session_state.candidate_email).execute()
                        supabase.table("exam_attempts").insert({
                            "email": st.session_state.candidate_email,
                            "score": score,
                            "status": "COMPLETED",
                            "violation_count": st.session_state.warnings,
                            "answers_json": st.session_state.user_answers
                        }).execute()
                    except Exception:
                        pass
                
                st.session_state.exam_finished = True
                st.rerun()

# ==========================================
# 3. RESULTS & CERTIFICATE DOWNLOAD
# ==========================================
if st.session_state.exam_finished:
    if st.session_state.disqualified or st.session_state.warnings >= 3:
        st.error("⛔ **EXAMINATION DISQUALIFIED**")
        st.write("You were flagged for violating examination security policies 3 times. Your score has been invalidated.")
    else:
        st.balloons()
        st.success("🎉 **EXAMINATION COMPLETED SUCCESSFULLY**")
        
        col_res1, col_res2 = st.columns(2)
        with col_res1:
            st.metric("Candidate Email", st.session_state.candidate_email)
        with col_res2:
            st.metric("Final Score", f"{st.session_state.final_score} / 30")
        
        st.divider()
        
        pdf_bytes = generate_certificate(st.session_state.candidate_email, st.session_state.final_score)
        st.download_button(
            label="📄 Download Participation Certificate (PDF)",
            data=pdf_bytes,
            file_name=f"Certificate_{st.session_state.candidate_email}.pdf",
            mime="application/pdf",
            type="primary"
        )
