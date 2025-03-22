import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import os
from datetime import datetime
import plotly.express as px

# Load environment variables
load_dotenv()

# Constants
SPREADSHEET_NAME = 'BROWNS STOCK MANAGEMENT'
SHEET_NAME = 'CHECK_OUT'

# Function to connect to Google Sheets
def connect_to_gsheet(spreadsheet_name, sheet_name):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        credentials = {
            "type": "service_account",
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
            "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
            "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
        }
        client_credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
        client = gspread.authorize(client_credentials)
        spreadsheet = client.open(spreadsheet_name)
        return spreadsheet.worksheet(sheet_name)
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None

# Function to load data from Google Sheets
def load_data_from_google_sheet():
    with st.spinner("Loading data from Google Sheets..."):
        try:
            worksheet = connect_to_gsheet(SPREADSHEET_NAME, SHEET_NAME)
            if worksheet is None:
                return None
            
            data = worksheet.get_all_records()
            if not data:
                st.error("No data found in the Google Sheet.")
                return None

            df = pd.DataFrame(data)
            df.columns = [
                "DATE", "ITEM_SERIAL", "ITEM NAME", "DEPARTMENT", "ISSUED_TO", "QUANTITY",
                "UNIT_OF_MEASURE", "ITEM_CATEGORY", "WEEK", "REFERENCE", "DEPARTMENT_CAT",
                "BATCH NO.", "STORE", "RECEIVED BY"
            ]
            df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
            df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce")
            df.dropna(subset=["QUANTITY"], inplace=True)
            df["QUARTER"] = df["DATE"].dt.to_period("Q")
            current_year = datetime.now().year
            df = df[df["DATE"].dt.year >= current_year - 1]
            return df
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return None

# Cache data for 1 hour
@st.cache_data(ttl=3600)
def get_cached_data():
    return load_data_from_google_sheet()

# Function to calculate proportions
def calculate_proportion(df, identifier, department=None, min_proportion=1.0):
    if df is None:
        return None
    try:
        if identifier.isnumeric():
            filtered_df = df[df["ITEM_SERIAL"].astype(str).str.lower() == identifier.lower()]
        else:
            filtered_df = df[df["ITEM NAME"].str.lower() == identifier.lower()]

        if filtered_df.empty:
            return None

        if department and department != "All Departments":
            filtered_df = filtered_df[filtered_df["DEPARTMENT"] == department]
            if filtered_df.empty:
                return None

        dept_usage = filtered_df.groupby("DEPARTMENT")["QUANTITY"].sum().reset_index()
        total_usage = dept_usage["QUANTITY"].sum()
        if total_usage == 0:
            return None
            
        dept_usage["PROPORTION"] = (dept_usage["QUANTITY"] / total_usage) * 100
        significant_depts = dept_usage[dept_usage["PROPORTION"] >= min_proportion].copy()
        
        if significant_depts.empty and not dept_usage.empty:
            significant_depts = pd.DataFrame([dept_usage.iloc[dept_usage["PROPORTION"].idxmax()]])
        
        total_proportion = significant_depts["PROPORTION"].sum()
        significant_depts["PROPORTION"] = (significant_depts["PROPORTION"] / total_proportion) * 100
        significant_depts["QUANTITY_ABS"] = significant_depts["QUANTITY"].abs()
        significant_depts["INTERNAL_WEIGHT"] = significant_depts["QUANTITY_ABS"] / significant_depts["QUANTITY_ABS"].sum()
        significant_depts.sort_values(by=["PROPORTION"], ascending=[False], inplace=True)
        return significant_depts
    except Exception as e:
        st.error(f"Error calculating proportions: {e}")
        return None

# Function to allocate quantity
def allocate_quantity(df, identifier, available_quantity, department=None):
    proportions = calculate_proportion(df, identifier, department, min_proportion=1.0)
    if proportions is None:
        return None
    
    proportions["ALLOCATED_QUANTITY"] = (proportions["PROPORTION"] / 100 * available_quantity).round(0)
    allocated_sum = proportions["ALLOCATED_QUANTITY"].sum()
    difference = int(available_quantity - allocated_sum)
    
    if difference != 0:
        index_max = proportions["ALLOCATED_QUANTITY"].idxmax()
        proportions.at[index_max, "ALLOCATED_QUANTITY"] += difference
    
    return proportions

# Function to generate historical usage trends
def generate_historical_usage_chart(df, item_name):
    filtered_df = df[df["ITEM NAME"] == item_name]
    if filtered_df.empty:
        return None
    
    # Resample data to reduce noise (e.g., monthly)
    filtered_df = filtered_df.set_index("DATE").resample("M").sum().reset_index()
    
    fig = px.line(
        filtered_df,
        x="DATE",
        y="QUANTITY",
        title=f"Historical Usage for {item_name}",
        labels={"DATE": "Date", "QUANTITY": "Quantity"},
        markers=True
    )
    return fig

# Streamlit UI
st.set_page_config(
    page_title="SPP Ingredients Management App",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern appearance
st.markdown("""
    <style>
    .title {
        text-align: center;
        font-size: 36px;
        font-weight: bold;
        color: #2E86C1;
        font-family: 'Arial', sans-serif;
        margin-bottom: 10px;
    }
    .subtitle {
        text-align: center;
        font-size: 18px;
        color: #6c757d;
        margin-bottom: 30px;
    }
    .footer {
        text-align: center;
        font-size: 12px;
        color: #888888;
        margin-top: 30px;
    }
    .stButton button {
        background-color: #f0f0f0;
        color: #2E86C1;
        font-weight: bold;
        border-radius: 5px;
        padding: 10px 20px;
        transition: background-color 0.3s ease;
    }
    .stButton button:hover {
        background-color: #2E86C1;
        color: white;
    }
    .stButton button:active {
        background-color: #2E86C1;
        color: white;
    }
    .card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 20px;
        border: 1px solid #e0e0e0;
    }
    .stDataFrame {
        background-color: #f9f9f9;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    .stDataFrame:active {
        background-color: #e0f7fa;
    }
    .stSelectbox, .stNumberInput, .stMultiselect {
        margin-bottom: 15px;
    }
    .stExpander {
        background-color: #f9f9f9;
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 20px;
    }
    .stMetric {
        background-color: #f0f4f8;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    </style>
""", unsafe_allow_html=True)

# Main title
st.markdown("<h1 class='title'>SPP Ingredients Management App</h1>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("<h2 class='title'>Quick Actions & Stats</h2>", unsafe_allow_html=True)
    
    # Refresh data button
    if st.button("🔄 Refresh Data"):
        st.session_state.data = load_data_from_google_sheet()
        st.success("Data refreshed successfully!")
    
    # Clear cache button
    if st.button("🧹 Clear Cache"):
        st.cache_data.clear()
        st.success("Cache cleared successfully!")
    
    # Summary statistics
    st.markdown("### Quick Stats")
    if "data" in st.session_state:
        unique_item_names = sorted(st.session_state.data["ITEM NAME"].unique().tolist())
        unique_departments = sorted(st.session_state.data["DEPARTMENT"].unique().tolist())
        st.metric("Total Items", f"{len(unique_item_names)}")
        st.metric("Total Departments", f"{len(unique_departments)}")
        
        # Display date period
        min_date = st.session_state.data["DATE"].min().date()
        max_date = st.session_state.data["DATE"].max().date()
        st.markdown(f"**Date Period:** {min_date} to {max_date}")
    else:
        st.warning("No data loaded yet.")

# Load data
if "data" not in st.session_state:
    st.session_state.data = get_cached_data()
data = st.session_state.data

if data is None:
    st.error("Failed to load data from Google Sheets. Please check your connection and credentials.")
    st.stop()

# Extract unique values for filters
unique_item_names = sorted(data["ITEM NAME"].unique().tolist())
unique_item_serials = sorted(data["ITEM_SERIAL"].unique().tolist())
unique_departments = sorted(["All Departments"] + data["DEPARTMENT"].unique().tolist())
unique_item_categories = sorted(data["ITEM_CATEGORY"].unique().tolist())
unique_department_cats = sorted(data["DEPARTMENT_CAT"].unique().tolist())
unique_stores = sorted(data["STORE"].unique().tolist())

# Buttons for main page
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("📊 Allocate Ingredients", key="allocate_button"):
        st.session_state.selected_tab = "Allocation Calculator"
with col2:
    if st.button("📈 View Data Overview", key="data_overview_button"):
        st.session_state.selected_tab = "Data Overview"
with col3:
    if st.button("📅 Analyze Historical Usage", key="historical_usage_button"):
        st.session_state.selected_tab = "Historical Usage"
with col4:
    if st.button("📝 Issue Ingredients", key="issue_ingredients_button"):
        st.session_state.selected_tab = "Ingredient Issuance"

# Default to Allocation Calculator if no tab is selected
if "selected_tab" not in st.session_state:
    st.session_state.selected_tab = "Allocation Calculator"

# Allocation Calculator
if st.session_state.selected_tab == "Allocation Calculator":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Allocation Calculator")
    st.markdown("""
        <p>
            Use this tool to calculate ingredient allocations based on historical usage data.
            Enter the items and quantities, and the app will allocate them proportionally across departments.
        </p>
    """, unsafe_allow_html=True)
    
    with st.form("allocation_form"):
        num_items = st.number_input("Number of items to allocate", min_value=1, max_value=10, step=1, value=10)
        selected_department = st.selectbox("Filter by Department (optional)", unique_departments)
        
        entries = []
        for i in range(num_items):
            st.markdown(f"**Item {i+1}**")
            col1, col2 = st.columns([2, 1])
            with col1:
                identifier = st.selectbox(f"Select item {i+1}", unique_item_names, key=f"item_{i}")
            with col2:
                available_quantity = st.number_input(f"Quantity:", min_value=0.1, step=0.1, key=f"qty_{i}")

            if identifier and available_quantity > 0:
                entries.append((identifier, available_quantity))

        submitted = st.form_submit_button("Calculate Allocation")
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        if not entries:
            st.warning("Please enter at least one valid item and quantity!")
        else:
            for idx, (identifier, available_quantity) in enumerate(entries):
                result = allocate_quantity(data, identifier, available_quantity, selected_department)
                if result is not None:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    st.markdown(f"<h3 style='color: #2E86C1;'>Allocation for {identifier}</h3>", unsafe_allow_html=True)
                    
                    formatted_result = result[["DEPARTMENT", "PROPORTION", "ALLOCATED_QUANTITY"]].copy()
                    formatted_result = formatted_result.rename(columns={
                        "DEPARTMENT": "Department",
                        "PROPORTION": "Proportion (%)",
                        "ALLOCATED_QUANTITY": "Allocated Quantity"
                    })
                    formatted_result["Proportion (%)"] = formatted_result["Proportion (%)"].round(2)
                    formatted_result["Allocated Quantity"] = formatted_result["Allocated Quantity"].astype(int)
                    
                    st.dataframe(formatted_result, use_container_width=True)
                    
                    # Download CSV for allocation results
                    csv = formatted_result.to_csv(index=False)
                    st.download_button(
                        label="Download Allocation as CSV",
                        data=csv,
                        file_name=f"{identifier}_allocation.csv",
                        mime="text/csv",
                        key=f"download_{idx}"  # Unique key for each download button
                    )
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.error(f"Item {identifier} not found in historical data or has no usage data for the selected department!")

# Data Overview
elif st.session_state.selected_tab == "Data Overview":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Data Overview")
    st.markdown("""
        <p>
            Explore filtered data and usage statistics. Use the filters to narrow down the data and visualize usage trends.
        </p>
    """, unsafe_allow_html=True)
    
    with st.expander("🔍 Advanced Filters", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            min_date = data["DATE"].min().date()
            max_date = data["DATE"].max().date()
            date_range = st.date_input("Select Date Range", [min_date, max_date])
        with col2:
            selected_categories = st.multiselect("Filter by Item Categories", unique_item_categories, default=[])
        
        col3, col4 = st.columns(2)
        with col3:
            selected_items = st.multiselect("Filter by Items", unique_item_names, default=[])
        with col4:
            selected_overview_dept = st.multiselect("Filter by Departments", unique_departments, default=[])
    
    filtered_data = data.copy()
    if date_range:
        filtered_data = filtered_data[(filtered_data["DATE"].dt.date >= date_range[0]) & 
                                     (filtered_data["DATE"].dt.date <= date_range[1])]
    if selected_categories:
        filtered_data = filtered_data[filtered_data["ITEM_CATEGORY"].isin(selected_categories)]
    if selected_items:
        filtered_data = filtered_data[filtered_data["ITEM NAME"].isin(selected_items)]
    if selected_overview_dept:
        filtered_data = filtered_data[filtered_data["DEPARTMENT"].isin(selected_overview_dept)]
    
    st.markdown("#### Filtered Data Preview")
    st.dataframe(filtered_data.head(100), use_container_width=True)
    
    # Download CSV for filtered data
    csv = filtered_data.to_csv(index=False)
    st.download_button(
        label="Download Filtered Data as CSV",
        data=csv,
        file_name="filtered_data.csv",
        mime="text/csv",
    )
    
    st.markdown("#### Usage Statistics")
    total_usage = filtered_data["QUANTITY"].sum()
    unique_items_count = filtered_data["ITEM NAME"].nunique()
    
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    with stat_col1:
        st.metric("Total Quantity Used", f"{total_usage:,.2f}")
    with stat_col2:
        st.metric("Unique Items", f"{unique_items_count}")
    with stat_col3:
        st.metric("Total Transactions", f"{len(filtered_data):,}")
    
    if not filtered_data.empty:
        st.markdown("#### Department Usage")
        dept_usage = filtered_data.groupby("DEPARTMENT")["QUANTITY"].sum().reset_index()
        dept_usage.sort_values(by="QUANTITY", ascending=False, inplace=True)
        
        fig = px.pie(
            dept_usage, 
            values="QUANTITY", 
            names="DEPARTMENT", 
            title="Usage Distribution by Department",
            hole=0.4
        )
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Historical Usage
elif st.session_state.selected_tab == "Historical Usage":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Historical Usage Trends")
    st.markdown("""
        <p>
            Visualize historical usage trends and identify most used items. Analyze monthly usage patterns by department.
        </p>
    """, unsafe_allow_html=True)
    
    # Department selection for overall statistics
    selected_department = st.selectbox("Select Department", unique_departments)
    
    if selected_department:
        if selected_department == "All Departments":
            filtered_data = data
        else:
            filtered_data = data[data["DEPARTMENT"] == selected_department]
        
        # Overall statistics
        st.markdown("#### Overall Statistics")
        total_usage = filtered_data["QUANTITY"].sum()
        most_used_item = filtered_data.groupby("ITEM NAME")["QUANTITY"].sum().idxmax()
        most_used_department = filtered_data.groupby("DEPARTMENT")["QUANTITY"].sum().idxmax()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Quantity Used", f"{total_usage:,.2f}")
        with col2:
            st.metric("Most Used Item", most_used_item)
        with col3:
            st.metric("Most Used Department", most_used_department)
        
        # Monthly usage per department
        st.markdown("#### Monthly Usage per Department")
        monthly_usage = filtered_data.groupby([pd.Grouper(key="DATE", freq="M"), "DEPARTMENT"])["QUANTITY"].sum().reset_index()
        
        fig = px.line(
            monthly_usage,
            x="DATE",
            y="QUANTITY",
            color="DEPARTMENT",
            title="Monthly Usage by Department",
            labels={"DATE": "Date", "QUANTITY": "Quantity"},
            markers=True
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Top 10 most used items by department
        st.markdown("#### Top 10 Most Used Items by Department")
        top_items = filtered_data.groupby("ITEM NAME")["QUANTITY"].sum().nlargest(10).reset_index()
        
        # Display the top items in a DataFrame with text wrapping
        st.dataframe(
            top_items,
            column_config={
                "ITEM NAME": st.column_config.TextColumn("Item Name", width="large"),
                "QUANTITY": st.column_config.NumberColumn("Quantity", format="%.2f")
            },
            use_container_width=True
        )
        
        # Bar chart for top 10 items
        fig = px.bar(
            top_items,
            x="ITEM NAME",
            y="QUANTITY",
            title=f"Top 10 Most Used Items in {selected_department}",
            labels={"ITEM NAME": "Item", "QUANTITY": "Quantity"},
            color="QUANTITY",
            color_continuous_scale=px.colors.sequential.Blues
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

# Ingredient Issuance
elif st.session_state.selected_tab == "Ingredient Issuance":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Ingredient Issuance Console")
    st.markdown("""
        <p>
            Record new ingredient issuances with suggestions from historical data. Enter the details and submit the form.
        </p>
    """, unsafe_allow_html=True)
    
    with st.form("issuance_form"):
        st.markdown("#### Enter Issuance Details")
        
        # Auto-fill date
        issuance_date = st.date_input("Date", value=datetime.now())
        
        # Item selection
        col1, col2 = st.columns(2)
        with col1:
            selected_item = st.selectbox("Item Name", unique_item_names)
        with col2:
            selected_item_serial = st.selectbox("Item Serial", unique_item_serials)
        
        # Quantity input
        quantity = st.number_input("Quantity", min_value=0.1, step=0.1)
        
        # Suggestions for other fields
        item_data = data[data["ITEM NAME"] == selected_item].iloc[0]
        department = st.selectbox("Department", unique_departments, index=unique_departments.index(item_data["DEPARTMENT"]))
        issued_to = st.text_input("Issued To", value=item_data["ISSUED_TO"])
        unit_of_measure = st.text_input("Unit of Measure", value=item_data["UNIT_OF_MEASURE"])
        item_category = st.selectbox("Item Category", unique_item_categories, index=unique_item_categories.index(item_data["ITEM_CATEGORY"]))
        reference = st.text_input("Reference", value=item_data["REFERENCE"])
        department_cat = st.selectbox("Department Category", unique_department_cats, index=unique_department_cats.index(item_data["DEPARTMENT_CAT"]))
        batch_no = st.text_input("Batch No.", value=item_data["BATCH NO."])
        store = st.selectbox("Store", unique_stores, index=unique_stores.index(item_data["STORE"]))
        received_by = st.text_input("Received By", value=item_data["RECEIVED BY"])
        
        submitted = st.form_submit_button("Submit Issuance")
    
    if submitted:
        st.success("Issuance recorded successfully!")
    st.markdown("</div>", unsafe_allow_html=True)
