import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
import time

# --- 1. PASSWORD PROTECTION ---
st.set_page_config(page_title="Blue Diamond Bulletin", page_icon="📢")

# Simple security gate
password = st.sidebar.text_input("Access Code", type="password")
if password != "BD10":  # Change this to your desired password
    st.info("Please enter the access code in the sidebar to begin.")
    st.stop()


# --- 2. DATA SETUP ---
@st.cache_resource
def get_gsheet_client():
    # For local testing, this uses your credentials.json
    # When you go live on Streamlit Cloud, we will use 'Secrets'
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file('credentials.json', scopes=scopes)
    return gspread.authorize(creds)


try:
    client = get_gsheet_client()
    sh = client.open_by_key("1vFIFSFWhyKOv3bL_RFIF9S5gYy8-5Ej-8-aUrOM-r8U")
    worksheet = sh.get_worksheet(0)
    all_records = worksheet.get_all_records()
    headers = worksheet.row_values(1)
    groups = [h for h in headers if h not in ['Name', 'Chat_ID']]
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()


def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- 3. UI BUILDER ---
st.title("📢 Blue Diamond Officers Announcement Builder")
st.write("Fill out the sections below. Use the button at the bottom to add more.")

if 'section_count' not in st.session_state:
    st.session_state.section_count = 1

full_bulletin_data = []

for i in range(st.session_state.section_count):
    with st.container(border=True):
        st.subheader(f"Section {i + 1}")
        s = st.text_input(f"Subject", key=f"s_{i}", placeholder="e.g., Leadership Updates")
        d = st.text_area(f"Details (Bulleted List)", key=f"d_{i}", placeholder="• Item 1\n• Item 2")
        full_bulletin_data.append({"subject": s, "details": d})

if st.button("➕ Add Another Section"):
    st.session_state.section_count += 1
    st.rerun()

# --- 4. RECIPIENT SELECTION ---
st.divider()
st.subheader("👥 Select Recipients")

# New field for the sender's name
sender_name = st.text_input("Your Name", placeholder="e.g., Brother Jestoni")

selected_groups = st.multiselect("Which groups should receive this?", groups)
send_to_all = st.checkbox("🚨 SEND TO ALL OFFICERS", value=False)

# --- 5. BROADCAST LOGIC ---
if st.button("🚀 SEND BROADCAST", type="primary", use_container_width=True):
    # Determine recipients
    final_list = []
    if send_to_all:
        final_list = all_records
    else:
        for person in all_records:
            for group in selected_groups:
                if str(person.get(group)).strip().lower() == "yes":
                    if person not in final_list:
                        final_list.append(person)
                    break

    if not final_list:
        st.warning("No recipients found! Please select a group.")
    else:
        # Build the message
        parts = []
        for sec in full_bulletin_data:
            subj = escape_html(sec['subject']).strip()
            det = escape_html(sec['details']).strip()
            if subj:
                parts.append(f"<b><u>{subj.upper()}</u></b>\n{det}")

        formatted_msg = "\n\n———\n\n".join(parts)

        # sender signature
        if sender_name:
            # We add a couple of line breaks and the signature
            formatted_msg += f"\n\n<i>Sent from {escape_html(sender_name)}</i>"

        # Send process
        success_count = 0
        progress_bar = st.progress(0)

        BOT_TOKEN = "7673357117:AAEYynKrvT2vVtJSxs-lTIciu4XJXyv7Hjc"

        for idx, person in enumerate(final_list):
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": str(person['Chat_ID']),
                "text": formatted_msg,
                "parse_mode": "HTML",
                "link_preview_options": {"is_disabled": True}
            }
            try:
                r = requests.post(url, json=payload)
                if r.status_code == 200:
                    success_count += 1
            except:
                pass
            progress_bar.progress((idx + 1) / len(final_list))
            time.sleep(0.05)

        st.success(f"Done! Broadcast sent to {success_count} officers.")

        # Admin Report
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                      data={"chat_id": "222361137", "text": f"✅ Web Broadcast Complete: {success_count} sent."})