# 🧠 CogAccess — Cognitive Accessibility Assistant

A Streamlit application that analyses web pages for cognitive accessibility barriers,
maps findings to WCAG 2.2 and ISO 9241-11, and supports NASA-TLX cognitive load measurement.

## Features

- **Five-dimension analysis**: Language complexity, layout density, visual hierarchy, animation/motion, navigation consistency
- **WCAG 2.2 mapping**: Every finding links to a specific success criterion (e.g. 3.1.5, 1.4.8, 2.2.2)
- **ISO 9241-11 alignment**: Scores map to effectiveness, efficiency, and satisfaction
- **NASA-TLX evaluation**: Six-subscale cognitive load measurement with cross-reference to analysis scores
- **Adaptation suggestions**: Concrete, actionable fixes with honest trade-off notes
- **Report export**: Download a full Markdown report for stakeholder review

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
streamlit run app.py
```

### 3. Add your API key

Enter your Anthropic API key in the sidebar when the app opens.  
Get a key at: https://console.anthropic.com/

## Usage

1. Paste any public URL into the input field and click **Analyse**
2. Review dimension scores on the **Dashboard** tab
3. Explore detailed findings (with WCAG/ISO citations) on the **Findings** tab
4. Read actionable suggestions (with trade-off notes) on the **Adaptations** tab
5. Complete the NASA-TLX evaluation on the **NASA-TLX Evaluation** tab
6. Download the full report from the sidebar

## Project context

Built for the Cognitive Accessibility Assistant project brief.  
Frameworks: WCAG 2.2 Cognitive Accessibility Guidance · ISO 9241-11 · NASA-TLX

## Project structure

```
cognitive_accessibility_assistant/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md           # This file
```