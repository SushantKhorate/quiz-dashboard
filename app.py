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

# Query Parameters Handler for Anti-Cheat Callbacks
query_params = st.query_params
if "action" in query_params:
    action = query_params["action"]
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
# 2. FULL SCREEN GATEWAY & PROCTORED EXAM
# ==========================================
elif st.session_state.logged_in and not st.session_state.exam_finished:

    if not st.session_state.fullscreen_active:
        st.subheader("🛡️ Proctoring Pre-Check")
        st.warning("This examination requires mandatory **Full-Screen Mode**. Exiting full-screen, switching apps, or attempting screenshots will add a strike violation!")
        
        col_center = st.columns([1, 2, 1])[1]
        with col_center:
            if st.button("🚀 Enable Full-Screen & Start Examination", type="primary", use_container_width=True):
                st.session_state.fullscreen_active = True
                st.rerun()

    else:
        # Full Anti-Cheat Monitoring Suite (Fires directly in top window context)
        st.components.v1.html("""
            <script>
            const doc = window.parent.document;
            const win = window.parent;

            // Automatically request full screen on parent window load
            if (!doc.fullscreenElement && !doc.webkitFullscreenElement) {
                const docEl = doc.documentElement;
                if (docEl.requestFullscreen) {
                    docEl.requestFullscreen().catch(err => console.log(err));
                } else if (docEl.webkitRequestFullscreen) {
                    docEl.webkitRequestFullscreen().catch(err => console.log(err));
                }
            }

            function recordViolation(reason) {
                alert("🚨 CHEAT WARNING: " + reason + "\\nA penalty strike has been registered!");
                const currentUrl = new URL(win.location.href);
                currentUrl.searchParams.set('action', 'violation');
                win.location.href = currentUrl.toString();
            }

            // 1. Context Menu & Selection Prevention
            doc.addEventListener('contextmenu', e => e.preventDefault());
            doc.addEventListener('copy', e => e.preventDefault());
            doc.addEventListener('cut', e => e.preventDefault());
            doc.addEventListener('paste', e => e.preventDefault());

            // 2. Keyboard Shortcut Prevention
            doc.addEventListener('keydown', e => {
                if (e.key === "PrintScreen" || 
                   (e.ctrlKey && (e.key === 'c' || e.key === 'u' || e.key === 's' || e.key === 'v')) || 
                   e.key === "F12") {
                    e.preventDefault();
                    recordViolation("Screenshot / Copy keyboard shortcut attempt detected.");
                }
            });

            // 3. Full Screen Exit Detection
            doc.addEventListener('fullscreenchange', () => {
                if (!doc.fullscreenElement && !doc.webkitFullscreenElement) {
                    recordViolation("Exited Full-Screen mode!");
                }
            });

            // 4. Tab Switch & App Blur Detection
            doc.addEventListener('visibilitychange', () => {
                if (doc.hidden) {
                    recordViolation("Switched browser tabs or minimized window!");
                }
            });
            
            win.addEventListener('blur', () => {
                recordViolation("Focus lost! Floating window or background app used.");
            });
            </script>
        """, height=0)

        # Header Information
        st.warning(f"⚠️ **PROCTORED SESSION ACTIVE** | Candidate: `{st.session_state.candidate_email}`")
        
        col_info, col_strike = st.columns([3, 1])
        with col_strike:
            st.error(f"⚠️ Violations: {st.session_state.warnings} / 2 Allowed")
            if st.button("🚨 Test Violation Trigger"):
                st.session_state.warnings += 1
                if st.session_state.warnings >= 3:
                    st.session_state.disqualified = True
                    st.session_state.exam_finished = True
                st.rerun()

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

        # Exam Questions Form
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
