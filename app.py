
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Explorer", layout="wide")

# --- STYLE MOBILE ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        /* Rend le tableau plus lisible sur petit écran */
        .stDataFrame { font-size: 0.8rem; }
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Polymarket Explorer")

# --- CONSTANTES ---
MAIN_CATEGORIES = [
    "Politics", "Crypto", "Sports", "Business", 
    "Science", "Pop Culture", "News", "Economics"
]

# --- FONCTION API (Mise en cache) ---
@st.cache_data(ttl=60)
def fetch_markets(limit=1000):
    url = "https://gamma-api.polymarket.com/events"
    params = {
        "limit": limit,
        "active": "true",
        "closed": "false",
        "order": "endDate",
        "ascending": "true"
    }
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        return data
    except Exception as e:
        return []

# --- CHARGEMENT DES DONNÉES ---
raw_data = fetch_markets()

# --- ZONE DE FILTRES (Au centre, pas dans la sidebar) ---
# On utilise un "expander" qui est replié par défaut pour ne pas gêner
with st.expander("⚙️ RÉGLAGES & FILTRES (Cliquer pour ouvrir)", expanded=False):
    
    st.write("### ⏱️ Temps & Argent")
    c1, c2 = st.columns(2)
    with c1:
        max_days = st.slider("Jours restants Max", 0, 30, 7)
        min_vol = st.number_input("Volume Min ($)", value=1000, step=1000)
    with c2:
        min_liquidity = st.number_input("Liquidité Min ($)", value=100, step=100)
        exclude_up_down = st.checkbox("Masquer Bots 'Up/Down'", value=True)

    st.write("### 📂 Catégories")
    # On pré-calcule les catégories dispos
    all_found_cats = set()
    for item in raw_data:
        tags = item.get('tags', [])
        for t in tags:
            if t.get('label'): all_found_cats.add(t.get('label'))
            
    # On mixe avec les catégories principales
    options = sorted(list(set(MAIN_CATEGORIES + list(all_found_cats))))
    
    selected_cats = st.multiselect(
        "Thèmes", 
        options,
        default=[c for c in MAIN_CATEGORIES if c in options] # Par défaut on coche les principaux
    )
    
    if st.button("🔄 Rafraîchir les données maintenant"):
        st.cache_data.clear()
        st.rerun()

# --- TRAITEMENT DES DONNÉES ---
market_list = []

if raw_data:
    for item in raw_data:
        if not item.get('markets'): continue

        # 1. Filtre Anti-Bot
        title = item.get('title', '').lower()
        if exclude_up_down:
            if "up or down" in title or "up/down" in title or "15min" in title:
                continue

        # 2. Catégorisation
        tags_raw = item.get('tags', [])
        market_category = "Autre"
        current_tags = [t.get('label') for t in tags_raw if t.get('label')]
        
        found_main = False
        for main_cat in MAIN_CATEGORIES:
            if main_cat in current_tags:
                market_category = main_cat
                found_main = True
                break
        if not found_main and current_tags:
            market_category = current_tags[0]

        # Filtre Catégorie (On filtre AVANT le traitement pour aller plus vite)
        if market_category not in selected_cats:
            continue

        m = item['markets'][0]
        
        # 3. Temps
        end_date_str = item.get('endDate')
        hours_left = 9999
        time_display = "N/A"
        
        if end_date_str:
            try:
                end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                now = datetime.now(end_dt.tzinfo)
                total_seconds = (end_dt - now).total_seconds()
                
                if total_seconds <= 0: continue
                hours_left = total_seconds / 3600
                days_left = hours_left / 24
                
                if days_left < 1:
                    time_display = f"{int(hours_left)}h 🔥"
                else:
                    time_display = f"{int(days_left)}j"
            except: pass

        # 4. Données Financières
        try:
            prices = json.loads(m.get('outcomePrices', '["0","0"]'))
            price_yes = float(prices[0])
        except: price_yes = 0

        liq = float(m.get('liquidity', 0) or 0)
        vol = float(item.get('volume', 0) or 0)

        # 5. Application Filtres numériques
        if (hours_left <= (max_days * 24)) and \
           (liq >= min_liquidity) and \
           (vol >= min_vol):
            
            market_list.append({
                "Catégorie": market_category,
                "Titre": item.get('title'),
                "Temps": time_display,
                "Prix": price_yes,
                "Vol.": vol,      # Nom raccourci pour mobile
                "Liq.": liq,      # Nom raccourci pour mobile
                "Tri_Technique": hours_left,
                "Lien": f"https://polymarket.com/event/{item.get('slug')}"
            })

    df = pd.DataFrame(market_list)

    if not df.empty:
        df = df.sort_values(by="Tri_Technique", ascending=True)
        display_df = df.drop(columns=["Tri_Technique"])

        st.caption(f"{len(df)} opportunités trouvées")
        
        st.dataframe(
            display_df,
            column_config={
                "Lien": st.column_config.LinkColumn("Go"), # Court pour mobile
                "Prix": st.column_config.ProgressColumn("Prix", format="%.2f", min_value=0, max_value=1),
                "Liq.": st.column_config.NumberColumn(format="$%d"),
                "Vol.": st.column_config.NumberColumn(format="$%d"),
                "Catégorie": st.column_config.TextColumn("Tag"),
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Aucun marché avec ces critères.")
else:
    st.error("Erreur de connexion API.")