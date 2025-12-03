import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Polymarket Explorer", layout="wide")

# --- AJOUT STYLE MOBILE (Coller ici) ---
st.markdown("""
    <style>
        /* Réduit les marges pour gagner de la place sur mobile */
        .block-container {
            padding-top: 1rem;
            padding-bottom: 0rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        /* Masque le menu hamburger et le footer Streamlit pour faire "App" */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)
# ---------------------------------------

st.title("🦅 Polymarket Explorer")

if st.button("🔄 Rafraîchir les données"):
    st.cache_data.clear()

# --- CONSTANTES ---
MAIN_CATEGORIES = [
    "Politics", "Crypto", "Sports", "Business", 
    "Science", "Pop Culture", "News", "Economics"
]

# --- BARRE LATÉRALE (FILTRES) ---
st.sidebar.header("🛡️ Sécurité & Bots")
exclude_up_down = st.sidebar.checkbox("Masquer Bots 'Up/Down'", value=True)

st.sidebar.header("⏱️ Temps")
max_days = st.sidebar.slider("Expiration Max (Jours)", 0, 30, 7) 

st.sidebar.header("💰 Financier")
# LE NOUVEAU FILTRE EST ICI :
min_vol = st.sidebar.number_input("Volume Global Min ($)", value=1000, step=1000, help="Volume total échangé depuis la création du marché.")
min_liquidity = st.sidebar.number_input("Liquidité Min ($)", value=100, step=100, help="Profondeur du carnet d'ordres actuel.")

# --- FONCTION DE RÉCUPÉRATION ---
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
        
        market_list = []
        for item in data:
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

            # 4. Prix & Données Financières
            try:
                prices = json.loads(m.get('outcomePrices', '["0","0"]'))
                price_yes = float(prices[0])
            except: price_yes = 0

            liq = float(m.get('liquidity', 0) or 0)
            vol = float(item.get('volume', 0) or 0)

            # --- APPLICATION DES FILTRES (VOLUME + LIQUIDITÉ + TEMPS) ---
            if (hours_left <= (max_days * 24)) and \
               (liq >= min_liquidity) and \
               (vol >= min_vol): # <-- Condition ajoutée ici
                
                market_list.append({
                    "Catégorie": market_category,
                    "Titre": item.get('title'),
                    "Temps": time_display,
                    "Prix": price_yes,
                    "Liquidité": liq,
                    "Volume": vol,
                    "Tri_Technique": hours_left,
                    "Lien": f"https://polymarket.com/event/{item.get('slug')}"
                })
            
        return pd.DataFrame(market_list)

    except Exception as e:
        st.error(f"Erreur API : {e}")
        return pd.DataFrame()

# --- INTERFACE ---
df = fetch_markets()

if not df.empty:
    found_cats = sorted(list(df["Catégorie"].unique()))
    all_options = sorted(list(set(MAIN_CATEGORIES + found_cats)))
    
    st.sidebar.header("📂 Filtrer par Thème")
    selected_cats = st.sidebar.multiselect(
        "Choisir les catégories", 
        all_options,
        default=found_cats
    )
    
    filtered_df = df[df["Catégorie"].isin(selected_cats)]
    filtered_df = filtered_df.sort_values(by="Tri_Technique", ascending=True)
    display_df = filtered_df.drop(columns=["Tri_Technique"])

    st.dataframe(
        display_df,
        column_config={
            "Lien": st.column_config.LinkColumn("Lien"),
            "Prix": st.column_config.ProgressColumn("Prix (Oui)", format="%.2f", min_value=0, max_value=1),
            "Liquidité": st.column_config.NumberColumn(format="$%d"),
            "Volume": st.column_config.NumberColumn(format="$%d"), # Affichage du volume
            "Catégorie": st.column_config.TextColumn("Catégorie", width="medium"),
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.caption(f"{len(filtered_df)} marchés trouvés.")

else:
    st.warning("Aucune donnée chargée.")