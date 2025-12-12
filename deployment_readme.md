# PilotBid Pro - Streamlit Deployment Guide

## Overview
This is a Streamlit conversion of the PilotBid Pro application, maintaining full functionality from the original React version while being deployable on Streamlit Cloud or any Python environment.

## Features Retained
✅ CSV upload and parsing  
✅ Flight pairing filtering (duration, aircraft, dates, search)  
✅ Preference-based scoring system  
✅ AI-powered schedule analysis (Gemini)  
✅ Automated schedule generation (3 strategies)  
✅ Statistics and visualizations  
✅ All scoring weights and algorithms  
✅ Calendar-style schedule display  

## Local Deployment

### Prerequisites
- Python 3.8 or higher
- pip

### Installation Steps

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application**
   ```bash
   streamlit run app.py
   ```

3. **Access the app**
   - Open your browser to `http://localhost:8501`

## Streamlit Cloud Deployment

### One-Click Deploy

1. **Fork/Upload to GitHub**
   - Create a new repository on GitHub
   - Upload `app.py` and `requirements.txt`

2. **Deploy to Streamlit Cloud**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Sign in with GitHub
   - Click "New app"
   - Select your repository
   - Set Main file path to `app.py`
   - Click "Deploy"

3. **Configure Secrets (Optional)**
   - In Streamlit Cloud dashboard, go to app settings
   - Add secrets if needed (like default API keys)

## Usage Instructions

### 1. Upload CSV File
- Click the file uploader on the home screen
- Select your airline's monthly pairing CSV
- CSV format should match:
  ```
  Pairing,Pre-assigned,Duration,AC,Departure,Arrival,Pairing details,Block hours
  ```

### 2. Filter Pairings
Use the sidebar to filter:
- **Search**: Enter airport codes or pairing numbers
- **Duration**: Adjust max trip length
- **Aircraft**: Select specific aircraft types
- **Dates**: Set date range

### 3. Add Preferences
In the Pairings tab:
- Click "Add New Preference"
- Choose preference type (e.g., "Block Specific Date Off")
- Enter details (dates, airports, etc.)
- Click "Add"

Preference types available:
- Block Specific Date Off
- Block Day of Week (e.g., all Sundays)
- Limit Trip Duration
- Avoid Red-Eye Arrivals
- Limit Flights per Day
- Maximize Earnings
- Prefer Airport/Route
- Prefer Departure Time
- Avoid Airport

### 4. View Ranked Pairings
- Pairings are automatically scored based on preferences
- Higher scores = better matches
- Green badges = matches your preferences
- Red badges = violates your preferences

### 5. Generate Schedules
Go to "Generated Calendars" tab:
- Click "Generate Schedules"
- View 3 optimized monthly schedules:
  - **Plan A**: Max earnings (highest block hours)
  - **Plan B**: Lifestyle & comfort (shorter trips)
  - **Plan C**: Weekends free

### 6. View Statistics
- Trip duration distribution chart
- Aircraft type breakdown pie chart
- Summary statistics

### 7. Ask AI
- Enter your Gemini API key
- Ask questions about your filtered pairings
- Get intelligent recommendations

## API Key Setup

### Getting a Gemini API Key
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key
5. Paste it in the "Ask AI" tab when needed

## CSV Format Requirements

Your CSV must have these columns:
- `Pairing`: Pairing number/ID
- `Pre-assigned`: Pre-assignment status
- `Duration`: Trip duration in days
- `AC`: Aircraft type
- `Departure`: Departure date/time (format: "Oct 12,2025 12:15")
- `Arrival`: Arrival date/time (format: "Oct 12,2025 18:45")
- `Pairing details`: Route details (e.g., "PTY - MIA - PTY")
- `Block hours`: Flight hours (format: "6:30")

## Scoring System

The app uses a weighted scoring algorithm:

| Preference Type | Weight |
|----------------|--------|
| Maximize Earnings | +2 per block hour |
| Preferred Route | +30 |
| Time Window | +20 |
| Max Duration | +15 |
| Max Legs/Day | +15 |
| Red Eye Avoidance | -50 |
| Avoid Airport | -100 |
| Day Off Conflict | -40 per day |
| Specific Date Conflict | -500 |

## Schedule Generation Logic

The automated schedule builder:
1. Respects 88-hour monthly block limit
2. Ensures 10-hour minimum rest between flights
3. Avoids blocked dates completely
4. Prevents overlapping pairings
5. Maximizes objective (earnings, comfort, or weekends)
6. Calculates days off based on calendar coverage

## Troubleshooting

### CSV Upload Fails
- Verify column names match exactly
- Check date format is "Month DD,YYYY HH:MM"
- Ensure no empty rows

### AI Not Working
- Verify API key is correct
- Check internet connection
- Ensure API key has not exceeded quota

### App Runs Slowly
- Reduce number of pairings (use date filters)
- Limit preferences to top priorities
- Clear browser cache

## Differences from Original React App

### What's Changed:
- **UI Framework**: React → Streamlit (Python-based)
- **Deployment**: Node.js/Vite → Python/Streamlit Cloud
- **Styling**: Tailwind CSS → Streamlit + Custom CSS
- **State Management**: React hooks → Streamlit session state

### What's the Same:
- All scoring algorithms identical
- Same preference system
- Same filtering logic
- Same schedule generation strategies
- Same AI integration (Gemini)
- All calculations and business logic preserved

## Performance Notes

- App handles up to 500+ pairings efficiently
- Filtering and scoring happens in real-time
- Schedule generation takes 2-5 seconds
- AI responses typically take 3-10 seconds

## Support

For issues or questions:
1. Check this README
2. Verify CSV format
3. Test with sample data
4. Review Streamlit logs in terminal

## License

Original application concept and logic from PilotBid Pro.
Streamlit conversion maintains all functionality for airline pilot schedule optimization.
