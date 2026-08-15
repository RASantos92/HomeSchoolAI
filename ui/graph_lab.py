import streamlit as st
import numpy as np
import plotly.graph_objects as go
from streamlit_plotly_events import plotly_events


def _qp_get(key: str, default=None):
    try:
        # new API (>=1.30)
        return st.query_params.get(key, default)
    except Exception:
        # legacy API
        val = st.experimental_get_query_params().get(key, [default])
        return val if isinstance(val, str) else (val[0] if val else default)


def _qp_set(**kwargs):
    try:
        st.query_params.update(kwargs)
    except Exception:
        st.experimental_set_query_params(**kwargs)


def _build_click_figure(clicked_pts):
    """Build a figure that shows existing points and the last fitted line (if >=2 pts)."""
    fig = go.Figure()
    fig.add_hline(y=0, line_color="gray", opacity=0.4)
    fig.add_vline(x=0, line_color="gray", opacity=0.4)
    fig.update_layout(
        xaxis=dict(title="x", range=[-10, 10], gridcolor="#333"),
        yaxis=dict(title="y", range=[-10, 10], scaleanchor="x", scaleratio=1, gridcolor="#333"),
        margin=dict(l=40, r=20, t=20, b=40),
        height=600,
        showlegend=False,
    )

    if clicked_pts:
        xs, ys = zip(*clicked_pts)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", marker=dict(size=10)))

    if len(clicked_pts) >= 2:
        (x1, y1), (x2, y2) = clicked_pts[-2:]
        if x2 != x1:
            m = (y2 - y1) / (x2 - x1)
            b = y1 - m * x1
            x = np.linspace(-10, 10, 401)
            y = m * x + b
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="fit"))
        # vertical line (slope undefined) is left undrawn

    return fig


def is_graph_popup_requested() -> bool:
    return str(_qp_get("graph", "0")) == "1"


def render_graph_popup():
    """Full-page Graph Lab, rendered when the app is opened with ?graph=1 (the fab's target tab)."""
    st.title("Graph Lab — Linear Functions")
    tab1, tab2 = st.tabs(["Sliders: y = m x + b", "Click 2 points → line"])

    with tab1:
        m = st.slider("Slope (m)", -5.0, 5.0, 1.0, 0.1)
        b = st.slider("Intercept (b)", -10.0, 10.0, 0.0, 0.5)
        x = np.linspace(-10, 10, 401)
        y = m * x + b

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines"))
        fig.add_hline(y=0, line_color="gray", opacity=0.4)
        fig.add_vline(x=0, line_color="gray", opacity=0.4)
        fig.update_layout(
            xaxis=dict(title="x", range=[-10, 10], gridcolor="#333"),
            yaxis=dict(title="y", range=[-10, 10], scaleanchor="x", scaleratio=1, gridcolor="#333"),
            margin=dict(l=40, r=20, t=20, b=40),
            height=600,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        x0 = st.number_input("Evaluate at x =", value=2.0, step=1.0)
        st.write(f"y({x0}) = {m*x0 + b:.2f}")

    with tab2:
        if "clicked_pts" not in st.session_state:
            st.session_state.clicked_pts = []

        fig2 = _build_click_figure(st.session_state.clicked_pts)
        # plotly_events BOTH renders the chart AND returns clicked points
        events = plotly_events(
            fig2, click_event=True, hover_event=False, select_event=False, key="graphlab_clicks"
        )

        if events:
            st.session_state.clicked_pts.append((events[0]["x"], events[0]["y"]))
            st.rerun()

        if len(st.session_state.clicked_pts) >= 2:
            (x1, y1), (x2, y2) = st.session_state.clicked_pts[-2:]
            if x2 != x1:
                m = (y2 - y1) / (x2 - x1)
                b = y1 - m * x1
                st.write(f"Slope **m = {m:.3f}**, Intercept **b = {b:.3f}**")
            else:
                st.info("Vertical line — slope undefined.")

        colA, colB = st.columns(2)
        with colA:
            if st.button("Clear points"):
                st.session_state.clicked_pts = []
                st.rerun()
        with colB:
            if st.button("Close window"):
                _qp_set()  # clears query params
                st.write("You can close this tab now.")


def render_graph_fab():
    """Floating action button that opens the Graph Lab popup (?graph=1) in a new tab."""
    st.components.v1.html(
        """
        <style>
        .fab-graph {
            position: fixed;
            right: 24px;
            bottom: 24px;
            z-index: 10000;
            background: #3b82f6;
            color: white;
            border-radius: 999px;
            padding: 12px 16px;
            font-weight: 600;
            text-decoration: none;
            box-shadow: 0 6px 16px rgba(0,0,0,0.3);
            font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
        }
        .fab-graph:hover { filter: brightness(1.05); }
        </style>
        <a class="fab-graph" href="?graph=1" target="_blank" rel="noopener">📈 Graph</a>
        """,
        height=0,
    )
