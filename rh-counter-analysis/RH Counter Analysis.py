import streamlit as st
import pandas as pd
from datetime import datetime
import io
import numpy as np

st.set_page_config(layout="wide")
st.title("Machinery RH Counters Analysis")

# --- File Uploaders and Vessel Delivery in Sidebar ---
with st.sidebar:
    uploaded_files = st.file_uploader(
        "Upload Machinery RH Counter Excel/CSV files",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key="uploaded_files"
    )
    vessel_delivery_file = st.file_uploader(
        "Upload Vessel Delivery Excel/CSV file (must have 'vessel' and 'delivery date' columns)",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=False,
        key="vessel_delivery_file"
    )

# --- Data Preparation ---
merged_df = None
vessel_df = None
if uploaded_files:
    dfs = []
    for file in uploaded_files:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        elif file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            continue
        dfs.append(df)
    if dfs:
        merged_df = pd.concat(dfs, ignore_index=True)
if vessel_delivery_file:
    if vessel_delivery_file.name.endswith('.csv'):
        vessel_df = pd.read_csv(vessel_delivery_file)
    elif vessel_delivery_file.name.endswith(('.xlsx', '.xls')):
        vessel_df = pd.read_excel(vessel_delivery_file)
    else:
        vessel_df = None

filtered_df = pd.DataFrame()
if (merged_df is not None) and (vessel_df is not None):
    # Add Component Type column
    if 'Inheriting Counter' in merged_df.columns:
        merged_df['Component Type'] = merged_df['Inheriting Counter'].apply(
            lambda x: "Parent" if pd.isnull(x) or str(x).strip() == "" else "Child"
        )
    else:
        merged_df['Component Type'] = "Unknown"

    # Add Parent_Reading column: Parent gets Reading, Child gets None, then fill down
    if 'Inheriting Counter' in merged_df.columns and 'Reading' in merged_df.columns:
        merged_df['Parent_Reading'] = merged_df.apply(
            lambda row: row['Reading'] if pd.isnull(row['Inheriting Counter']) or str(row['Inheriting Counter']).strip() == "" else None,
            axis=1
        )
        merged_df['Parent_Reading'] = merged_df['Parent_Reading'].ffill()
    else:
        merged_df['Parent_Reading'] = None

    # Remove decimals from Reading and Parent_Reading
    for col in ['Reading', 'Parent_Reading']:
        if col in merged_df.columns:
            merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').apply(lambda x: int(x) if not pd.isnull(x) else np.nan)

    # Add Days Since Last Reading column (difference between Reading Date and Vessel Delivery Date)
    if 'Reading Date' in merged_df.columns and 'Vessel Delivery Date' in merged_df.columns:
        merged_df['Days Since Last Reading'] = merged_df.apply(
            lambda row: (
                (datetime.strptime(row['Reading Date'], '%d-%m-%Y') - datetime.strptime(row['Vessel Delivery Date'], '%d-%m-%Y')).days
                if pd.notnull(row['Reading Date']) and pd.notnull(row['Vessel Delivery Date']) else np.nan
            ),
            axis=1
        )
        merged_df['Days Since Last Reading'] = merged_df['Days Since Last Reading'].apply(lambda x: int(x) if not pd.isnull(x) else np.nan)

    # Move Parent_Reading and Days Since Last Reading next to Reading
    cols = list(merged_df.columns)
    if 'Reading' in cols and 'Parent_Reading' in cols:
        reading_idx = cols.index('Reading')
        if 'Parent_Reading' in cols:
            cols.remove('Parent_Reading')
            cols.insert(reading_idx + 1, 'Parent_Reading')
        if 'Days Since Last Reading' in cols:
            cols.remove('Days Since Last Reading')
            cols.insert(reading_idx + 2, 'Days Since Last Reading')
        merged_df = merged_df[cols]

    # Add RH Counter_Result column
    def rh_counter_result(row):
        reading = row.get('Reading', None)
        parent_reading = row.get('Parent_Reading', None)
        if pd.isnull(reading) or str(reading) == "" or str(reading).lower() == "nan":
            return "Value Missing"
        elif reading == parent_reading:
            return "Match"
        elif parent_reading is not None and reading != parent_reading:
            return "Mismatch"
        else:
            return None
    merged_df['RH Counter_Result'] = merged_df.apply(rh_counter_result, axis=1)

    vessel_df_renamed = vessel_df.rename(
        columns={col: col.lower() for col in vessel_df.columns}
    )
    vessel_delivery_map = vessel_df_renamed.set_index('vessel')['delivery date'].to_dict()
    merged_df['Vessel Delivery Date'] = merged_df['Vessel'].map(vessel_delivery_map)
    for date_col in ['Reading Date', 'Vessel Delivery Date']:
        if date_col in merged_df.columns:
            merged_df[date_col] = pd.to_datetime(
                merged_df[date_col], format='%d-%m-%Y', errors='coerce'
            ).dt.strftime('%d-%m-%Y')
    def calc_rh_avg(row):
        try:
            reading = row['Reading']
            if pd.isnull(reading) or reading == "":
                return ""
            rd_str = row.get('Reading Date', "")
            vd_str = row.get('Vessel Delivery Date', "")
            if not rd_str or not vd_str:
                return ""
            rd = datetime.strptime(rd_str, '%d-%m-%Y')
            vd = datetime.strptime(vd_str, '%d-%m-%Y')
            days = (rd - vd).days
            if days == 0:
                return ""
            return round(float(reading) / days, 2)
        except Exception:
            return ""
    merged_df['RH Avg Calculated'] = merged_df.apply(calc_rh_avg, axis=1)
    def calc_variance(row):
        try:
            reading = row['Reading']
            if pd.isnull(reading) or reading == "":
                return ""
            rh_avg = row.get('RH Avg Calculated', "")
            rha_24 = row.get('Running Hours Average (/24 Hours)', "")
            if rh_avg == "" or rha_24 == "" or pd.isnull(rh_avg) or pd.isnull(rha_24):
                return ""
            return round(abs(float(rh_avg) - float(rha_24)), 2)
        except Exception:
            return ""
    merged_df['Variance'] = merged_df.apply(calc_variance, axis=1)
    def calc_correction(row):
        try:
            reading = row['Reading']
            if pd.isnull(reading) or reading == "":
                return ""
            variance = row.get('Variance', "")
            if variance == "" or pd.isnull(variance):
                return "No"
            return "Yes" if float(variance) > 3 else "No"
        except Exception:
            return ""
    merged_df['Correction Needed'] = merged_df.apply(calc_correction, axis=1)

    # --- Vessel filter ---
    col1, spacer, col2 = st.columns([1.3, 0.3, 1])
    vessel_options = sorted(merged_df['Vessel'].dropna().unique())
    with col2:
        selected_vessels = st.multiselect(
            "Select Vessel(s) to filter metrics and data:",
            options=vessel_options,
            default=vessel_options
        )
        st.write("")
        st.write("")  # Two line spaces before metric selection

    filtered_df = merged_df[merged_df['Vessel'].isin(selected_vessels)] if selected_vessels else merged_df.iloc[0:0]

    # --- Summary Metrics ---
    incorrect_rh_count = (filtered_df['Correction Needed'] == "Yes").sum()
    rh_mismatch_count = (filtered_df['RH Counter_Result'] == "Mismatch").sum()
    summary_metrics = {
        "Total Number of Records": len(filtered_df),
        "Number of Vessels Selected": len(selected_vessels),
        "Number of Records with Reading Date in Future": (
            pd.to_datetime(filtered_df['Reading Date'], format='%d-%m-%Y', errors='coerce') > pd.to_datetime(datetime.today().date())
        ).sum() if 'Reading Date' in filtered_df.columns else "N/A",
        "Number of Records with 'Running Hours Average (/24 Hours)' > 24": (
            pd.to_numeric(filtered_df['Running Hours Average (/24 Hours)'], errors='coerce') > 24
        ).sum() if 'Running Hours Average (/24 Hours)' in filtered_df.columns else "N/A",
        "Number of records with Incorrect RH Averages": incorrect_rh_count,
        "Number of Records with Reading Mismatch ⚠️": rh_mismatch_count
    }
    metrics_df = pd.DataFrame({
        "Metric": list(summary_metrics.keys()),
        "Value": list(summary_metrics.values())
    })

    def highlight_mismatch_row(row):
        if 'Reading Mismatch' in str(row['Metric']):
            return ['background-color: #ffcccc'] * len(row)
        else:
            return [''] * len(row)

    with col1:
        st.warning(f"⚠️ Number of Records with Reading Mismatch: {rh_mismatch_count}", icon="⚠️")
        st.subheader("Summary Metrics (for selected vessel(s))")
        metric_labels = [k for k in summary_metrics.keys() if k != "Number of Vessels Selected"]
        styled_metrics = metrics_df.style.apply(highlight_mismatch_row, axis=1)
        st.dataframe(styled_metrics, use_container_width=True)

    with col2:
        st.markdown("**Select a metric to show the full table for:**")
        selected_metric = st.selectbox(
            "Choose a metric", metric_labels, index=0, key="metric_selectbox"
        )

    def highlight_cols(x):
        color_green = 'background-color: #b6fcb6'
        color_orange = 'background-color: #ffe5b4'  # Light pastel orange
        df = pd.DataFrame('', index=x.index, columns=x.columns)
        if 'Parent_Reading' in df.columns:
            df['Parent_Reading'] = color_green
        if 'Running Hours Average (/24 Hours)' in df.columns:
            df['Running Hours Average (/24 Hours)'] = color_orange
        return df

    def safe_two_decimals(x):
        try:
            return "{:.2f}".format(float(x))
        except (ValueError, TypeError):
            return x

    if selected_metric:
        st.write("")
        st.write("")
        st.subheader(f"Full Merged Machinery RH Counter Data for: {selected_metric}")
        if selected_metric == "Total Number of Records":
            preview_df = filtered_df
        elif selected_metric == "Number of Records with Reading Date in Future":
            preview_df = filtered_df[
                pd.to_datetime(filtered_df['Reading Date'], format='%d-%m-%Y', errors='coerce') > pd.to_datetime(datetime.today().date())
            ] if 'Reading Date' in filtered_df.columns else filtered_df.iloc[0:0]
        elif selected_metric == "Number of Records with 'Running Hours Average (/24 Hours)' > 24":
            preview_df = filtered_df[
                pd.to_numeric(filtered_df['Running Hours Average (/24 Hours)'], errors='coerce') > 24
            ] if 'Running Hours Average (/24 Hours)' in filtered_df.columns else filtered_df.iloc[0:0]
        elif selected_metric == "Number of records with Incorrect RH Averages":
            preview_df = filtered_df[filtered_df['Correction Needed'] == "Yes"] if 'Correction Needed' in filtered_df.columns else filtered_df.iloc[0:0]
        elif "Reading Mismatch" in selected_metric:
            preview_df = filtered_df[filtered_df['RH Counter_Result'] == "Mismatch"] if 'RH Counter_Result' in filtered_df.columns else filtered_df.iloc[0:0]
        else:
            preview_df = filtered_df

        if 'Reading' in preview_df.columns and 'Parent_Reading' in preview_df.columns:
            cols = list(preview_df.columns)
            reading_idx = cols.index('Reading')
            if 'Parent_Reading' in cols:
                cols.remove('Parent_Reading')
                cols.insert(reading_idx + 1, 'Parent_Reading')
            if 'Days Since Last Reading' in cols:
                cols.remove('Days Since Last Reading')
                cols.insert(reading_idx + 2, 'Days Since Last Reading')
            preview_df = preview_df[cols]

        for col in ['Reading', 'Parent_Reading', 'Days Since Last Reading']:
            if col in preview_df.columns:
                preview_df[col] = pd.to_numeric(preview_df[col], errors='coerce').apply(lambda x: int(x) if not pd.isnull(x) else np.nan)

        float_format_dict = {}
        for col in preview_df.columns:
            if col.lower() in ['rh average', 'rh avg calculated', 'variance', 'running hours average (/24 hours)']:
                float_format_dict[col] = safe_two_decimals

        st.dataframe(
            preview_df.style
                .apply(highlight_cols, axis=None)
                .format(float_format_dict),
            use_container_width=True
        )

    # --- Download Button at Bottom of Sidebar ---
    with st.sidebar:
        st.write("")
        st.write("")
        if not filtered_df.empty:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                filtered_df.to_excel(writer, index=False, sheet_name='Filtered Data')
            st.download_button(
                label="Download Filtered Data as Excel",
                data=buffer.getvalue(),
                file_name="filtered_machinery_rh_counters.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="sidebar_download"
            )
        else:
            st.info("No data to download for the selected vessels.")

elif merged_df is not None:
    st.subheader("Preview of Merged Machinery RH Counter Data")
    st.dataframe(merged_df)
elif vessel_df is not None:
    st.subheader("Vessel Delivery File Preview")
    st.dataframe(vessel_df)
