# 0002. Streamlit Monolith with Native Material Symbols and shadcn/Antd Extensions

**Status:** accepted

We keep **Python + Streamlit (`>=1.40`)** as a single-process web monolith rather than splitting into a FastAPI backend and React/Next.js frontend, and we standardize the UI layer on **native Streamlit Material Symbols (`:material/...:`)**, **`streamlit-shadcn-ui`**, **`streamlit-antd-components`**, **Plotly**, and **`ui/theme.py`**.

## Context & Trade-offs

TindahanIQ is a single-store retail BI application deployed on Streamlit Community Cloud. Maintaining a separate JS/React frontend and API server adds deployment, CORS, and state-sync complexity without user benefit for this scope. To eliminate emoji-based "AI-slop" icons while staying inside Streamlit, native Material Symbols (`:material/...:`) replace emojis across navigation, metrics, and actions, paired with `streamlit-shadcn-ui` and `streamlit-antd-components` for cohesive cards, badges, and navigation controls.
