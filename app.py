# remora_tracker/app.py

import dash
from dash import html, dcc
import plotly.graph_objs as go
from dash.dependencies import Input, Output
import yfinance as yf
import numpy as np

app = dash.Dash(__name__, suppress_callback_exceptions=True)

# Only tracking WES Tail Hedge
warrants_data = {
    "WES Tail Hedge (KOQ)": {"long_ko": 60.00, "short_ko": 97.14, "gearing": 73}  # WESKOQ
}

interval_presets = {
    'Turbo Mode (10s)': 10,
    'Coffee Break (120s)': 120,
    'Cruise (60s)': 60,
    'Nap Time (300s)': 300
}

app.layout = html.Div(
    style={'overflow': 'hidden', 'height': '100vh'},
    children=[
        html.H2("🪝 Remora Tail Risk Tracker - WES Live"),

        dcc.Dropdown(
            id='ticker-dropdown',
            options=[{'label': symbol, 'value': symbol} for symbol in warrants_data.keys()],
            value='WES Tail Hedge (KOQ)'
        ),

        html.Label("☕ Preset Update Intervals:"),
        dcc.Dropdown(
            id='preset-dropdown',
            options=[{'label': k, 'value': v} for k, v in interval_presets.items()],
            value=60
        ),

        html.Label("⏱ Custom Interval (seconds):"),
        dcc.Slider(
            id='interval-slider',
            min=10, max=300, step=10,
            value=60,
            marks={i: f'{i}s' for i in range(10, 301, 30)}
        ),

        dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0),
        html.Div(id='live-price-display'),

        dcc.Graph(id='buffer-chart', style={'height': '300px'}),
        dcc.Graph(id='simulation-chart', style={'height': '300px'})
    ]
)

@app.callback(Output('interval-slider', 'value'), Input('preset-dropdown', 'value'))
def sync_preset_to_slider(preset_value):
    return preset_value

@app.callback(Output('interval-component', 'interval'), Input('interval-slider', 'value'))
def update_interval(seconds):
    return seconds * 1000

@app.callback(
    [Output('live-price-display', 'children'),
     Output('buffer-chart', 'figure'),
     Output('simulation-chart', 'figure')],
    [Input('interval-component', 'n_intervals'),
     Input('ticker-dropdown', 'value')]
)
def update_live_price(n, label):
    try:
        data = yf.Ticker("WES.AX")
        hist = data.history(period="6mo", interval="1d", auto_adjust=True)
        if hist.empty:
            return html.P("No data available..."), go.Figure(), go.Figure()

        current_price = hist['Close'].iloc[-1]
        long_ko = warrants_data[label]['long_ko']
        short_ko = warrants_data[label]['short_ko']
        gearing = warrants_data[label]['gearing']

        long_buffer = ((current_price - long_ko) / long_ko) * 100
        short_buffer = ((short_ko - current_price) / short_ko) * 100

        long_color = "green" if long_buffer >= 5 else "orange"
        short_color = "red" if short_buffer >= 5 else "darkred"
        risk_tag = "🧨 HIGH RISK" if gearing > 50 else ("⚠️ MODERATE" if gearing > 30 else "✅ Stable")

        display_text = html.Div([
            html.H4(f"Current WES Price: ${current_price:.2f}"),
            html.P(f"🟢 MINI Long KO: ${long_ko} | Buffer: {long_buffer:.2f}%"),
            html.P(f"🔴 MINI Short KO: ${short_ko} | Buffer: {short_buffer:.2f}%"),
            html.P(f"📈 Gearing: {gearing:.2f}x → {risk_tag}")
        ])

        # Gauge chart
        fig = go.Figure()
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=long_buffer,
            title={'text': "LONG KO Buffer %"},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': long_color}},
            domain={'x': [0, 0.4], 'y': [.6, 1]}
        ))
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=short_buffer,
            title={'text': "SHORT KO Buffer %"},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': short_color}},
            domain={'x': [0.2, .6], 'y': [0.6, 1]}
        ))
        fig.update_layout(margin=dict(t=50, b=0, l=0, r=0))

        # Monte Carlo simulation
        log_returns = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        mu = log_returns.mean()
        sigma = log_returns.std()
        paths = 10
        steps = 30
        dt = 1
        sim_paths = np.zeros((steps, paths))
        sim_paths[0] = current_price
        for i in range(1, steps):
            rand = np.random.normal(0, 1, paths)
            sim_paths[i] = sim_paths[i-1] * np.exp((mu - 0.5 * sigma**2)*dt + sigma * np.sqrt(dt) * rand)

        sim_fig = go.Figure()
        for j in range(paths):
            sim_fig.add_trace(go.Scatter(
                x=list(range(steps)),
                y=sim_paths[:, j],
                mode='lines',
                name=f'Path {j+1}',
                line=dict(width=1)
            ))
        sim_fig.add_hline(y=long_ko, line=dict(color='green', dash='dot'), annotation_text="LONG KO", annotation_position="bottom left")
        sim_fig.add_hline(y=short_ko, line=dict(color='red', dash='dot'), annotation_text="SHORT KO", annotation_position="top left")
        sim_fig.update_layout(title="📉 Simulated 30-Day Price Paths", height=300, margin=dict(t=30, b=30))

        return display_text, fig, sim_fig

    except Exception as e:
        return html.P(f"Error loading data: {e}"), go.Figure(), go.Figure()

if __name__ == '__main__':
    app.run(debug=True, port=8051)
