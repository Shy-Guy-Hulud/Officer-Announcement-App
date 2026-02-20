import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
import time

# --- 1. PASSWORD PROTECTION ---
st.set_page_config(page_title="Officer Announcements", page_icon="📢")

# Initialize session state to keep the user logged in
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# If not logged in, show the login screen
if not st.session_state.authenticated:
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.write("## 🔐 Access Required")
        pass_input = st.text_input("Enter Access Code", type="password")

        # CHANGED: Reference the secret here
        if pass_input == st.secrets["access_code"]:
            st.session_state.authenticated = True
            st.rerun()
        elif pass_input != "":
            st.error("Incorrect Code")
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
        d = st.text_area(f"Details (Bulleted List)", key=f"d_{i}", placeholder="• Item 1\n• Item 2")
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
if send_to_all:
    preview_list = [person['Name'] for person in all_records]
elif selected_groups:
    for person in all_records:
        for group in selected_groups:
            if str(person.get(group)).strip().lower() == "yes":
                if person['Name'] not in preview_list:
                    preview_list.append(person['Name'])
                break

if preview_list:
    # We sort the list alphabetically so it's easy to find a specific name
    sorted_names = sorted(preview_list)

    with st.expander(f"👁️ View Recipients ({len(sorted_names)} people total)"):
        # We join the names with a newline and a bullet point
        bulleted_list = "\n".join([f"* {name}" for name in sorted_names])
        st.markdown(bulleted_list)
else:
    st.caption("No recipients selected yet.")

# --- NEW: LIVE PREVIEW ---
st.divider()
st.subheader("🖼️ Announcement Preview")

with st.container(border=True):
    # Construct the message text exactly as it will appear
    preview_parts = []
    for sec in full_bulletin_data:
        subj = sec['subject'].strip()
        det = sec['details'].strip()
        if subj:
            preview_parts.append(f"**{subj.upper()}**\n{det}")

    preview_text = "\n\n---\n\n".join(preview_parts)
    if sender_name:
        preview_text += f"\n\n*Sent from {sender_name}*"

    # UI Layout for the preview
    if uploaded_files:
        col1, col2 = st.columns([1, 2])
        with col1:
            # Show the first uploaded file as the primary preview image
            first_file = uploaded_files[0]
            if first_file.type.startswith("image"):
                st.image(first_file, caption="Primary Attachment")
            else:
                st.info(f"📄 {first_file.name} (Document)")
        with col2:
            st.markdown(preview_text)
    else:
        # Text-only preview
        st.markdown(preview_text if preview_text else "*(Start typing above to see preview)*")

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
                parts.append(f"<b><u>{subj}</u></b>\n{det}")

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
            success = False

            try:
                # SCENARIO A: No files - Send standard Text message
                if not uploaded_files:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": chat_id,
                        "text": formatted_msg,
                        "parse_mode": "HTML",
                        "link_preview_options": {"is_disabled": True}
                    }
                    r = requests.post(url, json=payload)

                # SCENARIO B: Single File (Image or PDF)
                elif len(uploaded_files) == 1:
                    file = uploaded_files[0]
                    # Reset file pointer to beginning after each recipient
                    file.seek(0)

                    # Determine if it's a photo or document
                    method = "sendPhoto" if file.type.startswith("image") else "sendDocument"
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

                    files = {method.replace("send", "").lower(): file}
                    payload = {
                        "chat_id": chat_id,
                        "caption": formatted_msg,
                        "parse_mode": "HTML"
                    }
                    r = requests.post(url, data=payload, files=files)

                # SCENARIO C: Multiple Files (Media Group / Album)
                else:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
                    media = []
                    files = {}

                    for i, f in enumerate(uploaded_files):
                        f.seek(0)
                        file_input_name = f"file{i}"
                        files[file_input_name] = f

                        # Attach the caption only to the FIRST item in the group
                        media_item = {
                            "type": "photo" if f.type.startswith("image") else "document",
                            "media": f"attach://{file_input_name}"
                        }
                        if i == 0:
                            media_item["caption"] = formatted_msg
                            media_item["parse_mode"] = "HTML"
                        media.append(media_item)

                    payload = {"chat_id": chat_id, "media": requests.utils.quote(str(media).replace("'", '"'))}
                    # Note: MediaGroup is complex; usually easier to send text THEN files if multi-file.
                    r = requests.post(url, data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)

                if r.status_code == 200:
                    success_count += 1

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