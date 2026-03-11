import streamlit as st
import extra_streamlit_components as stx
import gspread
from google.oauth2.service_account import Credentials
import requests
import time
from datetime import datetime, timedelta

# --- 1. PASSWORD PROTECTION ---
st.set_page_config(page_title="Officer Announcements", page_icon="📢")

# --- COOKIE MANAGER SETUP ---
# Adding a 'key' ensures it stays consistent across refreshes
cookie_manager = stx.CookieManager(key="announcement_cookies")

# The library now handles the "readiness" check internally.
# We can just proceed to getting the cookie.
auth_cookie = cookie_manager.get("is_authenticated")

# Check if the "is_authenticated" cookie already exists
auth_cookie = cookie_manager.get("is_authenticated")

# Sync the cookie to session state
if auth_cookie == "true":
    st.session_state["authenticated"] = True

# Initialize session state to keep the user logged in
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.title("🔐 Officer Announcement Tool")
    with st.form("login_form"):
        pwd_input = st.text_input("Enter Access Code", type="password")
        if st.form_submit_button("Login"):
            if pwd_input == st.secrets["access_code"]:
                # 1. Update session state
                st.session_state["authenticated"] = True

                # 2. Save a cookie that lasts for 7 days
                cookie_manager.set(
                    "is_authenticated",
                    "true",
                    expires_at=datetime.now() + timedelta(days=7)
                )
                st.rerun()
            else:
                st.error("Invalid Code")
    st.stop()

# --- 2. DATA SETUP ---
@st.cache_resource
def get_gsheet_client():
    # UPDATED: Pulling from Streamlit Secrets instead of a local file
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    # This uses the dictionary you'll paste into the Streamlit dashboard
    creds_info = st.secrets["google_credentials"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)

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
st.title("📢 Officer Announcements")
st.write("Fill out the sections below. Click \"Add Another Topic\" to add more topics.")

if 'section_count' not in st.session_state:
    st.session_state.section_count = 1

full_bulletin_data = []

for i in range(st.session_state.section_count):
    with st.container(border=True):
        st.subheader(f"Topic {i + 1}")
        s = st.text_input(f"Subject", key=f"s_{i}", placeholder="e.g., Leadership Updates")
        d = st.text_area(f"Details - Tip: draft message in telegram, then copy/paste in here to keep formatting and emojis", key=f"d_{i}", placeholder="• Item 1\n• Item 2")
        full_bulletin_data.append({"subject": s, "details": d})

if st.button("➕ Add Another Topic"):
    st.session_state.section_count += 1
    st.rerun()

# New field for the sender's name
st.divider()
st.subheader("🫵🏽 Sender")
sender_name = st.text_input("Your Name (so brethren know who sent the announcement)", placeholder="e.g., Brother Jestoni")

# --- NEW: FILE UPLOAD SECTION ---
st.divider()
st.subheader("📎 Attachments (Optional)")
uploaded_files = st.file_uploader(
    "Upload images or a PDF",
    accept_multiple_files=True,
    type=['png', 'jpg', 'jpeg', 'pdf']
)

# --- 4. RECIPIENT SELECTION ---
st.divider()
st.subheader("👥 Select Recipients")

selected_groups = st.multiselect("Which groups should receive this?", groups)
send_to_all = st.checkbox("🚨 SEND TO ALL OFFICERS", value=False)

# --- NEW: LIVE RECIPIENT PREVIEW ---
preview_list = []
missing_id_list = []  # Track names of people missing Chat_IDs

if send_to_all:
    for person in all_records:
        preview_list.append(person['Name'])
        # Check if Chat_ID is missing or empty
        if not str(person.get('Chat_ID')).strip():
            missing_id_list.append(person['Name'])
elif selected_groups:
    for person in all_records:
        for group in selected_groups:
            if str(person.get(group)).strip().lower() == "yes":
                if person['Name'] not in preview_list:
                    preview_list.append(person['Name'])
                    # Check if Chat_ID is missing or empty
                    if not str(person.get('Chat_ID')).strip():
                        missing_id_list.append(person['Name'])
                break

# Display the warning if anyone is missing a Chat_ID
if missing_id_list:
    st.error(f"⚠️ **Missing Telegram IDs:** {', '.join(missing_id_list)}. These officers will not receive the announcement.")

if preview_list:
    sorted_names = sorted(preview_list)
    with st.expander(f"👁️ View Recipients ({len(sorted_names)} people total)"):
        bulleted_list = "\n".join([f"* {name}" for name in sorted_names])
        st.markdown(bulleted_list)
else:
    st.caption("No recipients selected yet.")

# --- UPDATED: LIVE PREVIEW ---
st.divider()
st.subheader("🖼️ Announcement Preview")

with st.container(border=True):
    preview_parts = []
    for sec in full_bulletin_data:
        subj = sec['subject'].strip()
        det = sec['details'].strip()
        if subj:
            preview_parts.append(f"<b><u>{subj}</u></b><br>{det}")

    preview_text = "\n\n---\n\n".join(preview_parts)
    if sender_name:
        preview_text += f"\n\n*Sent from {sender_name}*"

    # UI Layout for the preview
    if uploaded_files:
        # 1. Identify the first image as the 'Cover'
        first_image = next((f for f in uploaded_files if f.type.startswith("image")), None)
        other_files = [f for f in uploaded_files if f != first_image]

        col1, col2 = st.columns([1, 2])
        with col1:
            if first_image:
                st.image(first_image, caption="Main Announcement Image")
            else:
                st.info("ℹ️ No image: Text will be sent first.")

        with col2:
            st.markdown(preview_text.replace("\n", "<br>"), unsafe_allow_html=True)

        # 2. Show the "Follow-up" blurb for other files
        if other_files:
            st.write("---")
            st.caption("📂 **Additional files to be sent as separate messages:**")
            for f in other_files:
                icon = "🖼️" if f.type.startswith("image") else "📄"
                st.markdown(f"{icon} `{f.name}`")
    else:
        if preview_text:
            st.markdown(preview_text.replace("\n", "<br>"), unsafe_allow_html=True)
        else:
            st.markdown("*(Start typing above to see preview)*")

# --- 5. BROADCAST LOGIC ---
if st.button("🚀 SEND ANNOUNCEMENT(S)", type="primary", use_container_width=True):
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
                parts.append(f"<b><u>{subj}</u></b>\n\n{det}")

        formatted_msg = "\n\n———\n\n".join(parts)

        # sender signature
        if sender_name:
            # We add a couple of line breaks and the signature
            formatted_msg += f"\n\n<i>Sent from {escape_html(sender_name)}</i>"

        # Send process
        success_count = 0
        progress_bar = st.progress(0)

        BOT_TOKEN = st.secrets["telegram_token"]

        for idx, person in enumerate(final_list):
            chat_id = str(person['Chat_ID'])

            try:
                # SCENARIO A: No files
                if not uploaded_files:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": chat_id,
                        "text": formatted_msg,
                        "parse_mode": "HTML",
                        "link_preview_options": {"is_disabled": True}
                    }
                    r = requests.post(url, json=payload)
                    # ADD THIS:
                    if r.status_code == 200:
                        success_count += 1

                # SCENARIO B & C: With files
                elif uploaded_files:
                    first_image = next((f for f in uploaded_files if f.type.startswith("image")), None)

                    if first_image:
                        first_image.seek(0)
                        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                        files = {"photo": first_image}
                        payload = {"chat_id": chat_id, "caption": formatted_msg, "parse_mode": "HTML"}
                        r = requests.post(url, data=payload, files=files)
                    else:
                        url_text = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                        payload_text = {"chat_id": chat_id, "text": formatted_msg, "parse_mode": "HTML"}
                        r = requests.post(url_text, json=payload_text)

                    # ADD THIS:
                    if r.status_code == 200:
                        success_count += 1
                        # Send remaining files...
                        other_files = [f for f in uploaded_files if f != first_image]
                        for f in other_files:
                            f.seek(0)

                    # 2. Send all REMAINING files (PDFs or extra images) one by one
                    if r.status_code == 200:
                        for f in other_files:
                            f.seek(0)
                            method = "sendPhoto" if f.type.startswith("image") else "sendDocument"
                            file_key = "photo" if f.type.startswith("image") else "document"

                            url_file = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
                            # No caption here to keep the chat clean, or use f.name as a tiny caption
                            requests.post(url_file, data={"chat_id": chat_id}, files={file_key: f})

            except Exception as e:
                print(f"Error sending to {person['Name']}: {e}")

            progress_bar.progress((idx + 1) / len(final_list))
            time.sleep(0.1)  # Slightly longer delay to avoid Telegram rate limits with files

        # 1. Define your personal ID
        MY_CHAT_ID = "222361137"

        # 2. Check if the broadcast was sent to anyone OTHER than you
        # We check if any of the recipients in final_list had a Chat_ID different from yours
        was_sent_to_others = any(str(person['Chat_ID']) != MY_CHAT_ID for person in final_list)

        if was_sent_to_others:
            sender = sender_name if sender_name else "An Officer"
            admin_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

            admin_payload = {
                "chat_id": MY_CHAT_ID,
                "text": f"✅ <b>Heads up - broadcast generated by</b>\n\n<b>Sender:</b> {escape_html(sender)}\n<b>Recipients:</b> {success_count} officers",
                "parse_mode": "HTML"
            }

            try:
                # We use json=admin_payload to stay consistent with your other requests
                requests.post(admin_url, json=admin_payload)
            except Exception as e:
                # We log this to the console so it doesn't interrupt the UI for the user
                print(f"Admin notification failed: {e}")

        st.success(f"✅ Done! Sent to {success_count} officers with {len(uploaded_files)} attachment(s).")

# --- 6. LOGOUT SECTION (OPTIONAL BUT RECOMMENDED) ---
st.divider()
with st.expander("🔐 App Settings"):
    if st.button("Logout and Lock App"):
        # 1. Clear the cookie so the browser forgets the login
        cookie_manager.delete("is_authenticated")
        # 2. Clear the session state
        st.session_state["authenticated"] = False
        # 3. Refresh to show the login screen
        st.rerun()