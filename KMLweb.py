import streamlit as st
import pandas as pd
import math
import os

# --- Configuration ---
ENODEB_MULTIPLIER = 256
DEFAULT_RADIUS_METERS = 2000
KML_ALTITUDE = 100

# Updated with correct frequency column names
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

def generate_kml_content(df):
    kml_start = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
    <name>Cell Tower Sectors</name>
    <Style id="sectorStyle">
        <LineStyle><color>ff0000ff</color><width>1.5</width></LineStyle>
        <PolyStyle><color>7000ffff</color><fill>1</fill><outline>1</outline></PolyStyle>
    </Style>"""
    kml_content = []
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
        <name>{new_title}</name>
        <description><![CDATA[{description_html}]]></description>
        <styleUrl>#sectorStyle</styleUrl>
        <Point><coordinates>{row['longitude']},{row['latitude']},{KML_ALTITUDE}</coordinates></Point>
        <Polygon><extrude>1</extrude><altitudeMode>relativeToGround</altitudeMode><outerBoundaryIs><LinearRing><coordinates>{coords_str}</coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>""")
        except Exception:
            continue
    return kml_start + "\n".join(kml_content) + "\n</Document>\n</kml>"

# --- Streamlit UI ---
st.set_page_config(page_title="KML Generator", page_icon="📡", layout="centered")

st.title("📡 Cell Tower KML Generator")
st.markdown("Enter tower data below to generate your KML file.")

# 1. Province Selection
province_code = st.selectbox(
    "Select Province", 
    options=list(CANADIAN_PROVINCES.keys()), 
    index=list(CANADIAN_PROVINCES.keys()).index('ON')
)

# 2. Data Entry Tables
st.subheader("Enter Tower Data")
st.info("Add or remove rows as needed. Leaving a row's ID blank will ignore it.")

tab1, tab2, tab3 = st.tabs(["5G Towers", "4G Towers", "2G/3G Towers"])

with tab1:
    df_5g_init = pd.DataFrame([{"CellID": None, "Radius_m": DEFAULT_RADIUS_METERS}] * 3)
    df_5g = st.data_editor(df_5g_init, num_rows="dynamic", use_container_width=True, key="5g")

with tab2:
    df_4g_init = pd.DataFrame([{"eNodeB": None, "CellID": None, "Radius_m": DEFAULT_RADIUS_METERS}] * 3)
    df_4g = st.data_editor(df_4g_init, num_rows="dynamic", use_container_width=True, key="4g")

with tab3:
    df_legacy_init = pd.DataFrame([{"LAC": None, "CellID": None, "Radius_m": DEFAULT_RADIUS_METERS}] * 3)
    df_legacy = st.data_editor(df_legacy_init, num_rows="dynamic", use_container_width=True, key="legacy")

# 3. Processing
if st.button("Generate KML", type="primary"):
    # Build calculation data
    calc_data = []
    try:
        for _, row in df_5g.dropna(subset=['CellID']).iterrows():
            calc_data.append({'TowerID': str(int(row['CellID'])), 'CustomRadius': float(row['Radius_m'])})
            
        for _, row in df_4g.dropna(subset=['eNodeB', 'CellID']).iterrows():
            tid = str((int(row['eNodeB']) * ENODEB_MULTIPLIER) + int(row['CellID']))
            calc_data.append({'TowerID': tid, 'CustomRadius': float(row['Radius_m'])})
            
        for _, row in df_legacy.dropna(subset=['LAC', 'CellID']).iterrows():
            tid = f"{int(row['LAC'])}.*{int(row['CellID'])}"
            calc_data.append({'TowerID': tid, 'CustomRadius': float(row['Radius_m'])})
    except ValueError:
        st.error("Ensure all entered IDs are numbers.")
        st.stop()

    if not calc_data:
        st.warning("No valid tower data entered.")
    else:
        # Construct the file path based on the selected province (looking for .zip)
        target_file = f"split_data/{province_code.upper()}_towers.zip"
        
        if not os.path.exists(target_file):
            st.error(f"Server Error: Could not find the database for {province_code} at '{target_file}'. Please ensure the 'split_data' folder contains the zipped CSVs.")
        else:
            with st.spinner(f'Searching {province_code} database...'):
                # Pandas automatically decompresses the zip file to read the CSV inside
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
                st.warning("No matching records found for the entered IDs.")
            else:
                kml_string = generate_kml_content(final_df)
                st.success(f"Successfully generated KML for {len(final_df)} sectors!")
                
                st.download_button(
                    label="⬇️ Download KML File",
                    data=kml_string,
                    file_name="Cell_Tower_Sectors.kml",
                    mime="application/vnd.google-earth.kml+xml"
                )