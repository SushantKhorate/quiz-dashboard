import streamlit as st
import random
import time
from supabase import create_client, Client
from fpdf import FPDF
import base64

# --- Streamlit Page Setup ---
st.set_page_config(page_title="Proctored Exam Portal", page_icon="📝", layout="wide")

# --- Initialize Supabase Connection ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Session State Management ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "candidate_email" not in st.session_state:
    st.session_state.candidate_email = ""
if "exam_started" not in st.session_state:
    st.session_state.exam_started = False
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

# --- Helper: Certificate Generator (PDF) ---
def generate_certificate(email, score):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_line_width(2)
    pdf.rect(10, 10, 277, 190)
    
    pdf.set_font('Arial', 'B', 28)
    pdf.cell(0, 40, 'CERTIFICATE OF PARTICIPATION', 0, 1, 'C')
    
    pdf.set_font('Arial', '', 18)
    pdf.cell(0, 20, 'This is proudly presented to:', 0, 1, 'C')
    
    pdf.set_font('Arial', 'B', 24)
    pdf.cell(0, 25, f'{email}', 0, 1, 'C')
    
    pdf.set_font('Arial', '', 16)
    pdf.cell(0, 20, f'For completing the examination with a score of {score}/30.', 0, 1, 'C')
    
    return pdf.output(dest='S').encode('latin1')

# ==========================================
# 1. LOGIN SCREEN (Email & Passkey)
# ==========================================
if not st.session_state.logged_in and not st.session_state.exam_finished:
    st.title("🔒 Candidate Portal Login")
    
    email_input = st.text_input("Enter your Registered Email:")
    passkey_input = st.text_input("Enter your Exam Passkey:", type="password")
    
    if st.button("Authenticate & Start Test"):
        if email_input and passkey_input:
            res = supabase.table("candidates").select("*").eq("email", email_input).eq("passkey", passkey_input).execute()
            
            if len(res.data) > 0:
                candidate = res.data[0]
                if candidate["has_attempted"]:
                    st.error("❌ You have already submitted or attempted this examination.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.candidate_email = email_input
                    
                    # Fetch 30 random questions from Supabase
                    q_res = supabase.table("questions").select("*").execute()
                    all_questions = q_res.data
                    st.session_state.questions = random.sample(all_questions, min(len(all_questions), 30))
                    st.rerun()
            else:
                st.error("Invalid Email or Passkey combination.")
        else:
            st.warning("Please fill in all fields.")

# ==========================================
# 2. PROCTORED EXAMINATION SCREEN
# ==========================================
elif st.session_state.logged_in and not st.session_state.exam_finished:
    
    # Client-side Anti-Cheat JavaScript Injector
    st.components.v1.html("""
        <script>
        const doc = window.parent.document;
        
        // Disable Right-Click, Cut, Copy, Paste, & Text Selection
        doc.addEventListener('contextmenu', e => e.preventDefault());
        doc.addEventListener('copy', e => e.preventDefault());
        doc.addEventListener('cut', e => e.preventDefault());
        doc.addEventListener('paste', e => e.preventDefault());
        
        // Block Keyboard Shortcuts (PrintScreen, Ctrl+C, Ctrl+U, F12)
        doc.addEventListener('keydown', e => {
            if (e.key === "PrintScreen" || 
               (e.ctrlKey && (e.key === 'c' || e.key === 'u' || e.key === 's')) || 
               e.key === "F12") {
                e.preventDefault();
                alert("⚠️ Screenshot and Copy shortcuts are strictly disabled!");
            }
        });

        // Detect Window/Tab Blur (App switching / Floating windows)
        window.parent.addEventListener('blur', () => {
            console.log("Tab/Window Focus Lost!");
        });
        </script>
    """, height=0)

    st.warning(f"⚠️ **PROCTORING ACTIVE**: Candidate `{st.session_state.candidate_email}`. Do NOT copy text, exit full screen, or switch windows. You will be disqualified on the 3rd strike!")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        st.error(f"Warnings: {st.session_state.warnings} / 2")
        if st.button("🚨 Simulate Violation (For Testing)"):
            st.session_state.warnings += 1
            if st.session_state.warnings >= 3:
                st.session_state.disqualified = True
                st.session_state.exam_finished = True
            st.rerun()

    # Disqualification Logic
    if st.session_state.warnings >= 3 or st.session_state.disqualified:
        supabase.table("candidates").update({"has_attempted": True}).eq("email", st.session_state.candidate_email).execute()
        supabase.table("exam_attempts").insert({
            "email": st.session_state.candidate_email,
            "score": 0,
            "status": "DISQUALIFIED",
            "violation_count": st.session_state.warnings,
            "violation_reasons": "Exceeded maximum anti-cheat violations (App switch / Copy / Screenshot attempts)."
        }).execute()
        st.session_state.exam_finished = True
        st.rerun()

    # Render Exam Form
    with st.form("exam_form"):
        st.subheader("Answer the following 30 questions:")
        
        for idx, q in enumerate(st.session_state.questions):
            st.markdown(f"**Q{idx+1}: {q['question_text']}**")
            options = [q['option_a'], q['option_b'], q['option_c'], q['option_d']]
            selected = st.radio(f"Select answer for Q{idx+1}:", options, index=None, key=f"q_{q['id']}")
            st.session_state.user_answers[q['id']] = selected
            st.divider()

        submit_btn = st.form_submit_button("Finalize and Submit Exam")
        
        if submit_btn:
            # Calculate Score
            score = 0
            for q in st.session_state.questions:
                user_ans = st.session_state.user_answers.get(q['id'])
                opts = [q['option_a'], q['option_b'], q['option_c'], q['option_d']]
                correct_text = opts[q['correct_option'] - 1] if q['correct_option'] else None
                if user_ans == correct_text:
                    score += 1
            
            # Save Record to Supabase
            supabase.table("candidates").update({"has_attempted": True}).eq("email", st.session_state.candidate_email).execute()
            supabase.table("exam_attempts").insert({
                "email": st.session_state.candidate_email,
                "score": score,
                "status": "COMPLETED",
                "violation_count": st.session_state.warnings,
                "answers_json": st.session_state.user_answers
            }).execute()
            
            st.session_state.final_score = score
            st.session_state.exam_finished = True
            st.rerun()

# ==========================================
# 3. RESULT & CERTIFICATE SCREEN
# ==========================================
if st.session_state.exam_finished:
    if st.session_state.disqualified or st.session_state.warnings >= 3:
        st.error("⛔ **EXAMINATION DISQUALIFIED**")
        st.write("You were flagged for violating exam anti-cheating regulations 3 times. Your score has been voided.")
    else:
        st.balloons()
        st.success("🎉 **EXAMINATION SUBMITTED SUCCESSFULLY**")
        score = st.session_state.get("final_score", 0)
        st.write(f"Candidate: **{st.session_state.candidate_email}**")
        st.write(f"Your Total Score: **{score} / 30**")
        
        # Download Certificate Button
        pdf_bytes = generate_certificate(st.session_state.candidate_email, score)
        st.download_button(
            label="📄 Download Participation Certificate",
            data=pdf_bytes,
            file_name=f"Certificate_{st.session_state.candidate_email}.pdf",
            mime="application/pdf"
        )
