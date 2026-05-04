"""CSS global para o IFC Quality Copilot.

Importar via:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
"""

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Sora:wght@300;400;500;600;700;800&display=swap');

:root {
    --bg: #0a1720;
    --bg-alt: #122632;
    --panel: rgba(14, 32, 42, 0.82);
    --panel-strong: rgba(17, 39, 52, 0.95);
    --panel-soft: rgba(21, 49, 63, 0.76);
    --border: rgba(182, 156, 84, 0.2);
    --border-strong: rgba(215, 186, 109, 0.34);
    --text: #f4efe3;
    --muted: #b8b2a2;
    --accent: #d7ba6d;
    --accent-2: #6f8fa6;
    --success: #5db38c;
    --warning: #d7ba6d;
    --danger: #d46a5f;
    --shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
}

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: 'Sora', sans-serif;
    color: var(--text);
}

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at top left, rgba(215, 186, 109, 0.14), transparent 24%),
        radial-gradient(circle at 85% 0%, rgba(111, 143, 166, 0.14), transparent 20%),
        linear-gradient(180deg, #08131b 0%, #0c1d27 46%, #09161e 100%);
}

[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(15, 33, 44, 0.97) 0%, rgba(10, 23, 31, 0.99) 100%);
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] > div:first-child {
    background: transparent;
}

.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1440px;
}

button, [role="button"], label[data-testid], .stRadio label {
    cursor: pointer !important;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Sora', sans-serif;
    letter-spacing: -0.03em;
}

p, li, label, [data-testid="stMarkdownContainer"] {
    color: var(--text);
}

code, pre, .issue-element-ref, .prov-chip, .normref-badge,
[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', monospace !important;
}

.sidebar-brand {
    display: flex;
    align-items: center;
    gap: 0.85rem;
    padding: 0.35rem 0 0.2rem 0;
}

.sidebar-brand img {
    width: 52px;
    height: auto;
    flex: 0 0 auto;
}

.sidebar-brand-title {
    color: var(--text);
    font-size: 1.2rem;
    font-weight: 800;
    letter-spacing: -0.05em;
    line-height: 1.05;
}

[data-testid="stVerticalBlockBorderWrapper"] > div,
[data-testid="stExpander"] details,
[data-testid="stDataFrame"],
[data-testid="stMetric"] {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 24px !important;
    box-shadow: var(--shadow);
    backdrop-filter: blur(18px);
}

[data-testid="stVerticalBlockBorderWrapper"] > div:hover {
    border-color: var(--border-strong);
}

[data-testid="stMetric"] {
    padding: 0.35rem 0.2rem;
}

[data-testid="stMetricLabel"] {
    color: var(--muted) !important;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-size: 0.68rem !important;
}

[data-testid="stMetricValue"] {
    color: var(--text) !important;
    font-size: 1.5rem !important;
    letter-spacing: -0.04em;
}

[data-testid="stProgress"] > div {
    background: rgba(255, 255, 255, 0.06);
    border-radius: 999px;
}

[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #8fa8ba 0%, #5db38c 55%, #d7ba6d 100%);
    border-radius: 999px;
    transition: width 300ms ease;
}

[data-testid="stTabs"] {
    gap: 0.5rem;
}

[data-testid="stTabs"] [role="tablist"] {
    gap: 0.65rem;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border);
    padding: 0.35rem;
    border-radius: 999px;
}

[data-testid="stTabs"] button {
    border-radius: 999px !important;
    color: var(--muted) !important;
    font-weight: 600 !important;
    padding: 0.55rem 1rem !important;
    transition: all 160ms ease;
}

[data-testid="stTabs"] button[aria-selected="true"] {
    color: #0b1620 !important;
    background: linear-gradient(135deg, #d7ba6d 0%, #8fa8ba 100%) !important;
    border-bottom: none !important;
    box-shadow: 0 10px 24px rgba(215, 186, 109, 0.2);
}

[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div,
[data-testid="stTextArea"] textarea {
    background: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid var(--border) !important;
    border-radius: 16px !important;
    color: var(--text) !important;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(215, 186, 109, 0.12) !important;
}

[data-testid="stButton"] > button,
[data-testid="stDownloadButton"] > button {
    border-radius: 16px !important;
    border: 1px solid var(--border) !important;
    background: rgba(255, 255, 255, 0.04);
    color: var(--text);
    font-weight: 600;
    transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
}

[data-testid="stButton"] > button:hover,
[data-testid="stDownloadButton"] > button:hover {
    transform: translateY(-1px);
    border-color: var(--border-strong) !important;
    background: rgba(255, 255, 255, 0.06);
}

[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #d7ba6d 0%, #8fa8ba 100%);
    color: #0b1620;
    border: none !important;
    box-shadow: 0 12px 28px rgba(215, 186, 109, 0.2);
}

[data-testid="stButton"] > button[kind="primary"]:hover {
    filter: brightness(1.03);
}

[data-testid="stRadio"] label {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 0.6rem 0.75rem;
    margin-bottom: 0.4rem;
}

[data-testid="stRadio"] label:has(input:checked) {
    border-color: rgba(215, 186, 109, 0.38);
    background: rgba(215, 186, 109, 0.10);
}

[data-testid="stExpander"] summary {
    font-weight: 600;
    letter-spacing: -0.02em;
}

hr {
    border-color: rgba(148, 174, 190, 0.16) !important;
    margin: 1rem 0 !important;
}

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: #06131a; }
::-webkit-scrollbar-thumb {
    background: rgba(148, 174, 190, 0.28);
    border-radius: 999px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(148, 174, 190, 0.4); }

.app-hero,
.dashboard-shell,
.dashboard-panel,
.dashboard-stat,
.dashboard-mini,
.dashboard-kpi,
.dashboard-note {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 28px;
    background: linear-gradient(180deg, rgba(11, 32, 41, 0.92) 0%, rgba(8, 21, 28, 0.94) 100%);
    box-shadow: var(--shadow);
}

.app-hero::before,
.dashboard-shell::before,
.dashboard-panel::before,
.dashboard-stat::before,
.dashboard-mini::before,
.dashboard-kpi::before {
    content: "";
    position: absolute;
    inset: 0;
    background:
        radial-gradient(circle at top right, rgba(99, 210, 255, 0.10), transparent 26%),
        radial-gradient(circle at bottom left, rgba(246, 169, 59, 0.08), transparent 22%);
    pointer-events: none;
}

.dashboard-shell {
    padding: 1.4rem 1.5rem;
    margin-bottom: 1rem;
}

.app-hero {
    padding: 1.6rem 1.7rem;
    margin-bottom: 1rem;
}

.hero-kicker,
.dashboard-kicker {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--accent);
    font-weight: 700;
    margin-bottom: 0.5rem;
}

.hero-title {
    font-size: clamp(1.8rem, 2vw, 2.8rem);
    line-height: 1.02;
    font-weight: 800;
    letter-spacing: -0.05em;
    margin: 0;
}

.hero-subtitle,
.dashboard-muted {
    color: var(--muted);
    font-size: 0.92rem;
    line-height: 1.6;
}

.hero-chip-row,
.dashboard-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.55rem;
    margin-top: 1rem;
}

.hero-chip,
.dashboard-chip {
    border: 1px solid var(--border);
    background: rgba(255, 255, 255, 0.03);
    color: var(--text);
    border-radius: 999px;
    padding: 0.38rem 0.8rem;
    font-size: 0.72rem;
    font-weight: 600;
}

.dashboard-kpi {
    padding: 1rem 1.1rem;
    min-height: 148px;
}

.dashboard-kpi-label {
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.18em;
    font-size: 0.66rem;
    font-weight: 700;
}

.dashboard-kpi-value {
    margin-top: 0.85rem;
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.06em;
    color: var(--text);
}

.dashboard-kpi-delta {
    margin-top: 0.65rem;
    color: var(--muted);
    font-size: 0.82rem;
    line-height: 1.45;
}

.dashboard-panel {
    padding: 1.15rem 1.2rem;
    margin-bottom: 1rem;
}

.dashboard-panel-title {
    font-size: 1rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: -0.03em;
}

.dashboard-panel-subtitle {
    color: var(--muted);
    font-size: 0.83rem;
    margin-top: 0.35rem;
}

.dashboard-stat {
    padding: 1rem 1.05rem;
    min-height: 120px;
}

.dashboard-stat-value {
    font-size: 1.65rem;
    font-weight: 800;
    letter-spacing: -0.05em;
}

.dashboard-stat-label {
    color: var(--muted);
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    margin-top: 0.55rem;
}

.dashboard-stat-copy {
    margin-top: 0.8rem;
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1.5;
}

.dashboard-note {
    padding: 0.95rem 1rem;
    margin-bottom: 1rem;
}

.dashboard-note strong {
    color: var(--text);
}

.dashboard-table-caption {
    color: var(--muted);
    font-size: 0.78rem;
    margin-top: 0.35rem;
}

.welcome-hero {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 28px;
    background:
        linear-gradient(180deg, rgba(18, 39, 52, 0.95) 0%, rgba(11, 24, 33, 0.96) 100%);
    box-shadow: var(--shadow);
}

.welcome-hero::before {
    content: "";
    position: absolute;
    inset: 0;
    background:
        radial-gradient(circle at top right, rgba(215, 186, 109, 0.12), transparent 24%),
        radial-gradient(circle at bottom left, rgba(111, 143, 166, 0.12), transparent 20%);
    pointer-events: none;
}

.welcome-hero {
    padding: 1.8rem 1.9rem;
    margin-bottom: 1rem;
}

.welcome-kicker {
    font-size: 0.74rem;
    text-transform: uppercase;
    letter-spacing: 0.26em;
    color: var(--accent);
    font-weight: 700;
    margin-bottom: 0.6rem;
}

.welcome-title {
    margin: 0;
    font-size: clamp(2rem, 2.4vw, 3.1rem);
    line-height: 1;
    font-weight: 800;
    letter-spacing: -0.05em;
}

.welcome-subtitle {
    max-width: 62rem;
    margin-top: 0.9rem;
    color: var(--muted);
    font-size: 0.98rem;
    line-height: 1.7;
}

.guide-hero,
.tutorial-card {
    position: relative;
    overflow: hidden;
    border: 1px solid var(--border);
    border-radius: 28px;
    background:
        linear-gradient(180deg, rgba(18, 39, 52, 0.95) 0%, rgba(8, 21, 28, 0.96) 100%);
    box-shadow: var(--shadow);
}

.guide-hero::before,
.tutorial-card::before {
    content: "";
    position: absolute;
    inset: 0;
    background:
        linear-gradient(135deg, rgba(215, 186, 109, 0.12), transparent 36%),
        radial-gradient(circle at 92% 18%, rgba(93, 179, 140, 0.12), transparent 24%);
    pointer-events: none;
}

.guide-hero {
    padding: 1.45rem 1.55rem;
    margin-bottom: 1rem;
}

.guide-hero.compact {
    margin-top: 0.5rem;
}

.guide-kicker {
    color: var(--accent);
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.22em;
    text-transform: uppercase;
}

.guide-title {
    margin: 0.45rem 0 0 0;
    font-size: clamp(1.45rem, 1.8vw, 2.2rem);
    line-height: 1.05;
    letter-spacing: -0.05em;
}

.guide-copy {
    margin-top: 0.75rem;
    color: var(--muted);
    line-height: 1.65;
    max-width: 58rem;
}

.tutorial-card {
    padding: 1rem 1.05rem;
    min-height: 155px;
    margin-bottom: 0.85rem;
}

.tutorial-title {
    color: var(--text);
    font-size: 0.95rem;
    font-weight: 800;
    letter-spacing: -0.03em;
}

.tutorial-copy {
    margin-top: 0.65rem;
    color: var(--muted);
    line-height: 1.55;
    font-size: 0.82rem;
}

.issue-header-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 0.1rem;
}

.issue-title {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text);
    margin: 0;
    letter-spacing: -0.03em;
}

.issue-element-ref {
    font-size: 0.82rem;
    color: #7f99aa;
    margin-bottom: 0.5rem;
}

.severity-badge,
.status-badge,
.source-badge {
    display: inline-block;
    font-size: 0.73rem;
    font-weight: 700;
    padding: 0.18rem 0.58rem;
    border-radius: 999px;
    vertical-align: middle;
}

.normref-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 8px;
    background: rgba(99, 210, 255, 0.14);
    color: #a9e8ff;
    margin-left: 0.4rem;
    vertical-align: middle;
}

.context-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 0.55rem 0.9rem;
    margin: 0.7rem 0;
}

.context-item {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(130, 172, 191, 0.12);
    border-radius: 16px;
    padding: 0.7rem 0.75rem;
}

.context-key {
    color: #7f99aa;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
}

.context-val {
    color: #dceaf2;
    font-weight: 600;
    margin-top: 0.2rem;
}

.resolution-box {
    background: rgba(255, 255, 255, 0.03);
    border-left: 3px solid;
    border-radius: 16px;
    padding: 0.75rem 0.95rem;
    margin-top: 0.65rem;
    font-size: 0.85rem;
}

.prov-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.55rem 0 0.25rem 0;
}

.prov-chip {
    display: inline-block;
    padding: 0.18rem 0.56rem;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.04);
    color: #dceaf2;
    border: 1px solid rgba(130, 172, 191, 0.16);
    font-size: 0.7rem;
}

.validation-box {
    margin-top: 0.55rem;
    padding: 0.55rem 0.8rem;
    border: 1px solid;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.02);
    font-size: 0.78rem;
    font-weight: 700;
}

.state-card {
    border: 1px solid;
    border-radius: 18px;
    padding: 0.9rem 1rem;
    margin-bottom: 0.3rem;
    background: rgba(255, 255, 255, 0.03);
}
</style>
"""
