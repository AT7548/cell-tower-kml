import streamlit as st
import pandas as pd
import math
import os
import re

# --- Configuration ---
ENODEB_MULTIPLIER = 256
DEFAULT_RADIUS_METERS = 2000
KML_ALTITUDE = 100

TARGET_COLUMNS = [
    'cell_id', 'licensee_name*', 'technology', 
    'latitude', 'longitude', 'tx_ant_horiz_beamwidth', 'tx_ant_azimuth',
    'tx_frequency', 'rx_frequency'
]
PROVINCE_COLUMN = 'province_code'

CANADIAN_PROVINCES = {
    'AB': 'Alberta', 'BC': 'British Columbia', 'MB': 'Manitoba', 
    'NB': 'New Brunswick', 'NL': 'Newfoundland and Labrador', 
    'NS': 'Nova Scotia', 'NT': 'Northwest Territories', 
    'NU': 'Nunavut', 'ON': 'Ontario', 'PE': 'Prince Edward Island', 
    'QC': 'Quebec', 'SK': 'Saskatchewan', 'YT': 'Yukon'
}

# --- Utility Functions ---
def clean_number(val):
    """Strips letters and spaces from Excel inputs (e.g. '5000 m' -> 5000.0)"""
    try:
        clean = re.sub(r'[^\d.-]', '', str(val))
        return float(clean) if clean else 0.0
    except:
        return 0.0

# --- KML Generation Logic ---
def get_sector_coords(lat, lon, azimuth, beamwidth, radius_m):
    total_angle = beamwidth * 2
    start_angle = (azimuth - (total_angle / 2)) % 360
    end_angle = (azimuth + (total_angle / 2)) % 360
    segments = 36 
    coords = [f"{lon},{lat},{KML_ALTITUDE}"] 
    for i in range(segments + 1):
        angle = start_angle + (i * total_angle / segments)
        angle_rad = math.radians(angle)
        lat_rad = math.radians(lat)
        dLat = (radius_m / 111111) * math.cos(angle_rad)
        dLon = (radius_m / (111111 * math.cos(lat_rad))) * math.sin(angle_rad)
        coords.append(f"{lon + dLon},{lat + dLat},{KML_ALTITUDE}")
    coords.append(f"{lon},{lat},{KML_ALTITUDE}")
    return " ".join(coords)

def get_circle_coords(lat, lon, radius_m):
    segments = 36
    coords = []
    for i in range(segments):
        angle_rad = math.radians(i * (360 / segments))
        lat_rad = math.radians(lat)
        dLat = (radius_m / 111111) * math.cos(angle_rad)
        dLon = (radius_m / (111111 * math.cos(lat_rad))) * math.sin(angle_rad)
        coords.append(f"{lon + dLon},{lat + dLat},{KML_ALTITUDE}")
    coords.append(coords[0]) 
    return " ".join(coords)

def generate_kml_content(df, lbs_df=None):
    kml_start = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <name>Network and LBS Investigation</name>
    
    <Style id="sectorStyle">
        <LineStyle><color>ff0000ff</color><width>1.5</width></LineStyle>
        <PolyStyle><color>7000ffff</color><fill>1</fill><outline>1</outline></PolyStyle>
        <LabelStyle><scale>0</scale></LabelStyle>
    </Style>
    
    <Style id="pingStyle">
        <LineStyle><color>ffffaa00</color><width>2.0</width></LineStyle>
        <PolyStyle><color>80ffaa00</color><fill>1</fill><outline>1</outline></PolyStyle>
        <LabelStyle><scale>0</scale></LabelStyle>
    </Style>"""
    kml_content = []
    
    # --- Generate Cell Tower Sectors ---
    kml_content.append("<Folder>\n<name>Cell Sectors</name>")
    if not df.empty:
        metadata_cols = TARGET_COLUMNS + [PROVINCE_COLUMN, 'TowerID', 'CustomRadius']
        for _, row in df.iterrows():
            try:
                coords_str = get_sector_coords(
                    float(row['latitude']), float(row['longitude']), 
                    float(row['tx_ant_azimuth']), float(row['tx_ant_horiz_beamwidth']), 
                    float(row['CustomRadius'])
                )
                new_title = f"{row.get('licensee_name*', 'Unknown')} - {row.get('technology', 'Unknown')} - {row['TowerID']}"
                
                desc_rows = [f"<tr><td><b>{c}:</b></td><td>{row.get(c, '')}</td></tr>" for c in metadata_cols if pd.notna(row.get(c))]
                description_html = f"<table>{''.join(desc_rows)}</table>"
                
                kml_content.append(f"""
    <Placemark>
        <name><![CDATA[{new_title}]]></name>
        <description><![CDATA[{description_html}]]></description>
        <styleUrl>#sectorStyle</styleUrl>
        <MultiGeometry>
            <Point><coordinates>{row['longitude']},{row['latitude']},{KML_ALTITUDE}</coordinates></Point>
            <Polygon><extrude>1</extrude><altitudeMode>relativeToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{coords_str}</coordinates></LinearRing></outerBoundaryIs></Polygon>
        </MultiGeometry>
    </Placemark>""")
            except Exception:
                continue
    kml_content.append("</Folder>")

    # --- Generate LBS Pings ---
    lbs_written_count = 0
    kml_content.append("<Folder>\n<name>LBS Pings</name>")
    if lbs_df is not None and not lbs_df.empty:
        for _, row in lbs_df.iterrows():
            try:
                lat = clean_number(row['Latitude'])
                lon = clean_number(row['Longitude'])
                rad = clean_number(row['Radius'])
                
                if lat == 0.0 or lon == 0.0 or rad == 0.0:
                    continue
                    
                timestamp = str(row['Start Date/Time'])
                
                coords_str = get_circle_coords(lat, lon, rad)
                description_html = f"<table><tr><td><b>Start Date/Time:</b></td><td>{timestamp}</td></tr><tr><td><b>Radius:</b></td><td>{rad}m</td></tr><tr><td><b>Lat/Lon:</b></td><td>{lat}, {lon}</td></tr></table>"
                
                kml_content.append(f"""
    <Placemark>
        <name><![CDATA[{timestamp}]]></name>
        <description><![CDATA[{description_html}]]></description>
        <styleUrl>#pingStyle</styleUrl>
        <MultiGeometry>
            <Point><coordinates>{lon},{lat},{KML_ALTITUDE}</coordinates></Point>
            <Polygon><extrude>1</extrude><altitudeMode>relativeToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{coords_str}</coordinates></LinearRing></outerBoundaryIs></Polygon>
        </MultiGeometry>
    </Placemark>""")
                lbs_written_count += 1
            except Exception as e:
                continue
    kml_content.append("</Folder>")

    return kml_start + "\n".join(kml_content) + "\n</Document>\n</kml>", lbs_written_count

# --- Streamlit UI ---
st.set_page_config(page_title="KML Generator", page_icon="📡", layout="centered")

st.title("📡 Cell Tower KML Generator")

# 1. Province Selection
province_code = st.selectbox(
    "Select Province", 
    options=list(CANADIAN_PROVINCES.keys()), 
    index=list(CANADIAN_PROVINCES.keys()).index('ON')
)

st.divider()

# 2. Tower Data Section
st.subheader("Enter Tower Data")
st.markdown("[Download ISED CSV](https://www.ic.gc.ca/engineering/SMS_TAFL_Files/Site_Data_Extract_FX.zip)")
st.info("Add or remove rows as needed. Leaving a row's ID blank will ignore it.")

tab1, tab2, tab3 = st.tabs(["5G Towers", "4G Towers", "2G/3G Towers"])

with tab1:
    df_5g_init = pd.DataFrame([{"CellID": None, "Radius_m": DEFAULT_RADIUS_METERS}] * 3)
    df_5g = st.data_editor(df_5g_init, num_rows="dynamic", use_container_width=True, key="5g")

with tab2:
    # MODIFIED: Changed label to 'Tower ID (Optional)'
    df_4g_init = pd.DataFrame([{"Tower ID (Optional)": None, "eNodeB": None, "CellID": None, "Radius_m": DEFAULT_RADIUS_METERS}] * 3)
    df_4g = st.data_editor(df_4g_init, num_rows="dynamic", use_container_width=True, key="4g")

with tab3:
    df_legacy_init = pd.DataFrame([{"LAC": None, "CellID": None, "Radius_m": DEFAULT_RADIUS_METERS}] * 3)
    df_legacy = st.data_editor(df_legacy_init, num_rows="dynamic", use_container_width=True, key="legacy")

st.divider()

# 3. LBS Pings Section
st.subheader("LBS Pings")
st.info("Upload an Excel file of pings, or enter them manually. You can do both at the same time!")

lbs_file = st.file_uploader("Upload LBS Pings (.xlsx)", type=['xlsx'])
st.caption("Required columns: Start Date/Time, Latitude, Longitude, Radius")

st.markdown("**Manual LBS Entry:**")
df_lbs_init = pd.DataFrame([{"Start Date/Time": None, "Latitude": None, "Longitude": None, "Radius": DEFAULT_RADIUS_METERS}] * 3)
df_lbs_manual = st.data_editor(df_lbs_init, num_rows="dynamic", use_container_width=True, key="lbs_manual")

st.divider()

# 4. Processing
if st.button("Generate KML", type="primary"):
    
    # --- Collect Manual LBS Data ---
    manual_lbs_list = []
    try:
        for _, row in df_lbs_manual.dropna(subset=['Latitude', 'Longitude']).iterrows():
            val_time = row['Start Date/Time']
            time_str = str(val_time) if pd.notna(val_time) and str(val_time).strip() != "" else "Manual Ping"
            
            manual_lbs_list.append({
                'Start Date/Time': time_str,
                'Latitude': float(row['Latitude']),
                'Longitude': float(row['Longitude']),
                'Radius': float(row['Radius'])
            })
    except ValueError:
        st.error("Ensure manual LBS Latitude, Longitude, and Radius are numbers.")
        st.stop()
        
    manual_lbs_df = pd.DataFrame(manual_lbs_list)
    lbs_data = None

    # --- Process LBS File if uploaded ---
    if lbs_file is not None:
        try:
            file_lbs_data = pd.read_excel(lbs_file)
            file_lbs_data.columns = file_lbs_data.columns.str.strip() 
            
            required_cols = ['Start Date/Time', 'Latitude', 'Longitude', 'Radius']
            missing = [c for c in required_cols if c not in file_lbs_data.columns]
            if missing:
                st.warning(f"LBS file is missing columns: {', '.join(missing)}. LBS file data will be skipped.")
            else:
                lbs_data = file_lbs_data
                st.success("LBS file loaded successfully!")
        except Exception as e:
            st.error(f"Error reading LBS file: {e}")

    # --- Merge Manual and Uploaded LBS Data ---
    if lbs_data is not None and not manual_lbs_df.empty:
        lbs_data = pd.concat([lbs_data, manual_lbs_df], ignore_index=True)
    elif lbs_data is None and not manual_lbs_df.empty:
        lbs_data = manual_lbs_df

    # --- Build calculation data for towers ---
    calc_data = []
    try:
        for _, row in df_5g.dropna(subset=['CellID']).iterrows():
            calc_data.append({'TowerID': str(int(row['CellID'])), 'CustomRadius': float(row['Radius_m'])})
            
        # MODIFIED: Look for 'Tower ID (Optional)' instead of 'Tower ID'
        for _, row in df_4g.iterrows():
            has_explicit_id = pd.notna(row.get('Tower ID (Optional)')) and str(row['Tower ID (Optional)']).strip() != ""
            has_calc_id = pd.notna(row.get('eNodeB')) and pd.notna(row.get('CellID'))
            
            if has_explicit_id:
                tid = str(int(float(row['Tower ID (Optional)'])))
                calc_data.append({'TowerID': tid, 'CustomRadius': float(row['Radius_m'])})
            elif has_calc_id:
                tid = str((int(row['eNodeB']) * ENODEB_MULTIPLIER) + int(row['CellID']))
                calc_data.append({'TowerID': tid, 'CustomRadius': float(row['Radius_m'])})
            
        for _, row in df_legacy.dropna(subset=['LAC', 'CellID']).iterrows():
            tid = f"{int(row['LAC'])}.*{int(row['CellID'])}"
            calc_data.append({'TowerID': tid, 'CustomRadius': float(row['Radius_m'])})
    except ValueError:
        st.error("Ensure all entered IDs are numbers.")
        st.stop()

    if not calc_data and (lbs_data is None or lbs_data.empty):
        st.warning("No tower data entered and no LBS data provided. Nothing to generate.")
    else:
        final_df = pd.DataFrame()
        
        if calc_data:
            target_file = f"split_data/{province_code.upper()}_towers.zip"
            
            if not os.path.exists(target_file):
                st.error(f"Server Error: Could not find the database for {province_code} at '{target_file}'.")
            else:
                with st.spinner(f'Searching {province_code} database...'):
                    df = pd.read_csv(target_file, low_memory=False, encoding='utf-8')
                    
                    mask = pd.Series([False] * len(df), index=df.index)
                    for item in calc_data:
                        tid = item['TowerID']
                        if '.*' in tid:
                            m = df['cell_id'].astype(str).str.contains(tid, na=False, regex=True)
                        else:
                            m = df['cell_id'].astype(str).str.contains(tid, na=False, regex=False)
                        mask |= m
                    
                    res = df[mask].drop_duplicates(subset=['cell_id'], keep='first').copy()
                    res['tx_ant_horiz_beamwidth'] = res['tx_ant_horiz_beamwidth'].fillna(359.0)
                    res['tx_ant_azimuth'] = res['tx_ant_azimuth'].fillna(0.0)
                    res['tx_ant_horiz_beamwidth'] = pd.to_numeric(res['tx_ant_horiz_beamwidth'], errors='coerce')
                    res['tx_ant_azimuth'] = pd.to_numeric(res['tx_ant_azimuth'], errors='coerce')

                    merged = []
                    for _, row in res.iterrows():
                        cid = str(row['cell_id'])
                        for item in calc_data:
                            if item['TowerID'].isdigit() and item['TowerID'] in cid:
                                row['TowerID'], row['CustomRadius'] = item['TowerID'], item['CustomRadius']
                                merged.append(row)
                                break 
                            elif '.*' in item['TowerID']:
                                parts = item['TowerID'].split('.*')
                                if len(parts) == 2 and parts[0] in cid and parts[1] in cid:
                                     row['TowerID'], row['CustomRadius'] = item['TowerID'], item['CustomRadius']
                                     merged.append(row)
                                     break
                    
                    final_df = pd.DataFrame(merged)
                    if final_df.empty:
                         st.warning("No matching records found for the entered tower IDs.")

        kml_string, actual_lbs_count = generate_kml_content(final_df, lbs_data)
        
        tower_count = len(final_df)
        
        st.success(f"Successfully generated KML! (Sectors: {tower_count} | LBS Pings: {actual_lbs_count})")
        
        st.download_button(
            label="⬇️ Download KML File",
            data=kml_string,
            file_name="Investigation_Map.kml",
            mime="application/vnd.google-earth.kml+xml"
        )
