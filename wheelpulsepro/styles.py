"""WheelPulsePro – extra CSS styles for the Gradio interface."""

_EXTRA_CSS = """
/* Selected Spins Input - full width and more readable */
#selected-spins,
#selected-spins > .wrap,
#selected-spins > label,
#selected-spins-input,
#selected-spins-input > .wrap,
#selected-spins-input > label {
    width: 100% !important;
    max-width: 100% !important;
}
#selected-spins textarea,
#selected-spins input,
#selected-spins-input textarea,
#selected-spins-input input {
    width: 100% !important;
    max-width: 100% !important;
    font-size: 16px !important;
    padding: 12px !important;
    min-height: 120px !important;
    max-height: 300px !important;
    overflow-y: auto !important;
    letter-spacing: 1px;
    font-family: 'Courier New', monospace;
}
#selected-spins label span,
#selected-spins-input label span {
    font-size: 16px !important;
    font-weight: 700 !important;
}

/* Accordion headers - more readable */
.gradio-accordion > .label-wrap {
    font-size: 16px !important;
    font-weight: 700 !important;
    padding: 12px !important;
}

/* Status bar: keep spin counter centered */
#status-bar-container {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: center !important;
    background: rgba(0, 0, 0, 0.05);
    border-radius: 12px;
    padding: 5px 15px !important;
    margin: 10px 0 !important;
    width: 100% !important;
}

#strategy-alert-overlay {
    width: 100% !important;
    border-left: 2px solid rgba(0,0,0,0.1);
    margin-left: 10px;
    border-radius: 8px;
    padding: 2px 8px;
    display: flex;
    align-items: center;
    min-height: 40px;
}

/* Spin counter: centered and wider */
.spin-counter-box {
    display: flex !important;
    justify-content: center !important;
    min-width: 220px !important;
    width: 100% !important;
    white-space: nowrap !important;
}

/* Selected spins row: full width matching accordions */
#selected-spins-row > div,
#selected-spins-row .gradio-column {
    width: 100% !important;
    max-width: 100% !important;
    flex: 1 1 100% !important;
    min-width: 0 !important;
}

/* Statistical Intelligence Layer — ensure all text is light on dark background */
#stat-intel-accordion > .label-wrap,
#stat-intel-accordion > .label-wrap span,
#stat-intel-accordion > .label-wrap button {
    color: #f1f5f9 !important;
}
#stat-intel-accordion b,
#stat-intel-accordion strong,
#stat-intel-accordion small,
#stat-intel-accordion h3,
#stat-intel-accordion h4,
#stat-intel-accordion label,
#stat-intel-accordion span {
    color: #e2e8f0 !important;
}
/* Ensure accordion label itself is visible */
.gradio-accordion#stat-intel-accordion > .label-wrap span,
details#stat-intel-accordion > summary span,
details#stat-intel-accordion > summary {
    color: #f1f5f9 !important;
}

/* Pulsing glow animation for the "If I were you" strong-signal card */
@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 8px #ef4444aa; border-color: #ef4444; }
    50%       { box-shadow: 0 0 22px #ef4444, 0 0 35px #ef4444aa; border-color: #fca5a5; }
}

/* Final Brain display — always visible live decision engine */
#final-brain-output {
    margin: 8px 0 10px 0;
}
/* Ensure all bold/strong text in Final Brain renders white, not browser-default black */
#final-brain-output b,
#final-brain-output strong,
#final-brain-output li {
    color: #e2e8f0 !important;
}
@keyframes final-brain-glow {
    0%, 100% { box-shadow: 0 0 10px rgba(99,102,241,0.4); border-color: #6366f1; }
    50%       { box-shadow: 0 0 28px rgba(99,102,241,0.8), 0 0 50px rgba(99,102,241,0.3); border-color: #818cf8; }
}

/* Roulette table pulse/glow when strategy cards are active */
@keyframes table-pulse-glow {
    0%, 100% { box-shadow: 0 0 15px 4px rgba(255, 215, 0, 0.5), inset 0 0 15px 2px rgba(255, 215, 0, 0.1); border-color: #FFD700; }
    50% { box-shadow: 0 0 30px 10px rgba(255, 165, 0, 0.8), inset 0 0 25px 5px rgba(255, 165, 0, 0.15); border-color: #FFA500; }
}
.roulette-table-pulse {
    animation: table-pulse-glow 1.5s ease-in-out infinite !important;
    border: 4px solid #FFD700 !important;
    border-radius: 8px !important;
}

/* Siren indicator — flashing 🚨 emoji at top-right of roulette table */
@keyframes siren-flash {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.3; transform: scale(1.3); }
}
.siren-indicator {
    position: absolute;
    top: 6px;
    right: 10px;
    font-size: 24px;
    z-index: 10;
    animation: siren-flash 0.8s ease-in-out infinite;
}

/* Alerts Sidebar — fixed right-side panel that follows the user as they scroll */
#alerts-sidebar {
    background: linear-gradient(145deg, #0f172a, #1e293b);
    border: 2px solid #FFD700;
    border-radius: 8px;
    padding: 8px 12px;
    margin-top: 6px;
    margin-bottom: 10px;
    font-size: 12px;
    box-shadow: 0 2px 12px rgba(255, 215, 0, 0.2);
}
"""
