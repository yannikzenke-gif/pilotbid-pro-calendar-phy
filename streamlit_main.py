import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any
import google.generativeai as genai
import os

# Page config
st.set_page_config(
    page_title="PilotBid Pro",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stButton > button {
        width: 100%;
    }
    .pairing-card {
        border: 1px solid #e2e8f0;
        border-radius: 0.75rem;
        padding: 1.25rem;
        margin-bottom: 1rem;
        background: white;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
    .score-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 0.5rem;
        font-weight: 600;
        font-size: 0.875rem;
    }
    .score-high {
        background: #d1fae5;
        color: #065f46;
    }
    .score-medium {
        background: #dbeafe;
        color: #1e40af;
    }
    .score-low {
        background: #fee2e2;
        color: #991b1b;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'pairings' not in st.session_state:
    st.session_state.pairings = None
if 'preferences' not in st.session_state:
    st.session_state.preferences = []
if 'ai_response' not in st.session_state:
    st.session_state.ai_response = ""
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = "Pairings"
if 'generated_schedules' not in st.session_state:
    st.session_state.generated_schedules = []

# Helper functions
def parse_csv(uploaded_file):
    """Parse the uploaded CSV file"""
    df = pd.read_csv(uploaded_file)
    
    # Parse dates
    date_format = '%b %d,%Y %H:%M'
    df['departureTime'] = pd.to_datetime(df['Departure'], format=date_format)
    df['arrivalTime'] = pd.to_datetime(df['Arrival'], format=date_format)
    
    # Parse block hours
    def parse_block_hours(time_str):
        if pd.isna(time_str) or str(time_str).strip() == '':
            return 0.0
        parts = str(time_str).split(':')
        return float(parts[0]) + float(parts[1])/60 if len(parts) == 2 else 0.0
    
    df['blockHoursDecimal'] = df['Block hours'].apply(parse_block_hours)
    
    # Extract layovers
    df['layovers'] = df['Pairing details'].apply(
        lambda x: list(set([s.strip() for s in str(x).split('-') if s.strip()]))
    )
    
    # Calculate duration if not present
    if 'Duration' not in df.columns:
        df['Duration'] = (df['arrivalTime'] - df['departureTime']).dt.days + 1
    
    return df

def score_pairing(pairing, preferences):
    """Score a single pairing based on preferences"""
    score = 0
    matches = []
    
    SCORE_WEIGHTS = {
        'STRATEGY_MONEY': 2,
        'ROUTE': 30,
        'TIME_WINDOW': 20,
        'MAX_DURATION': 15,
        'MAX_LEGS_PER_DAY': 15,
        'AVOID_RED_EYE': -50,
        'AVOID_AIRPORT': -100,
        'DAY_OF_WEEK_OFF': -40,
        'SPECIFIC_DATE_OFF': -500,
    }
    
    for pref in preferences:
        pref_type = pref['type']
        pref_value = pref['value']
        
        if pref_type == 'STRATEGY_MONEY':
            money_points = round(pairing['blockHoursDecimal'] * SCORE_WEIGHTS['STRATEGY_MONEY'])
            score += money_points
            if pairing['blockHoursDecimal'] > 15:
                matches.append("High Earnings ($$$)")
        
        elif pref_type == 'SPECIFIC_DATE_OFF':
            date_to_avoid = pd.to_datetime(pref_value)
            flight_days = pd.date_range(pairing['departureTime'], pairing['arrivalTime'], freq='D')
            if any(date_to_avoid.date() == d.date() for d in flight_days):
                score += SCORE_WEIGHTS['SPECIFIC_DATE_OFF']
                matches.append(f"Conflicts with {date_to_avoid.strftime('%b %d')} (Violated)")
        
        elif pref_type == 'DAY_OF_WEEK_OFF':
            day_to_avoid = int(pref_value)
            flight_days = pd.date_range(pairing['departureTime'], pairing['arrivalTime'], freq='D')
            if any(d.dayofweek == (day_to_avoid + 6) % 7 for d in flight_days):
                score += SCORE_WEIGHTS['DAY_OF_WEEK_OFF']
                matches.append("Works on a requested Day Off (Violated)")
            else:
                score += 10
                matches.append("Keeps preferred weekday free")
        
        elif pref_type == 'AVOID_RED_EYE':
            arr_hour = pairing['arrivalTime'].hour
            if 0 <= arr_hour <= 7:
                score += SCORE_WEIGHTS['AVOID_RED_EYE']
                matches.append(f"Red Eye Arrival ({arr_hour}:00)")
        
        elif pref_type == 'MAX_LEGS_PER_DAY':
            total_legs = len(pairing['layovers']) + 1
            legs_per_day = total_legs / pairing['Duration']
            max_legs = int(pref_value)
            if legs_per_day <= max_legs:
                score += SCORE_WEIGHTS['MAX_LEGS_PER_DAY']
                matches.append(f"Low workload (~{round(legs_per_day)} legs/day)")
        
        elif pref_type == 'ROUTE':
            if pref_value.upper() in str(pairing['Pairing details']).upper():
                score += SCORE_WEIGHTS['ROUTE']
                matches.append(f"Route includes {pref_value}")
        
        elif pref_type == 'TIME_WINDOW':
            start_hour, end_hour = map(int, pref_value.split('-'))
            dep_hour = pairing['departureTime'].hour
            if start_hour <= dep_hour <= end_hour:
                score += SCORE_WEIGHTS['TIME_WINDOW']
                matches.append(f"Departure between {start_hour}:00-{end_hour}:00")
        
        elif pref_type == 'MAX_DURATION':
            max_days = int(pref_value)
            if pairing['Duration'] <= max_days:
                score += SCORE_WEIGHTS['MAX_DURATION']
                matches.append(f"Duration under {max_days} days")
        
        elif pref_type == 'AVOID_AIRPORT':
            if pref_value.upper() in str(pairing['Pairing details']).upper():
                score += SCORE_WEIGHTS['AVOID_AIRPORT']
                matches.append(f"Avoids {pref_value} (Violated)")
    
    return score, list(set(matches))

def rank_pairings(df, preferences):
    """Rank all pairings based on preferences"""
    scores = []
    matches_list = []
    
    for idx, row in df.iterrows():
        score, matches = score_pairing(row, preferences)
        scores.append(score)
        matches_list.append(matches)
    
    df['score'] = scores
    df['matches'] = matches_list
    
    return df.sort_values('score', ascending=False)

def generate_schedules(df, preferences):
    """Generate optimized monthly schedules"""
    MAX_MONTHLY_BLOCK_HOURS = 88
    MIN_REST_HOURS = 10
    
    schedules = []
    
    # Plan A: Max Earnings
    money_prefs = preferences + [{'type': 'STRATEGY_MONEY', 'value': 'true', 'label': 'Max Earnings'}]
    money_schedule = build_schedule(df, money_prefs, "Plan A: Max Earnings", 
                                   "Prioritizes high block-hour trips to maximize pay")
    schedules.append(money_schedule)
    
    # Plan B: Lifestyle
    lifestyle_prefs = preferences.copy()
    if not any(p['type'] == 'MAX_DURATION' for p in lifestyle_prefs):
        lifestyle_prefs.append({'type': 'MAX_DURATION', 'value': '3', 'label': 'Short Trips'})
    lifestyle_schedule = build_schedule(df, lifestyle_prefs, "Plan B: Lifestyle & Comfort",
                                       "Prioritizes shorter trips and user preferences")
    schedules.append(lifestyle_schedule)
    
    # Plan C: Weekends Free
    weekend_prefs = preferences + [
        {'type': 'DAY_OF_WEEK_OFF', 'value': '6', 'label': 'Saturday'},
        {'type': 'DAY_OF_WEEK_OFF', 'value': '0', 'label': 'Sunday'}
    ]
    weekend_schedule = build_schedule(df, weekend_prefs, "Plan C: Weekends Free",
                                     "Attempts to keep Saturdays and Sundays free")
    schedules.append(weekend_schedule)
    
    return schedules

def build_schedule(df, preferences, name, description):
    """Build a single optimized schedule"""
    ranked_df = rank_pairings(df.copy(), preferences)
    
    selected = []
    total_block_hours = 0
    
    for idx, pairing in ranked_df.iterrows():
        if total_block_hours + pairing['blockHoursDecimal'] > 88:
            continue
        
        if pairing['score'] < -100:
            continue
        
        # Check for conflicts with blocked dates
        conflict = False
        for pref in preferences:
            if pref['type'] == 'SPECIFIC_DATE_OFF':
                date_to_avoid = pd.to_datetime(pref['value'])
                flight_days = pd.date_range(pairing['departureTime'], pairing['arrivalTime'], freq='D')
                if any(date_to_avoid.date() == d.date() for d in flight_days):
                    conflict = True
                    break
        
        if conflict:
            continue
        
        # Check overlap with already selected
        has_overlap = False
        for sel in selected:
            if (pairing['departureTime'] < sel['arrivalTime'] + timedelta(hours=10) and
                pairing['arrivalTime'] + timedelta(hours=10) > sel['departureTime']):
                has_overlap = True
                break
        
        if has_overlap:
            continue
        
        selected.append(pairing)
        total_block_hours += pairing['blockHoursDecimal']
    
    # Calculate days off
    work_days = set()
    for p in selected:
        for d in pd.date_range(p['departureTime'], p['arrivalTime'], freq='D'):
            work_days.add(d.date())
    
    days_off = 30 - len(work_days)
    
    return {
        'name': name,
        'description': description,
        'pairings': selected,
        'total_block_hours': round(total_block_hours, 2),
        'days_off': days_off,
        'flight_count': len(selected)
    }

def get_ai_response(pairings_df, query, api_key):
    """Get AI response using Gemini"""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Prepare context
        context_pairings = pairings_df.head(30)[['Pairing', 'AC', 'Duration', 'Pairing details', 'Block hours']].to_dict('records')
        
        prompt = f"""
You are an intelligent assistant for an airline pilot using a bidding app called "PilotBid Pro".

The pilot has filtered their monthly schedule and is asking a question about the remaining available flights.

Here is a sample of the filtered pairings:
{json.dumps(context_pairings, indent=2, default=str)}

User Question: "{query}"

Please provide a helpful, professional, and concise answer.
If suggesting specific pairings, refer to them by their Pairing ID.
Highlight specific pros/cons like "good for maximizing block hours" or "easy turn-around".
If the list seems empty or irrelevant to the query, advise them to adjust filters.
"""
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {str(e)}"

# Main UI
def main():
    # Header
    st.markdown("""
    <div style='text-align: center; padding: 1rem 0 2rem 0;'>
        <h1 style='color: #0284c7; margin-bottom: 0.5rem;'>✈️ PilotBid Pro</h1>
        <p style='color: #64748b; font-size: 1.1rem;'>The intelligent way to bid on flight pairings</p>
    </div>
    """, unsafe_allow_html=True)
    
    # File upload if no data
    if st.session_state.pairings is None:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            uploaded_file = st.file_uploader(
                "Upload your monthly pairing CSV",
                type=['csv'],
                help="Upload your airline's monthly pairing schedule"
            )
            
            if uploaded_file is not None:
                with st.spinner("Parsing schedule..."):
                    st.session_state.pairings = parse_csv(uploaded_file)
                st.success(f"✅ Loaded {len(st.session_state.pairings)} pairings")
                st.rerun()
        return
    
    # Sidebar filters
    with st.sidebar:
        st.header("🔍 Search & Filter")
        
        # Reset button
        if st.button("🔄 Reset & Upload New File", use_container_width=True):
            st.session_state.pairings = None
            st.session_state.preferences = []
            st.session_state.generated_schedules = []
            st.rerun()
        
        st.divider()
        
        # Search
        search_query = st.text_input("Search destination", placeholder="e.g., MIA, JFK")
        
        # Duration filter
        max_duration = st.slider("Max Duration (days)", 1, 10, 10)
        
        # Aircraft filter
        unique_aircraft = sorted(st.session_state.pairings['AC'].unique())
        selected_aircraft = st.multiselect(
            "Aircraft Types",
            unique_aircraft,
            default=unique_aircraft
        )
        
        # Date filter
        st.subheader("Date Range")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start", value=None)
        with col2:
            end_date = st.date_input("End", value=None)
    
    # Apply filters
    filtered_df = st.session_state.pairings.copy()
    
    if search_query:
        filtered_df = filtered_df[
            filtered_df['Pairing'].str.contains(search_query, case=False, na=False) |
            filtered_df['Pairing details'].str.contains(search_query, case=False, na=False) |
            filtered_df['AC'].str.contains(search_query, case=False, na=False)
        ]
    
    filtered_df = filtered_df[filtered_df['Duration'] <= max_duration]
    
    if selected_aircraft:
        filtered_df = filtered_df[filtered_df['AC'].isin(selected_aircraft)]
    
    if start_date:
        filtered_df = filtered_df[filtered_df['departureTime'].dt.date >= start_date]
    
    if end_date:
        filtered_df = filtered_df[filtered_df['departureTime'].dt.date <= end_date]
    
    # View mode tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        f"📋 Pairings ({len(filtered_df)})",
        "📅 Generated Calendars",
        "📊 Statistics",
        "🤖 Ask AI"
    ])
    
    with tab1:
        # Preferences manager
        st.subheader("⭐ Priorities & Preferences")
        
        with st.expander("➕ Add New Preference", expanded=len(st.session_state.preferences) == 0):
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                pref_type = st.selectbox(
                    "I want to...",
                    [
                        "Block Specific Date Off",
                        "Block Day of Week",
                        "Limit Trip Duration",
                        "Avoid Red-Eye Arrivals",
                        "Limit Flights per Day",
                        "Maximize Earnings",
                        "Prefer Airport/Route",
                        "Prefer Departure Time",
                        "Avoid Airport"
                    ]
                )
            
            pref_map = {
                "Block Specific Date Off": "SPECIFIC_DATE_OFF",
                "Block Day of Week": "DAY_OF_WEEK_OFF",
                "Limit Trip Duration": "MAX_DURATION",
                "Avoid Red-Eye Arrivals": "AVOID_RED_EYE",
                "Limit Flights per Day": "MAX_LEGS_PER_DAY",
                "Maximize Earnings": "STRATEGY_MONEY",
                "Prefer Airport/Route": "ROUTE",
                "Prefer Departure Time": "TIME_WINDOW",
                "Avoid Airport": "AVOID_AIRPORT"
            }
            
            pref_type_key = pref_map[pref_type]
            
            with col2:
                pref_value = None
                if pref_type_key == "SPECIFIC_DATE_OFF":
                    pref_value = st.date_input("Select date", value=None, key="pref_date")
                    if pref_value:
                        pref_value = pref_value.strftime("%Y-%m-%d")
                elif pref_type_key == "DAY_OF_WEEK_OFF":
                    day_name = st.selectbox("Select day", 
                        ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
                    pref_value = str(["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"].index(day_name))
                elif pref_type_key == "MAX_DURATION":
                    pref_value = str(st.number_input("Max days", min_value=1, max_value=10, value=3))
                elif pref_type_key == "MAX_LEGS_PER_DAY":
                    pref_value = str(st.number_input("Max legs", min_value=1, max_value=10, value=2))
                elif pref_type_key in ["ROUTE", "AVOID_AIRPORT"]:
                    pref_value = st.text_input("Airport code", placeholder="e.g., JFK")
                elif pref_type_key == "TIME_WINDOW":
                    col_a, col_b = st.columns(2)
                    with col_a:
                        start_hour = st.selectbox("From", range(24), index=6)
                    with col_b:
                        end_hour = st.selectbox("To", range(24), index=12)
                    pref_value = f"{start_hour}-{end_hour}"
                elif pref_type_key in ["STRATEGY_MONEY", "AVOID_RED_EYE"]:
                    st.info("No additional input needed")
                    pref_value = "true"
            
            with col3:
                if st.button("Add", use_container_width=True, type="primary"):
                    if pref_value or pref_type_key in ["STRATEGY_MONEY", "AVOID_RED_EYE"]:
                        new_pref = {
                            'type': pref_type_key,
                            'value': pref_value or "true",
                            'label': pref_type
                        }
                        st.session_state.preferences.append(new_pref)
                        st.rerun()
        
        # Display active preferences
        if st.session_state.preferences:
            st.write("**Active Preferences:**")
            cols = st.columns(3)
            for idx, pref in enumerate(st.session_state.preferences):
                with cols[idx % 3]:
                    col_a, col_b = st.columns([4, 1])
                    with col_a:
                        st.info(f"{pref['label']}: {pref['value']}")
                    with col_b:
                        if st.button("❌", key=f"del_{idx}"):
                            st.session_state.preferences.pop(idx)
                            st.rerun()
        
        st.divider()
        
        # Rank pairings
        ranked_df = rank_pairings(filtered_df, st.session_state.preferences)
        
        # Display pairings
        st.subheader(f"Top Ranked Pairings (showing {min(50, len(ranked_df))} of {len(ranked_df)})")
        
        for idx, row in ranked_df.head(50).iterrows():
            score_class = "score-high" if row['score'] >= 50 else "score-medium" if row['score'] > 0 else "score-low"
            
            with st.container():
                st.markdown(f"""
                <div class="pairing-card">
                    <div style="display: flex; justify-between; align-items: start; margin-bottom: 0.75rem;">
                        <div>
                            <h4 style="margin: 0; color: #1e293b;">Pairing {row['Pairing']}</h4>
                            <p style="margin: 0.25rem 0 0 0; color: #64748b; font-size: 0.875rem;">
                                ✈️ {row['AC']} • {row['Duration']} Days • {row['Block hours']} BH
                            </p>
                        </div>
                        <span class="score-badge {score_class}">Score: {row['score']}</span>
                    </div>
                """, unsafe_allow_html=True)
                
                # Matches
                if row['matches']:
                    st.markdown("**Matches:**")
                    for match in row['matches']:
                        if 'Violated' in match or 'Conflicts' in match:
                            st.error(f"⚠️ {match}", icon="🚫")
                        else:
                            st.success(f"✅ {match}", icon="✓")
                
                # Details
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Departure:** {row['departureTime'].strftime('%b %d, %Y at %H:%M')}")
                with col2:
                    st.write(f"**Arrival:** {row['arrivalTime'].strftime('%b %d, %Y at %H:%M')}")
                
                st.write(f"**Route:** {row['Pairing details']}")
                
                st.markdown("</div>", unsafe_allow_html=True)
    
    with tab2:
        st.subheader("📅 AI-Generated Monthly Schedules")
        
        if st.button("🔄 Generate Schedules", type="primary", use_container_width=True):
            with st.spinner("Building optimized schedules..."):
                st.session_state.generated_schedules = generate_schedules(filtered_df, st.session_state.preferences)
            st.success("✅ Generated 3 schedule options!")
        
        if st.session_state.generated_schedules:
            for schedule in st.session_state.generated_schedules:
                with st.expander(f"{schedule['name']} - {schedule['total_block_hours']} BH, {schedule['days_off']} Days Off", expanded=True):
                    st.write(schedule['description'])
                    
                    # Stats
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Block Hours", f"{schedule['total_block_hours']}")
                    with col2:
                        st.metric("Days Off", schedule['days_off'])
                    with col3:
                        st.metric("Number of Trips", schedule['flight_count'])
                    
                    # Display pairings
                    st.write("**Scheduled Pairings:**")
                    for p in schedule['pairings']:
                        st.write(f"- **{p['Pairing']}**: {p['departureTime'].strftime('%b %d')} → {p['arrivalTime'].strftime('%b %d')} ({p['Block hours']} BH)")
    
    with tab3:
        st.subheader("📊 Schedule Statistics")
        
        # Duration distribution
        st.write("**Trip Duration Distribution**")
        duration_counts = filtered_df['Duration'].value_counts().sort_index()
        fig = px.bar(x=duration_counts.index, y=duration_counts.values,
                    labels={'x': 'Days', 'y': 'Count'},
                    color=duration_counts.values,
                    color_continuous_scale='Blues')
        st.plotly_chart(fig, use_container_width=True)
        
        # Aircraft breakdown
        st.write("**Aircraft Type Breakdown**")
        aircraft_counts = filtered_df['AC'].value_counts()
        fig = px.pie(values=aircraft_counts.values, names=aircraft_counts.index,
                    color_discrete_sequence=px.colors.sequential.Blues_r)
        st.plotly_chart(fig, use_container_width=True)
        
        # Summary stats
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Pairings", len(filtered_df))
        with col2:
            st.metric("Avg Duration", f"{filtered_df['Duration'].mean():.1f} days")
        with col3:
            st.metric("Avg Block Hours", f"{filtered_df['blockHoursDecimal'].mean():.1f} hrs")
    
    with tab4:
        st.subheader("🤖 Ask AI Assistant")
        
        # API Key input
        api_key = st.text_input("Gemini API Key", type="password",
                               help="Enter your Google Gemini API key")
        
        # Query input
        query = st.text_area("Ask about your filtered pairings",
                           placeholder="e.g., Which of these have the longest layovers?")
        
        if st.button("Ask AI", type="primary", disabled=not query or not api_key):
            with st.spinner("Thinking..."):
                response = get_ai_response(filtered_df, query, api_key)
                st.session_state.ai_response = response
        
        if st.session_state.ai_response:
            st.info(st.session_state.ai_response)

if __name__ == "__main__":
    main()
