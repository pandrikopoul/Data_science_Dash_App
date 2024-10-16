import pika
from datetime import date, datetime, timedelta
from dash import Input, Output, State, callback_context
import dash_daq as daq  # Import dash_daq
import datetime
from IPython.display import display, HTML
from dash.dash_table import DataTable
import dash_bootstrap_components as dbc
from dash import dcc, html
from scipy.stats import pearsonr
from scipy.stats import gmean
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import plotly.graph_objects as go  # Import for creating the second graph
import time
from dash.dependencies import Input, Output
from dash import html
from dash import dcc
import dash
import plotly.express as px
from retry_requests import retry
import requests_cache
import openmeteo_requests
from geopy.geocoders import Nominatim
from dash.dependencies import Input, Output, State
import pandas as pd
from threading import Thread
import os
from sqlalchemy import create_engine, text, inspect, Table


def log_action(service_name, message):
    try:
        service_indicator = service_name.upper()[0]
    except:
        service_indicator = "X"

    TIMESTAMP = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f" [{TIMESTAMP}] - [{service_indicator}] {message}")


SERVER_SERVICE_NAME = os.getenv('SERVER_SERVICE_NAME', 'server')
INDICATOR = SERVER_SERVICE_NAME.upper()[0]
SERVER_QUEUE = os.getenv('SERVER_QUEUE', 'server_queue')
engine = create_engine(
    "postgresql://student:infomdss@database:5432/dashboard")

# Create Dash app
app = dash.Dash(__name__, external_stylesheets=[
                dbc.themes.BOOTSTRAP], title="Agriculture Dashboard")
# Define the style dictionary
style = {
    'width': '33%',
    'maxWidth': '400px',
    'margin': '0 auto'
}


def load_and_prepare_data(ch, method, properties, body):
    global current_date, current_date_or, FAOSTAT
    global yearly_average_merged_data, yearly_totals
    global average_growth_rate, mean_value, geom_mean_value
    global min_value, min_year, max_value, max_year, top_products
    global top_5_products, merged_df, correlations, top_5_correlations

    if body is not None:
        try:
            log_action(SERVER_SERVICE_NAME, f"Received {body.decode()}")
        except Exception as e:
            pass

    # LOAD CROP DATA
    # FAOSTAT = pd.read_csv("/data/FAOSTAT_nozer.csv")
    FAOSTAT = None

    with engine.connect() as connection:
        # QCL is in quotes because of case sensitivity
        result = connection.execute(text('SELECT * FROM "QCL"'))
        data = result.fetchall()
        columns = result.keys()
        FAOSTAT = pd.DataFrame(data, columns=columns)

    log_action(SERVER_SERVICE_NAME,
               f"Loaded {FAOSTAT.shape[0]} rows from FAOSTAT")
    # LOAD WEATHER DATA
    yearly_average_merged_data = pd.read_csv(
        "/data/final_yearly_merged_data.csv")

    # with engine.connect() as connection:
    #     result = connection.execute(text("SELECT * FROM Weather"))
    #     data = result.fetchall()
    #     columns = result.keys()
    #     FAOSTAT = pd.DataFrame(data, columns=columns)

    # CREAT THE DATASET WITH THE TOTAL CROP PER YEAR
    yearly_totals = FAOSTAT.groupby('Year')['Value'].sum().reset_index()

    # Calculate and print the average growth rate
    average_growth_rate = calculate_average_growth_rate(yearly_totals)

    # CALCULATE STATISTICS FOR TOTAL CROP YIELD THROUGH THE YEARS #################
    # 1. Calculate Mean Value
    mean_value = yearly_totals['Value'].mean()

    # 2. Calculate Geometric Mean
    geom_mean_value = average_growth_rate

    # 3. Calculate Min Value and the Year it Occurs
    min_value = yearly_totals['Value'].min()
    min_year = yearly_totals['Year'][yearly_totals['Value'].idxmin()]

    # 4. Calculate Max Value and the Year it Occurs
    max_value = yearly_totals['Value'].max()
    max_year = yearly_totals['Year'][yearly_totals['Value'].idxmax()]

    # CALCULATE CORRELATION BETWEEN WEATHER ATTRIBUTES AND CROP ####################
    # Calculate total production by product
    top_products = FAOSTAT.groupby('Item')['Value'].sum().reset_index()

    # Sort the products by value in descending order and get the top 5
    top_5_products = top_products.nlargest(
        5, 'Value').sort_values(by='Value', ascending=False)

    # Merge DataFrames on Year
    merged_df = pd.merge(yearly_average_merged_data, yearly_totals, on='Year')

    # Calculate Pearson correlations
    correlations = {}
    for column in merged_df.columns:
        if column not in ['Year', 'Value']:
            correlation_coefficient, _ = pearsonr(
                merged_df[column], merged_df['Value'])
            correlations[column] = correlation_coefficient

    # Get the top 5 most correlated weather attributes
    top_5_correlations = pd.Series(correlations).nlargest(5).reset_index()
    top_5_correlations.columns = ['Attribute', 'Correlation']

    # Convert correlation to percentage
    top_5_correlations['Correlation'] = (
        top_5_correlations['Correlation'] * 100).round(2)

    current_date_or = date.today()
    # Get current date - 1 day  i cases the data source isnt updated
    current_date = date.today() - timedelta(days=1)


def calculate_average_growth_rate(yearly_totals):
    """
    Calculates the average growth rate using the geometric mean.

    Args:
        yearly_totals: DataFrame with 'Year' and 'Value' columns.

    Returns:
        The average growth rate.
    """

    # Calculate yearly growth rates
    yearly_growth_rates = yearly_totals['Value'].pct_change().dropna() + 1

    # Calculate the geometric mean of growth rates
    average_growth_rate = gmean(yearly_growth_rates) - 1

    return average_growth_rate


current_date_or = date.today()
# Get current date - 1 day  i cases the data source isnt updated
current_date = date.today() - timedelta(days=1)

# GENERAL STATISTIC INFO FOR TOTAL CROP YIEL ###################################
load_and_prepare_data(None, None, None, None)


def create_cards():
    return html.Div(
        style={'display': 'flex', 'flexWrap': 'nowrap',
               'overflowX': 'auto', 'justifyContent': 'center'},  # Flexbox settings
        children=[
            dbc.Card(
                dbc.CardBody([
                    html.H5("Average Crop Production", className="card-title"),
                    html.P(f"{mean_value:.2f}", className="card-text")
                ]),
                # Adjust width as needed
                style={'backgroundColor': '#f8f9fa',
                       'boxShadow': '0 4px 8px rgba(0,0,0,0.2)', 'borderRadius': '10px', 'padding': '20px', 'flex': '0 0 200px', 'marginRight': '10px'}
            ),
            dbc.Card(
                dbc.CardBody([
                    html.H5("Average Growth Rate of Crop yield(1961-2022)",
                            className="card-title"),
                    html.P(f"{geom_mean_value*100:.2f}%",
                           className="card-text")
                ]),
                style={'backgroundColor': '#f8f9fa',
                       'boxShadow': '0 4px 8px rgba(0,0,0,0.2)', 'borderRadius': '10px', 'padding': '20px', 'flex': '0 0 200px', 'marginRight': '10px'}
            ),
            dbc.Card(
                dbc.CardBody([
                    html.H5("Minimum Crop production (Year)",
                            className="card-title"),
                    html.P(f"{min_value:.2f} ({min_year})",
                           className="card-text")
                ]),
                style={'backgroundColor': '#f8f9fa',
                       'boxShadow': '0 4px 8px rgba(0,0,0,0.2)', 'borderRadius': '10px', 'padding': '20px', 'flex': '0 0 200px', 'marginRight': '10px'}
            ),
            dbc.Card(
                dbc.CardBody([
                    html.H5("Maximum crop production (Year)",
                            className="card-title"),
                    html.P(f"{max_value:.2f} ({max_year})",
                           className="card-text")
                ]),
                style={'backgroundColor': '#f8f9fa',
                       'boxShadow': '0 4px 8px rgba(0,0,0,0.2)', 'borderRadius': '10px', 'padding': '20px', 'flex': '0 0 200px', 'marginRight': '10px'}
            ),
        ]
    )


app.layout = dbc.Container(
    fluid=True,
    children=[    # define the components shown in the app GUI


        # html.Div([
        #     dcc.DatePickerRange(
        #         id='date-picker-range',
        #         min_date_allowed=date(2001, 9, 12),  # Minimum allowed date
        #         max_date_allowed=current_date_or,      # Maximum allowed date (current date)
        #         initial_visible_month=current_date,
        #         start_date=date(2023, 9, 12).strftime('%Y-%m-%d'),  # Default start_date
        #         end_date=current_date.strftime('%Y-%m-%d'),        # Default end_date
        #         style=style  # Apply the style
        #     )
        # ], style={'padding': 10}),

        # CARD PLOT GNERAL STATISTICS FOR TOTAL CROP YIELD THROUGH YEARS ############
        dbc.Container([
            html.H1("Statistics Summary", className="text-center mb-4",
                    style={'color': '#343a40'}),
            create_cards()  # Insert cards here
        ], fluid=True),

        # WEATHER AND CROP DATA VISUALIZATION #######################################
        html.H1(children="Weather and Crop Data Visualization"),
        html.Div(
            style={
                'display': 'flex',
                'justifyContent': 'center',  # Center horizontally
                'alignItems': 'center',  # Center vertically if needed
                'gap': '10px',  # Reduced space between dropdowns
                'padding': '20px'  # Optional padding around the container
            },
            children=[
                dcc.Dropdown(
                    id='yearly-data-feature',
                    options=[{'label': col, 'value': col}
                             for col in yearly_average_merged_data.columns if col != 'Year'],
                    # Default value (first column after 'Year')
                    value=yearly_average_merged_data.columns[1],
                    className='dropdown-container',
                    clearable=False,
                    searchable=True,
                    style={
                        'width': '300px',  # Increased width for better visibility
                        'fontSize': '16px',  # Increase font size for better readability
                        'border': '1px solid #ccc',  # Light border
                        'backgroundColor': '#f9f9f9',  # Light background color
                        'color': '#333',  # Text color
                    },
                    optionHeight=60

                ),
                dcc.Dropdown(
                    id='faostat-item',
                    options=[{'label': item, 'value': item}
                             for item in FAOSTAT['Item'].unique()],
                    # Default value (first Item)
                    value=FAOSTAT['Item'].unique()[2],
                    className='dropdown-container',
                    clearable=False,
                    searchable=True,
                    style={
                        'width': '300px',  # Increased width for better visibility
                        'fontSize': '16px',  # Increase font size for better readability
                        'border': '1px solid #ccc',  # Light border
                        'backgroundColor': '#f9f9f9',  # Light background color
                        'color': '#333',  # Text color
                    },
                    optionHeight=60

                )
            ]
        ),

        dcc.Graph(id='yield-graph'),  # New graph for yield data

        # SCATTER PLOT FOR CORELLATION BETWEEN WEATHER ATTRIBUTES AND CROP YIELD ####
        html.H1(children="Correlation between weather attributes and crop yield"),
        html.Div(
            style={
                'display': 'flex',
                'justifyContent': 'center',  # Center horizontally
                'alignItems': 'center',  # Center vertically if needed
                'gap': '10px',  # Reduced space between dropdowns
                'padding': '20px'  # Optional padding around the container
            },
            children=[
                dcc.Dropdown(
                    id='item-dropdown',
                    options=[{'label': item, 'value': item}
                             for item in FAOSTAT['Item'].unique()],
                    value='Mushrooms and truffles',  # Default value
                    className='dropdown-container',
                    clearable=False,
                    searchable=True,
                    style={
                        'width': '300px',  # Increased width for better visibility
                        'fontSize': '16px',  # Increase font size for better readability
                        'border': '1px solid #ccc',  # Light border
                        'backgroundColor': '#f9f9f9',  # Light background color
                        'color': '#333',  # Text color
                    },
                    optionHeight=60

                ),
                dcc.Dropdown(
                    id='weather-attribute-dropdown',
                    options=[{'label': col, 'value': col}
                             for col in yearly_average_merged_data.columns if col != 'Year'],
                    value="Mean 2m temperature",  # Default value
                    className='dropdown-container',
                    clearable=False,
                    searchable=True,
                    style={
                        'width': '300px',  # Increased width for better visibility
                        'fontSize': '16px',  # Increase font size for better readability
                        'border': '1px solid #ccc',  # Light border
                        'backgroundColor': '#f9f9f9',  # Light background color
                        'color': '#333',  # Text color
                    },
                    optionHeight=60

                )
            ]
        ),
        # add the gauge meters and put them in the same line with the scatter plot
        html.Div(
            className='row',
            style={'display': 'flex', 'align-items': 'center',
                   'justify-content': 'space-between', 'flex-wrap': 'wrap'},  # Ensure flexible layout
            children=[
                # Scatter plot
                # Make the graph flexible and responsive
                html.Div(
                    className='col-xl-6 col-lg-6 col-md-6 mb-6',  # Responsive columns
                    children=[
                        dcc.Graph(id='scatter-plot',
                                  style={'flex': '1 1 60%', 'min-width': '300px'}),
                    ]
                ),


                # Gauge meters
                html.Div(
                    className='col-xl-6 col-lg-6 col-md-6',
                    style={'display': 'flex', 'flex-direction': 'column', 'flex': '1 1 30%',
                           'min-width': '250px', 'margin-left': '20px'},  # Flexible layout for the gauges
                    children=[
                        daq.Gauge(
                            id='correlation-gauge',
                            label="Correlation",
                            value=0,  # Initial value, will be updated
                            max=1,
                            min=-1,
                            color={"gradient": True, "ranges": {
                                "green": [0.8, 1], "yellow": [0.5, 0.8], "red": [-1, 0.5]}}
                        ),
                        daq.Gauge(
                            id='p-value-gauge',
                            label="Trustability",
                            value=0,  # Initial value, will be updated
                            max=1,
                            color={"gradient": True, "ranges": {
                                "green": [0.95, 1], "yellow": [0.8, 0.95], "red": [0, 0.8]}}
                        ),
                    ]
                ),
            ]
        ),


        # TOTAL CROP YIELD THROUGH THE YEARS ########################################
        html.H1(children="Total Crop yield through the years"),
        daq.ToggleSwitch(
            id='start-tutorial',
            label='Help',
            labelPosition='bottom',
            value=False,
            color='green'
        ),
        # Store for current tutorial step
        dcc.Store(id='current-step-store', data={'step': 0}),

        # Overlay for tutorial instructions
        html.Div(id='tutorial-overlay', style={'display': 'none', 'position': 'absolute',
                                               'background-color': 'rgba(0, 0, 0, 0.5)',
                                               'color': 'white',
                                               'padding': '20px',
                                               'border-radius': '5px',
                                               'z-index': '1000'}),

        # Line graph is visible initially
        dcc.Graph(id='line-graph', style={'display': 'block'}),
        # Pie chart hidden initially
        dcc.Graph(id='pie-chart', style={'display': 'none', 'width': '100%'}),
        html.Button('Back to Line Chart', id='back-button',
                    style={'display': 'none'}),  # Back button hidden initially

        # TOP MOST PRODUCED CROPS IN NETHERLANDS AND TOP MOST CORRELATE WEATHER ATTRIBUTES ##################################
        html.Div(style={
            'padding': '20px',
            'fontFamily': 'Arial, sans-serif',
            'color': '#333',
            'display': 'flex',
            'justifyContent': 'space-between'  # Align children in a row
        }, children=[
            # Left box for top 5 most produced crops
            html.Div(style={
                'border': '1px solid #ccc',
                'borderRadius': '8px',
                'padding': '20px',
                'margin': '0',
                'width': '48%',  # Adjusted width to fit side by side
                'backgroundColor': '#ffffff',
                'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.1)'
            }, children=[
                html.H1("Top 5 Most Produced Crops in the Netherlands",
                        style={'textAlign': 'left', 'color': '#4a4a4a'}),
                *[html.Div(style={'margin': '10px 0', 'padding': '10px', 'backgroundColor': '#f1f1f1', 'borderRadius': '5px'},
                           children=[
                    html.H3(f"{i + 1}. {row.Item}",
                            style={'margin': '0', 'color': '#333'}),
                    html.P(f"Quantity in tons: {row.Value}", style={
                        'margin': '0', 'color': '#555'})
                ])
                    for i, row in enumerate(top_5_products.itertuples(index=False))]  # Use enumerate for correct numbering
            ]),

            # Right box for top 5 most correlated weather attributes
            html.Div(style={
                'border': '1px solid #ccc',
                'borderRadius': '8px',
                'padding': '20px',
                'margin': '0',
                'width': '48%',  # Adjusted width to fit side by side
                'backgroundColor': '#ffffff',
                'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.1)'
            }, children=[
                html.H1("Top 5 Most Correlated Weather Attributes with Crop Production", style={
                    'textAlign': 'left', 'color': '#4a4a4a'}),
                *[html.Div(style={'margin': '10px 0', 'padding': '10px', 'backgroundColor': '#f1f1f1', 'borderRadius': '5px'},
                           children=[
                    html.H3(f"{row.Attribute}", style={
                        'margin': '0', 'color': '#333'}),
                    html.P(f"Correlation: {row.Correlation}%", style={
                        'margin': '0', 'color': '#555'})
                ])
                    for row in top_5_correlations.itertuples(index=False)]  # Iterate through the rows
            ])

        ])



    ])
# Tutorial
# Callback to control tutorial steps


@app.callback(
    Output('tutorial-overlay', 'style'),
    Output('tutorial-overlay', 'children'),
    Output('start-tutorial', 'value'),  # Output for the toggle switch
    Input('start-tutorial', 'value'),
    Input('line-graph', 'clickData'),  # Check for click data on line graph
    Input('back-button', 'n_clicks'),   # Check for back button clicks
)
def update_tutorial(start_tutorial, clickData, n_clicks):
    # Tutorial steps
    steps = [
        {'content': 'Click on a point in the line graph to see the crop distribution for that year.'},
        {'content': 'This pie chart shows the distribution of crop values for the selected year. Use the back button to return.'}
    ]

    # If the tutorial is started
    if start_tutorial:
        if n_clicks:  # If back button is clicked
            # Hide the tutorial and turn off the toggle
            return {'display': 'none'}, "", False

        if clickData:  # If a point on the line graph is clicked
            # Show pie chart tutorial step
            return {'display': 'block'}, steps[1]['content'], True

        # If no interaction yet, show the first step
        # Show line graph tutorial step
        return {'display': 'block'}, steps[0]['content'], True

    # If the tutorial is not active and back button is not clicked, ensure to reset
    return {'display': 'none'}, "", False  # Reset tutorial when not active


# Tutorial


# BAR CHART OF WEATHER ATTRIBUTES AND CROP YIELD#################################
@app.callback(
    Output('yield-graph', 'figure'),
    [Input('yearly-data-feature', 'value'),
     Input('faostat-item', 'value')]
)
def update_yield_graph(selected_feature, selected_item):
    filtered_faostat = FAOSTAT[FAOSTAT['Item'] == selected_item]

    fig = go.Figure()

    fig.add_trace(go.Bar(x=yearly_average_merged_data['Year'],
                         y=yearly_average_merged_data[selected_feature],
                         name=selected_feature,
                         offsetgroup=0))  # Assign to first offset group

    fig.add_trace(go.Bar(x=filtered_faostat['Year'],
                         y=filtered_faostat['Value'],
                         name=selected_item,
                         offsetgroup=1,   # Assign to second offset group
                         yaxis='y2'))  # Assign to secondary y-axis

    fig.update_layout(title=f"{selected_feature} and {selected_item} over Time",
                      xaxis_title="Year",
                      yaxis_title=selected_feature,
                      yaxis2=dict(title=selected_item,
                                  overlaying='y', side='right'),
                      barmode='group')  # Set barmode to 'group'

    return fig

# SCATTER PLOT FOR CORRELATION OF CROP AND WEATHER ATRIBUTES ####################


@app.callback(
    Output('scatter-plot', 'figure'),
    Output('correlation-gauge', 'value'),  # Output for correlation gauge
    Output('p-value-gauge', 'value'),    # Output for p-value gauge
    [Input('item-dropdown', 'value'),
     Input('weather-attribute-dropdown', 'value')]
)
def update_scatter_plot(item_name, weather_column):
    value_column = 'Value'

    # Filter FAOSTAT data for the specified item
    item_faostat_data = FAOSTAT[FAOSTAT['Item'] == item_name]

    # Merge the DataFrames based on 'Year'
    merged_data = pd.merge(yearly_average_merged_data, item_faostat_data[[
                           'Year', value_column]], on='Year', how='inner')

    # Extract data for plotting and scaling
    x = merged_data[value_column].values.reshape(-1, 1)
    y = merged_data[weather_column].values.reshape(-1, 1)

    # Calculate Pearson correlation BEFORE scaling
    correlation, p_value = pearsonr(x.flatten(), y.flatten())

    # MinMax scaling
    scaler_x = MinMaxScaler()
    scaler_y = MinMaxScaler()
    x_scaled = scaler_x.fit_transform(x)
    y_scaled = scaler_y.fit_transform(y)

    # Create scatter plot using plotly.express
    fig = px.scatter(
        x=x_scaled.flatten(),
        y=y_scaled.flatten(),
        labels={
            'x': f"{item_name} Production ({value_column}) - Scaled", 'y': f"{weather_column} - Scaled"},
        title=f"Scatter Plot: {item_name} Production vs. {weather_column}",
        width=700,  # Set the width
        height=700
    )

    # Add correlation annotation to the plot
    fig.add_annotation(
        x=0.5,
        y=0.95,
        text=f"Correlation: {correlation:.2f}",

        showarrow=False,
        font=dict(size=14)
    ),
    fig.add_annotation(
        x=0.5,
        y=0.90,  # Adjust y position for the p-value annotation
        text=f"P-value: {p_value:.10f}",  # Format p-value to 3 decimal places
        showarrow=False,
        font=dict(size=14)
    )

    return fig, correlation, 1-p_value


# LINE GRAPH FOR TOTAL CROP YIELD THROUGH YEARS #################################
@app.callback(
    Output('line-graph', 'figure'),
    Input('line-graph', 'id')  # dummy input to trigger initial rendering
)
def update_line_graph(_):
    # Create line graph with yearly totals
    fig = go.Figure(go.Scatter(
        x=yearly_totals['Year'], y=yearly_totals['Value'], mode='lines+markers'))
    fig.update_layout(xaxis_title='Year', yaxis_title='Total Value')
    return fig

# DRILL DOW PIE CHART FOR CROP DISTRIBUTION #####


@app.callback(
    Output('line-graph', 'style'),
    Output('pie-chart', 'figure'),
    Output('pie-chart', 'style'),
    Output('back-button', 'style'),
    Input('line-graph', 'clickData'),
    Input('back-button', 'n_clicks'),
    State('line-graph', 'style'),
    State('current-step-store', 'data')  # Get current tutorial step
)
def toggle_pie_chart(clickData, n_clicks, line_graph_style, current_step_data):
    if clickData and line_graph_style['display'] == 'block':
        clicked_year = clickData['points'][0]['x']
        year_data = FAOSTAT[FAOSTAT['Year'] == clicked_year]
        total_value = year_data['Value'].sum()

        pie_data = go.Pie(
            labels=year_data['Item'], values=year_data['Value'], hole=0.3)
        pie_fig = go.Figure(data=[pie_data])
        pie_fig.update_layout(
            title=f'Distribution for {clicked_year}',
            height=1000,
            width=1400,
            autosize=True,
            margin=dict(l=50, r=50, t=100, b=50),
            legend=dict(x=1.05, y=0.5, orientation='v'),
            paper_bgcolor='rgba(0,0,0,0)',
        )
        pie_fig.add_annotation(
            text=f'Total:<br>{total_value}',
            font_size=15,
            showarrow=False,
            x=0.5,
            y=0.5,
            align='center',
            bgcolor='rgba(255, 255, 255, 0.8)',
            bordercolor='black',
            borderwidth=1
        )

        # Show pie chart, hide line chart, and show the "Back" button
        return {'display': 'none'}, pie_fig, {'display': 'block'}, {'display': 'block'}

    if n_clicks:
        return {'display': 'block'}, {}, {'display': 'none'}, {'display': 'none'}

    return {'display': 'block'}, {}, {'display': 'none'}, {'display': 'none'}


def on_message(channel, method_frame, header_frame, body):
    log_action(SERVER_SERVICE_NAME,
               f"Received message: {body.decode('utf-8')}")
    # Manually acknowledge the message
    channel.basic_ack(delivery_tag=method_frame.delivery_tag)


def on_connected(connection):
    # Open a channel once the connection is established
    connection.channel(on_open_callback=on_channel_open)


def on_channel_open(channel):
    # Declare the queue
    channel.queue_declare(queue=SERVER_QUEUE)
    # Start consuming messages
    channel.basic_consume(SERVER_QUEUE, load_and_prepare_data)


def rabbitmq_consumer():
    parameters = pika.ConnectionParameters(host='rabbitmq', heartbeat=600)
    connection = pika.SelectConnection(
        parameters, on_open_callback=on_connected)

    log_action(SERVER_SERVICE_NAME, "Starting RabbitMQ consumer...")
    # Non-blocking I/O loop
    try:
        connection.ioloop.start()
    except Exception as e:
        log_action(SERVER_SERVICE_NAME, f"Error in consumer: {e}")
        connection.ioloop.stop()


# Run the app
if __name__ == '__main__':

    consumer_thread = Thread(target=rabbitmq_consumer, daemon=True)
    consumer_thread.start()

    app.run_server(debug=True, host='0.0.0.0', port=8050, use_reloader=True)
