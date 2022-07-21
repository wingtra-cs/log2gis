import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
import simplekml
import zipfile
import os
import pydeck as pdk

@st.experimental_singleton(suppress_st_warning=True, allow_output_mutation=True)
def create_df(df):
    df_final = pd.DataFrame()
    df_final['id'] = range(len(basis_col))
    df_final['id'] = df_final.index
    
    for col in df.columns:
        vals = []
        if '_y' not in col and col != 'id': 
            if col_len[col] < len(df[col]):
                col_num = pd.to_numeric(df[col][:col_len[col]])
            else:
                col_num = pd.to_numeric(df[col])
            for time in basis_col:
                if time != '':
                    index = abs(col_num - time).idxmin()
                    vals.append(float(df[col[:-2] + '_y'][index]))
            df_final[col.split(' > ')[1][:-2]] = vals
    
    return df_final

st.set_page_config(layout="wide")

st.title('GIS Visualization of Flight Log Data')

st.sidebar.image('./logo.png', width=260)
st.sidebar.markdown('#')
st.sidebar.write('This application visualizes extracted CSV data from the flight log (.ulg) file.')
st.sidebar.write('It requires the inclusion of global location parameters to proceed (latitude, longitude, altitude).')
st.sidebar.markdown('#')
st.sidebar.info('This is a prototype application. Wingtra AG does not guarantee correct functionality. Use with discretion.')


# Ask for the input and create the output location.
uploaded_csv = st.file_uploader('Please Select Extracted CSV file.', accept_multiple_files=False)
uploaded = False

if uploaded_csv is not None:
    if uploaded_csv.name.lower().endswith('.csv'):
        uploaded = True
    else:
        msg = 'Please upload a CSV file.'
        st.error(msg)
        st.stop()

if uploaded:
    try:
        file_name = uploaded_csv.name.split('.')[0]
        df = pd.read_csv(uploaded_csv, index_col=False)
        st.success('File Uploaded: ' + uploaded_csv.name + '.') 
    except:
        st.error('File selection error. Choose a valid CSV.')
        st.stop()

    # Simplify location naming
    lat = 'vehicle_global_position_0 > lat_y'
    lon = 'vehicle_global_position_0 > lon_y'
    
    alt = 'vehicle_global_position_0 > alt_y'
    alt_flag = False

    # Check if the lat and lon columns were selected
    if lon not in df.columns:
        st.error('Longitude Column is Absent.')
        if lat not in df.columns:
            st.error('Latitude Column is Absent.')
        st.error('Please ensure that at least the latitude and longitude parameters are available.')
        st.stop()

    else:
        with st.spinner('Processing Data...'):
            # Check if altitude was included    
            if alt in df.columns:
                alt_flag = True
        
            # Build the trajectory data frame
            trunc = len(df) - (df[lat] == ' ').sum()
            if alt_flag:
                traj_df = pd.concat([df[lat][:trunc],
                                     df[lon][:trunc],
                                     df[alt][:trunc]], 
                                    axis=1, keys=['lat','lon','alt'])
            else:
                traj_df = pd.concat([df[lat][:trunc],
                                     df[lon][:trunc]], 
                                    axis=1, keys=['lat','lon'])
        
            # Find shortest column
            col_len = {}
            for col in df.columns:
                if '_x' in col:
                    col_len[col] = len(df) - (df[col] == ' ').sum()
            
            shortest_col = min(col_len, key=col_len.get)
            
            # Get times of shortest column
            basis_col = df[shortest_col].tolist()
            basis_col = list(map(float,[x for x in basis_col if x != ' ']))
            
            # Build a new dataframe based on the times
            df_final = create_df(df)
        
            with zipfile.ZipFile(file_name + '_Outputs.zip', 'w') as out_zip:
                
                # Save the DataFrame as a CSV
                out_zip.writestr('Clean_CSV/' + file_name + '_Data.csv', df_final.to_csv(index=False))
                                           
                # Build the point shapefile 
                gdf = gpd.GeoDataFrame(df_final)
                gdf.set_geometry(gpd.points_from_xy(gdf['lon'], gdf['lat']), crs='EPSG:4326', inplace=True)
                gdf.drop(['lat', 'lon'], axis=1, inplace=True)
                
                os.makedirs('PointData_SHP', exist_ok=True)
                gdf.to_file('PointData_SHP/' + file_name + '_Points.shp.zip')
                out_zip.write('PointData_SHP/' + file_name + '_Points.shp.zip')
                
                # Build the trajectory shapefile
                traj_gdf = gpd.GeoDataFrame(traj_df)
                traj_points = gpd.points_from_xy(traj_gdf['lon'], traj_gdf['lat'])
                line_geom = [LineString(traj_points)]
                
                name = ['Flight Trajectory']
                gdf_line = gpd.GeoDataFrame(list(zip(name, line_geom)), columns=['Name', 'geometry'], crs='EPSG:4326')
                
                os.makedirs('Trajectory_SHP', exist_ok=True)
                gdf_line.to_file('Trajectory_SHP/' + file_name + '_FlightTrajectory.shp.zip')
                out_zip.write('Trajectory_SHP/' + file_name + '_FlightTrajectory.shp.zip')
                
                # Generate a KML of the flight trajectory
                line_kml = simplekml.Kml()
                linestring = line_kml.newlinestring(name="Flight Trajectory")
                linestring.style.linestyle.width = 3
                if not alt_flag:
                    linestring.coords = list(zip(traj_df.lon, traj_df.lat))        
                else:
                    linestring.coords = list(zip(traj_df.lon, traj_df.lat, traj_df.alt))
                    linestring.altitudemode = simplekml.AltitudeMode.absolute
                
                os.makedirs('Trajectory_KML', exist_ok=True)
                line_kml.save('Trajectory_KML/' + file_name + '_FlightTrajectory.kml')
                out_zip.write('Trajectory_KML/' + file_name + '_FlightTrajectory.kml')
            
    points_df = pd.concat([df_final['lat'], df_final['lon']], axis=1, keys=['lat','lon'])
    view = pdk.data_utils.viewport_helpers.compute_view(points_df, view_proportion=1)
    level = int(str(view).split('"zoom": ')[-1].split('}')[0])
    
    st.success('Processing Finished.')

    st.pydeck_chart(pdk.Deck(
        map_style='mapbox://styles/mapbox/satellite-streets-v11',
        initial_view_state=pdk.ViewState(
            latitude=points_df['lat'].mean(),
            longitude=points_df['lon'].mean(),
            zoom=level,
            pitch=0,
        ),
        layers=[
            pdk.Layer(
                'GeoJsonLayer',
                data=gdf_line['geometry'],
                get_line_color='[35, 205, 255]',
                lineWidthScale=8,
                opacity=0.5,
                pickable=True,
            ),
            ],
    ))   
    fp = open(file_name + '_Outputs.zip', 'rb')
    st.download_button(
        label="Download Data",
        data=fp,
        file_name=file_name + '_Outputs.zip',
        mime='application/zip',
        )
    st.stop()
else:
    st.stop()
