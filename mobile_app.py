import streamlit as st
import requests
import json
from datetime import datetime, timedelta
import io
import base64

st.set_page_config(
    page_title="Qloo Voice Scheduler",
    page_icon="🗓️",
    layout="wide"
)

API_BASE_URL = "http://localhost:8000"

def main():
    st.title("🗓️ Qloo Voice Scheduler")
    st.write("Voice-based scheduling assistant")
    
    tab1, tab2, tab3 = st.tabs(["Voice Input", "Schedule", "Settings"])
    
    with tab1:
        voice_interface()
    
    with tab2:
        schedule_interface()
    
    with tab3:
        settings_interface()

def voice_interface():
    st.header("Voice Input")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Text Input")
        text_input = st.text_area("Enter your scheduling request:", 
                                 placeholder="Schedule a meeting with John tomorrow at 2 PM")
        
        if st.button("Process Text"):
            if text_input:
                process_text_request(text_input)
    
    with col2:
        st.subheader("Audio Input")
        audio_file = st.file_uploader("Upload audio file", type=['wav', 'mp3', 'ogg'])
        
        if audio_file and st.button("Process Audio"):
            process_audio_request(audio_file)

def process_text_request(text):
    try:
        with st.spinner("Processing request..."):
            response = requests.post(
                f"{API_BASE_URL}/api/intent",
                json={"text": text}
            )
            
            if response.status_code == 200:
                result = response.json()
                st.success("Request processed successfully!")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.json(result)
                
                with col2:
                    if result.get("intent_type") == "schedule_event":
                        st.write("**Scheduling Event...**")
                        schedule_from_intent(result, text)
            else:
                st.error(f"Error: {response.status_code}")
                
    except Exception as e:
        st.error(f"Error processing request: {str(e)}")

def process_audio_request(audio_file):
    try:
        with st.spinner("Transcribing audio..."):
            files = {"audio": audio_file.getvalue()}
            response = requests.post(
                f"{API_BASE_URL}/api/voice/transcribe",
                files=files
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    st.success("Audio transcribed successfully!")
                    transcribed_text = result.get("transcribed_text", "")
                    st.write(f"**Transcribed:** {transcribed_text}")
                    
                    if transcribed_text:
                        process_text_request(transcribed_text)
                else:
                    st.error(f"Transcription failed: {result.get('error_message', 'Unknown error')}")
            else:
                st.error(f"Error: {response.status_code}")
                
    except Exception as e:
        st.error(f"Error processing audio: {str(e)}")

def schedule_from_intent(intent_result, original_text):
    try:
        entities = intent_result.get("entities", {})
        
        schedule_request = {
            "title": entities.get("title", "New Meeting"),
            "description": original_text,
            "duration": entities.get("duration", 60),
            "auto_schedule": False
        }
        
        response = requests.post(
            f"{API_BASE_URL}/api/schedule",
            json=schedule_request
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                st.success("Available time slots found!")
                
                slots = result.get("suggested_slots", [])
                if slots:
                    st.write("**Available Time Slots:**")
                    for i, slot in enumerate(slots[:5]):
                        start_time = datetime.fromisoformat(slot["start_time"].replace("Z", "+00:00"))
                        end_time = datetime.fromisoformat(slot["end_time"].replace("Z", "+00:00"))
                        
                        st.write(f"{i+1}. {start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%H:%M')} "
                                f"(Score: {slot['availability_score']:.2f})")
                else:
                    st.warning("No available time slots found")
            else:
                st.error(f"Scheduling failed: {result.get('message', 'Unknown error')}")
        else:
            st.error(f"Error: {response.status_code}")
            
    except Exception as e:
        st.error(f"Error scheduling event: {str(e)}")

def schedule_interface():
    st.header("Schedule")
    
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input("Start Date", datetime.now().date())
        
    with col2:
        end_date = st.date_input("End Date", datetime.now().date() + timedelta(days=7))
    
    if st.button("Get Schedule"):
        get_schedule(start_date, end_date)

def get_schedule(start_date, end_date):
    try:
        with st.spinner("Loading schedule..."):
            response = requests.get(
                f"{API_BASE_URL}/api/schedule",
                params={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                }
            )
            
            if response.status_code == 200:
                events = response.json()
                
                if events:
                    st.success(f"Found {len(events)} events")
                    
                    for event in events:
                        with st.expander(f"📅 {event['title']}"):
                            st.write(f"**Start:** {event['start_time']}")
                            st.write(f"**End:** {event['end_time']}")
                            if event.get('description'):
                                st.write(f"**Description:** {event['description']}")
                            if event.get('location'):
                                st.write(f"**Location:** {event['location']}")
                else:
                    st.info("No events found for the selected date range")
            else:
                st.error(f"Error: {response.status_code}")
                
    except Exception as e:
        st.error(f"Error getting schedule: {str(e)}")

def settings_interface():
    st.header("Settings")
    
    with st.form("user_preferences"):
        st.subheader("User Preferences")
        
        work_start = st.time_input("Work Start Time", value=datetime.strptime("09:00", "%H:%M").time())
        work_end = st.time_input("Work End Time", value=datetime.strptime("17:00", "%H:%M").time())
        
        timezone = st.selectbox("Timezone", ["UTC", "America/New_York", "America/Los_Angeles", "America/Chicago"])
        
        buffer_time = st.number_input("Buffer Time (minutes)", min_value=0, max_value=60, value=15)
        
        default_duration = st.number_input("Default Meeting Duration (minutes)", min_value=15, max_value=240, value=60)
        
        submitted = st.form_submit_button("Save Preferences")
        
        if submitted:
            st.success("Preferences saved successfully!")
    
    st.subheader("API Status")
    check_api_status()

def check_api_status():
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            result = response.json()
            st.success(f"API Status: {result.get('status', 'Unknown')}")
            st.write(f"Version: {result.get('version', 'Unknown')}")
        else:
            st.error("API is not responding")
    except Exception as e:
        st.error(f"Cannot connect to API: {str(e)}")

if __name__ == "__main__":
    main()